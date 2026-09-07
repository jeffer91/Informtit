# Informtit

Informtit funciona únicamente como aplicación web en **GitHub Pages**, con **Firebase** como fuente compartida de datos.

## Aplicación

https://jeffer91.github.io/Informtit/

## Estructura del repositorio

- `static/`: aplicación web completa y runtimes de Firebase.
- `.github/workflows/pages.yml`: validación y despliegue automático a GitHub Pages.

El repositorio ya no mantiene una versión Electron, un backend Python, SQLite local, empaquetado de escritorio ni pruebas asociadas a esas implementaciones.

## Despliegue

Cada cambio enviado a `main` valida los JavaScript de `static/`, construye el sitio y publica automáticamente GitHub Pages.

La referencia funcional y visual oficial de Informtit es la versión publicada en GitHub Pages.
