# Informtit

Aplicación de escritorio Electron para crear informes finales del proceso de titulación en modalidad presencial y en línea.

## Flujo principal

1. Importar el reporte general antiguo `.xls` generado por el sistema. El archivo es una tabla HTML compatible con Excel.
2. Informtit identifica estudiantes, carreras, modalidad, sede y jornada.
3. Se crean automáticamente un informe presencial y otro en línea.
4. Dentro de cada carrera se pegan las calificaciones copiadas desde Moodle.
5. La aplicación conserva la nómina importada y relaciona las notas por correo institucional o nombre.
6. Se generan análisis, tablas, gráficos, Word y PDF.

## Responsables institucionales

Los campos Elaborado por, Revisado por y Aprobado por se registran una sola vez en **Configuración institucional** y se aplican a todos los informes.

## GitHub Pages + backend web

El frontend web se publica en `https://jeffer91.github.io/Informtit/`.

Para conservar las mismas funciones de la aplicación (API Python, SQLite, importaciones, PDFs y archivos), el backend debe ejecutarse en un servicio web. El repositorio incluye `render.yaml`, preparado para desplegar `web_entry.py` como servicio Docker con almacenamiento persistente para la base SQLite, cargas y exportaciones.

Después de crear el servicio en Render, copie su URL `https://...onrender.com` y abra una sola vez:

`https://jeffer91.github.io/Informtit/?api=https://...onrender.com`

Informtit guardará esa dirección en el navegador y las llamadas `/api`, `/uploads` y `/exports` pasarán al backend.

## Requisitos de desarrollo

- Node.js y npm.
- Python 3.11 o superior.

## Instalación en PowerShell

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\configurar.ps1
npm start
```

La base SQLite se crea localmente en `data/informtit.db`.
