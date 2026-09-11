# Informtit

Informtit funciona como aplicación web publicada en **GitHub Pages**.

## Arquitectura vigente

- **GitHub Pages**: interfaz oficial de Informtit.
- **Google Sheets + Google Apps Script**: fuente institucional compartida para períodos académicos y datos operativos de estudiantes, matrículas, requisitos, núcleos, Examen Complexivo y Trabajo de Titulación.
- **Almacenamiento del navegador**: se utiliza únicamente como compatibilidad temporal para configuración local y datos que todavía no tienen persistencia compartida en Apps Script.
- **GitHub Actions**: valida JavaScript, prepara el bundle específico para Pages y despliega automáticamente desde `main`.

## Aplicación

https://jeffer91.github.io/Informtit/

## Estructura del repositorio

- `static/`: aplicación web y módulos de compatibilidad/runtime.
- `.github/workflows/pages.yml`: construcción y despliegue de la versión oficial de GitHub Pages.

La versión oficial funcional y visual es la publicada en GitHub Pages. Los módulos heredados con nombres Firebase, desktop, fix/hotfix o versiones anteriores pueden permanecer temporalmente en el repositorio durante la migración, pero no representan por sí mismos la arquitectura vigente de producción.

## Regla de contexto

El **período activo** es el contexto global de la aplicación. Los documentos y datos del usuario deben operar siempre dentro de un `periodId` canónico con formato `AAAA-MM_AAAA-MM`.
