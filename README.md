# Informtit

Aplicación de escritorio en **Electron** para crear informes finales del proceso de titulación en modalidad presencial y en línea.

La interfaz se abre en una ventana de Electron. El procesamiento local, la base SQLite, el análisis de notas y la generación de documentos se ejecutan mediante el backend local de Python incluido en el proyecto.

## Funciones incluidas

- Proyectos de informe guardados en SQLite local.
- Registro de periodo, modalidad, código, versión y responsables.
- Catálogo de carreras por informe.
- Pegado directo de calificaciones copiadas desde Moodle.
- Limpieza automática de encabezados, `Ocultar`, iniciales y guiones.
- Separación de resultados ordinarios, supletorios y consolidados.
- Ponderación: teórico 40 % y práctico 60 %.
- En supletorio se reemplaza únicamente el componente rendido.
- Configuración local de Gemini, Groq y OpenRouter.
- Generación de texto antes y después de cada tabla.
- Carga de imágenes e infografías.
- Exportación a Word y PDF.

## Requisitos

- Git.
- Visual Studio Code.
- Node.js LTS con npm.
- Python 3.11 o superior.

## Descargar en el escritorio con PowerShell

Abra Visual Studio Code y luego **Terminal → New Terminal**. En PowerShell ejecute:

```powershell
cd $HOME\Desktop
git clone https://github.com/jeffer91/Informtit.git
cd Informtit
code .
```

## Configuración automática

En la terminal integrada de Visual Studio Code:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\configurar.ps1
```

El script instala las dependencias de Electron, crea `.venv` e instala las dependencias de Python.

## Abrir en modo Electron

```powershell
$env:INFORMTIT_PYTHON = ".venv\Scripts\python.exe"
npm start
```

No ejecute `python app.py` para el uso normal de escritorio. Ese comando abre únicamente el servidor local. El comando `npm start` abre la aplicación en una ventana de Electron.

## Base local

La base se crea localmente. Durante el desarrollo se encuentra en:

```text
data/informtit.db
```

Los archivos cargados se guardan en `uploads/` y los documentos generados en `exports/`.

## Crear instalador de Windows

```powershell
$env:INFORMTIT_PYTHON = ".venv\Scripts\python.exe"
npm run make
```

Electron Forge generará los archivos en la carpeta `out/`.

> Estado actual del instalador: la aplicación funciona en Electron, pero el equipo de destino todavía debe tener Python y las dependencias de `requirements.txt`. Para obtener un instalador totalmente independiente será necesario empaquetar también el runtime de Python o migrar el backend a Node.js.

## Inteligencias artificiales

Abra **Inteligencias artificiales** y configure en cada proveedor:

- Endpoint.
- Modelo disponible.
- Clave API.
- Prioridad.
- Estado habilitado.

Las claves se almacenan en la base SQLite local. No suba la base de datos a GitHub.

## Pruebas

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```
