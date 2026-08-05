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
