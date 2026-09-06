# Informtit

Aplicación para crear y administrar informes finales del proceso de titulación en modalidad presencial y en línea.

## Flujo principal

1. Importar el reporte general antiguo `.xls` generado por el sistema. El archivo es una tabla HTML compatible con Excel.
2. Informtit identifica estudiantes, carreras, modalidad, sede y jornada.
3. Se organiza un informe global por período con sus salidas institucionales.
4. Dentro de cada módulo se cargan y concilian calificaciones y evidencias.
5. La aplicación conserva la nómina oficial y relaciona la información académica con cada estudiante.
6. Se generan análisis, tablas, gráficos y documentos PDF institucionales.

## Responsables institucionales

Los campos Elaborado por, Revisado por y Aprobado por se registran una sola vez en **Configuración institucional** y se aplican a los informes.

## Una sola aplicación: npm start y GitHub Pages

El frontend web se publica en `https://jeffer91.github.io/Informtit/`.

`npm start` y GitHub Pages usan los mismos archivos de `static/` y la misma preparación Python de `desktop_entry.prepare()`.

- En escritorio, Electron inicia el backend local.
- En GitHub Pages, `web-runtime.js` dirige las llamadas al backend web configurado en `INFORMTIT_API_BASE`.
- Pages no usa una implementación paralela de informes en `localStorage` ni reemplaza el backend con runtimes Firebase distintos.
- Antes de desplegar Pages, GitHub Actions comprueba que el backend esté disponible y que `/api/runtime-info` reporte exactamente la misma versión que `package.json`.

El repositorio incluye `render.yaml`, preparado para desplegar `web_entry.py` como servicio Docker con almacenamiento persistente para SQLite, cargas y exportaciones.

La variable de repositorio `INFORMTIT_API_BASE` es obligatoria y debe contener la URL HTTPS pública del backend sin `/` final.

## Requisitos de desarrollo

- Node.js y npm.
- Python 3.11 o superior.

## Instalación en PowerShell

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\configurar.ps1
npm start
```

La aplicación de escritorio guarda su base persistente en el directorio de datos de Informtit; el backend web utiliza el almacenamiento persistente configurado en el servicio de despliegue.
