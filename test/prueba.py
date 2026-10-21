"""
Prueba automatica de index.html.

Crea fotos falsas con GPS cerca de Valdivia, abre la pagina en Chromium (Playwright),
genera el KMZ y verifica su contenido. Tambien prueba el visor de KMZ.

Requiere: pip install Pillow playwright  &&  python -m playwright install chromium
Uso:      python test/prueba.py
"""

import io
import os
import shutil
import sys
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

INDEX = Path(__file__).resolve().parent.parent / "index.html"
KML_NS = {"k": "http://www.opengis.net/kml/2.2"}

VALDIVIA = (-39.8142, -73.2459)


def a_dms(valor):
    valor = abs(valor)
    g = int(valor)
    m = int((valor - g) * 60)
    s = round(((valor - g) * 60 - m) * 60, 4)
    return (float(g), float(m), s)


def crear_foto(ruta, lat=None, lon=None, fecha=None, orientacion=1, tam=(600, 400), color=(200, 60, 60)):
    img = Image.new("RGB", tam, color)
    # Marca en la esquina superior izquierda para poder comprobar la rotacion
    img.paste((255, 255, 0), (0, 0, 60, 30))
    exif = Image.Exif()
    exif[0x0112] = orientacion
    if fecha:
        exif.get_ifd(0x8769)[0x9003] = fecha  # DateTimeOriginal
    if lat is not None:
        gps = exif.get_ifd(0x8825)
        gps[1] = "S" if lat < 0 else "N"
        gps[2] = a_dms(lat)
        gps[3] = "W" if lon < 0 else "E"
        gps[4] = a_dms(lon)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    img.save(ruta, "JPEG", exif=exif, quality=90)


def generar_kmz(page, carpeta, descargas):
    page.goto(INDEX.as_uri())
    page.wait_for_function("typeof exifr !== 'undefined' && typeof JSZip !== 'undefined'", timeout=30000)
    page.set_input_files("#inCarpeta", str(carpeta))
    page.wait_for_selector("#btnGenerar:not([disabled])")
    with page.expect_download(timeout=60000) as info:
        page.click("#btnGenerar")
    destino = descargas / info.value.suggested_filename
    info.value.save_as(destino)
    page.wait_for_selector("#resumen:not([hidden])")
    return destino, page.inner_text("#resumen")


def fallar(msg):
    print("FALLA:", msg)
    sys.exit(1)


def comprobar(cond, msg):
    if not cond:
        fallar(msg)
    print("  ok -", msg)


def main():
    tmp = Path(tempfile.mkdtemp(prefix="prueba_kmz_"))
    try:
        # ---- Caso 1: una carpeta, 5 fotos con GPS + 1 sin GPS + 1 danada ----
        vuelo = tmp / "vuelo_prueba"
        # Fechas desordenadas respecto al nombre, para comprobar el orden por captura
        fechas = ["2026:10:21 10:04:00", "2026:10:21 10:01:00", "2026:10:21 10:03:00",
                  "2026:10:21 10:00:00", "2026:10:21 10:02:00"]
        for i, f in enumerate(fechas):
            lat = VALDIVIA[0] + i * 0.001
            lon = VALDIVIA[1] + i * 0.001
            crear_foto(vuelo / f"DJI_{i:04d}.JPG", lat, lon, f, orientacion=6 if i == 0 else 1)
        crear_foto(vuelo / "sin_gps.jpg", fecha="2026:10:21 10:05:00")
        crear_foto(vuelo / "zz_danada.jpeg", -39.82, -73.25, "2026:10:21 10:06:00")
        datos = (vuelo / "zz_danada.jpeg").read_bytes()
        (vuelo / "zz_danada.jpeg").write_bytes(datos[:datos.index(b"\xff\xda")])  # EXIF intacto, sin datos de imagen

        # ---- Caso 2: carpeta con 2 subcarpetas (una linea por subcarpeta) ----
        multi = tmp / "obra_multi"
        for s, sub in enumerate(["vuelo A", "vuelo B"]):
            for i in range(3):
                crear_foto(multi / sub / f"IMG_{i}.jpg", VALDIVIA[0] + s * 0.01 + i * 0.001,
                           VALDIVIA[1] + i * 0.001, f"2026:10:2{s} 09:0{i}:00")

        descargas = tmp / "descargas"
        descargas.mkdir()

        with sync_playwright() as p:
            navegador = p.chromium.launch()
            page = navegador.new_page(accept_downloads=True)
            errores = []
            page.on("pageerror", lambda e: errores.append(str(e)))

            print("Caso 1: carpeta simple")
            kmz, resumen = generar_kmz(page, vuelo, descargas)
            comprobar(kmz.name == "vuelo_prueba.kmz", f"nombre por defecto = nombre de carpeta ({kmz.name})")
            comprobar("Fotos incluidas\t5" in resumen, "resumen: 5 fotos incluidas")
            comprobar("Fotos sin GPS (omitidas)\t1" in resumen, "resumen: 1 foto sin GPS")
            comprobar("Archivos dañados (omitidos)\t1" in resumen, "resumen: 1 archivo dañado")

            with zipfile.ZipFile(kmz) as z:
                nombres = [n for n in z.namelist() if not n.endswith("/")]
                comprobar(z.testzip() is None, "el KMZ es un zip valido")
                iconos = [n for n in nombres if n.startswith("miniaturas/")]
                fotos = [n for n in nombres if n.startswith("fotos/")]
                comprobar(len(iconos) == 5, f"5 iconos ({len(iconos)})")
                comprobar(len(fotos) == 5, f"5 fotos ({len(fotos)})")
                raiz = ET.fromstring(z.read("doc.kml"))
                comprobar(raiz.find("k:Document/k:name", KML_NS).text == "vuelo_prueba", "Document con nombre de la carpeta")
                pms = [pm for pm in raiz.iter("{%s}Placemark" % KML_NS["k"]) if pm.find("k:Point", KML_NS) is not None]
                comprobar(len(pms) == 5, "doc.kml valido con 5 Placemarks de foto")
                linea = raiz.find(".//k:LineString/k:coordinates", KML_NS).text.split()
                comprobar(len(linea) == 5, "linea con 5 puntos")
                # Orden esperado por fecha: DJI_0003, 0001, 0004, 0002, 0000
                esperado = [3, 1, 4, 2, 0]
                lats = [round(float(c.split(",")[1]), 4) for c in linea]
                comprobar(lats == [round(VALDIVIA[0] + i * 0.001, 4) for i in esperado], "linea ordenada por fecha de captura")
                desc = pms[0].find("k:description", KML_NS).text
                comprobar('src="fotos/DJI_0003.jpg"' in desc, "Foto 1 = la mas antigua, ruta relativa")
                comprobar("http" not in pms[0].find(".//k:Icon/k:href", KML_NS).text, "icono con ruta relativa")
                comprobar("maps/dir/?api=1&destination=" in desc and "origin=" in desc, "links Como llegar")
                comprobar(all(n in nombres for n in ("fotos/DJI_0003.jpg", "miniaturas/DJI_0003.jpg")), "rutas existen dentro del KMZ")
                icono = Image.open(io.BytesIO(z.read("miniaturas/DJI_0001.jpg")))
                comprobar(icono.size == (96, 96), f"miniatura 96x96 ({icono.size})")
                rotada = Image.open(io.BytesIO(z.read("fotos/DJI_0000.jpg")))
                comprobar(rotada.size == (400, 600), f"orientacion EXIF aplicada ({rotada.size})")
                # Con orientacion 6 la marca amarilla (arriba-izq) debe quedar arriba-derecha
                r, g, b = rotada.convert("RGB").getpixel((385, 20))
                comprobar(r > 200 and g > 200 and b < 100, "rotacion en el sentido correcto")

            print("Caso 2: carpeta con subcarpetas")
            kmz2, resumen2 = generar_kmz(page, multi, descargas)
            with zipfile.ZipFile(kmz2) as z:
                raiz = ET.fromstring(z.read("doc.kml"))
                carpetas = raiz.findall(".//k:Folder", KML_NS)
                comprobar(len(carpetas) == 2, "2 Folders (una por subcarpeta)")
                comprobar(len(raiz.findall(".//k:LineString", KML_NS)) == 2, "2 lineas de recorrido")
                comprobar(len([n for n in z.namelist() if n.startswith("fotos/") and not n.endswith("/")]) == 6, "6 fotos")
                comprobar("fotos/vuelo_A__IMG_0.jpg" in z.namelist(), "nombres sin choques entre subcarpetas")

            print("Caso 3: visor de KMZ")
            page.goto(INDEX.as_uri())
            page.wait_for_function("typeof JSZip !== 'undefined'", timeout=30000)
            page.set_input_files("#inKmz", str(kmz))
            page.wait_for_function("document.querySelectorAll('#galeria img[src]').length === 5")
            comprobar(True, "galeria con 5 miniaturas")
            page.click("#galeria button >> nth=2")
            page.wait_for_selector("#modal:not([hidden])")
            comprobar("Foto 3" in page.inner_text("#modalTitulo"), "se abre la foto grande")
            with page.expect_download() as info:
                page.click("#modalDescargar")
            destino = descargas / info.value.suggested_filename
            info.value.save_as(destino)
            comprobar(Image.open(destino).format == "JPEG", f"descarga de foto individual ({destino.name})")

            comprobar(not errores, f"sin errores de JavaScript {errores}")
            navegador.close()

        print("\nTODAS LAS PRUEBAS PASARON")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
