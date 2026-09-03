# Informtit en GitHub Pages

La interfaz web se publica automáticamente desde `main` mediante `.github/workflows/pages.yml`.

## Arquitectura

- GitHub Pages sirve la misma interfaz HTML/CSS/JavaScript de `static/`.
- El backend Python se ejecuta con `python web_entry.py` en un servicio que permita procesos Python y almacenamiento persistente para `data/`.
- La URL pública del backend se configura en GitHub como variable de repositorio `INFORMTIT_API_BASE` (sin `/` final).
- `web_entry.py` admite por defecto `https://jeffer91.github.io` como origen CORS. Se puede ampliar mediante `INFORMTIT_ALLOWED_ORIGINS`, separado por comas.

## Contenedor del backend

El `Dockerfile` incluido arranca `web_entry.py` y respeta la variable `PORT` del proveedor. Para conservar SQLite entre despliegues, el proveedor debe montar almacenamiento persistente sobre la carpeta `data/` de la aplicación.

Si `INFORMTIT_API_BASE` todavía no está configurada, GitHub Pages muestra un panel para conectar temporalmente una URL de backend; la dirección queda guardada en el navegador.
