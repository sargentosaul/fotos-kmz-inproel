# Fotos a KMZ - Inproel

Página web que convierte una carpeta de fotos con GPS (dron o celular) en un **recorrido fotográfico KMZ** para Google Earth.

**Las fotos se procesan en tu computador, no se suben a internet.** No hay que instalar nada.

## Cómo usarla

1. Abre el link de la herramienta en Chrome o Edge.
2. Pincha **Elegir carpeta de fotos** (o arrastra la carpeta a la página).
3. Revisa el nombre del archivo (por defecto, el de la carpeta).
4. Pincha **Generar KMZ** y espera la barra de progreso. El archivo se descarga solo.
5. Ábrelo con **Google Earth Pro**.

En el mapa verás:

- cada foto como miniatura en el lugar donde se tomó (al pincharla se agranda),
- una línea roja que une las fotos en el orden en que fueron tomadas,
- links "Cómo llegar" (A aquí / De aquí) a Google Maps.

**Consejo:** usa una carpeta por vuelo. Si la carpeta tiene subcarpetas, cada subcarpeta tendrá su propia línea de recorrido.

Las fotos sin GPS se omiten, y el resumen final dice cuántas fueron.

## Ver y descargar fotos de un KMZ

En la sección **2. Ver y descargar fotos de un KMZ** puedes abrir cualquier KMZ hecho con esta herramienta (o con el antiguo `FotosAKMZ.exe`). Verás todas las fotos en una galería y podrás descargar la que necesites. Las fotos descargadas son las del KMZ, de máximo 1024 px.

## Prueba automática

```
pip install Pillow playwright
python -m playwright install chromium
python test/prueba.py
```

La prueba crea fotos falsas con GPS cerca de Valdivia, genera el KMZ en un navegador y revisa su contenido.
