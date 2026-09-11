# Informtit

Informtit funciona como aplicación web publicada en **GitHub Pages**.

## Arquitectura vigente

- **GitHub Pages**: interfaz oficial de Informtit.
- **Google Sheets + Google Apps Script**: fuente institucional compartida para períodos académicos y datos operativos de estudiantes, matrículas, requisitos, núcleos, Examen Complexivo y Trabajo de Titulación.
- **Servicios de navegador para Pages**: resuelven salud del runtime, auditoría previa, generación/descarga de PDF e imágenes sin depender de un backend local.
- **Almacenamiento del navegador**: se utiliza como compatibilidad para configuración local, historial PDF e información que todavía no tiene persistencia compartida en Apps Script.
- **GitHub Actions**: valida JavaScript, ejecuta una prueba funcional del runtime de Pages, prepara el bundle específico y despliega automáticamente desde `main`.

## Aplicación

https://jeffer91.github.io/Informtit/

## Estructura del repositorio

- `static/`: aplicación web y runtimes de producción/compatibilidad.
- `scripts/pages-smoke.mjs`: prueba funcional mínima de salud, auditoría, imágenes y PDF para GitHub Pages.
- `.github/workflows/pages.yml`: construcción, validación y despliegue de la versión oficial de GitHub Pages.

La versión oficial funcional y visual es la publicada en GitHub Pages. Los módulos heredados con nombres Firebase, desktop, fix/hotfix o versiones anteriores pueden permanecer temporalmente en el repositorio durante la migración, pero no representan por sí mismos la arquitectura vigente de producción.

## Regla de contexto

El **período activo** es el contexto global de la aplicación. Los documentos y datos del usuario deben operar siempre dentro de un `periodId` canónico con formato `AAAA-MM_AAAA-MM`.
