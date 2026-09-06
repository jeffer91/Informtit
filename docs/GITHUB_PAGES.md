# Informtit en GitHub Pages

La interfaz web se publica automáticamente desde `main` mediante `.github/workflows/pages.yml`.

## URL

La dirección del frontend es `https://jeffer91.github.io/Informtit/`.

## Arquitectura de paridad

GitHub Pages y `npm start` usan la misma carpeta `static/` y el mismo backend Python preparado por `desktop_entry.prepare()`.

- `npm start` abre Electron y levanta el backend local de Informtit.
- GitHub Pages sirve exactamente los mismos HTML, CSS y JavaScript de `static/`.
- En Pages solo se añade `web-config.js` + `web-runtime.js` para dirigir `/api`, `/uploads` y `/exports` al backend web.
- Ya no se cargan emuladores paralelos de informes, Firebase o `localStorage` para sustituir el backend. Así se evita que la versión web tenga reglas distintas a la versión de escritorio.
- El backend web se ejecuta con `python web_entry.py` y también llama `desktop_entry.prepare()`.

## Backend obligatorio

La URL pública del backend debe configurarse en GitHub como variable de repositorio `INFORMTIT_API_BASE`, sin `/` final y usando HTTPS.

Antes de publicar, el workflow comprueba automáticamente:

1. que `INFORMTIT_API_BASE` exista y sea HTTPS;
2. que `/api/health` responda como Informtit completo y exponga la capacidad `schedules`;
3. que `/api/runtime-info` tenga exactamente la misma versión que `package.json`.

Si alguna de estas comprobaciones falla, GitHub Pages no despliega una versión reducida o distinta. El despliegue se detiene hasta que backend y repositorio vuelvan a estar sincronizados.

## Contenedor del backend

El repositorio incluye `render.yaml`. El servicio ejecuta `web_entry.py`, permite como origen CORS `https://jeffer91.github.io` y utiliza almacenamiento persistente para SQLite, cargas y exportaciones.

El backend debe desplegar la misma rama `main` antes de que GitHub Pages pueda publicar la nueva versión.
