# Informtit

Aplicación web local para crear informes finales del proceso de titulación en modalidad presencial y en línea.

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

- Python 3.11 o superior.
- Dependencias de `requirements.txt`.

## Instalación

```bash
python -m pip install -r requirements.txt
python app.py
```

En Windows también puede ejecutar `iniciar.bat`.

La aplicación abre en:

```text
http://127.0.0.1:8765
```

## Base local

La base se crea automáticamente en:

```text
data/informtit.db
```

Los archivos cargados se guardan en `uploads/` y los documentos generados en `exports/`.

## Inteligencias artificiales

Abra **Inteligencias artificiales** y configure en cada proveedor:

- Endpoint.
- Modelo disponible.
- Clave API.
- Prioridad.
- Estado habilitado.

Las claves se almacenan en la base SQLite del equipo. No suba `data/informtit.db` a GitHub ni comparta esa base.

## Copias de seguridad

Para respaldar todo el trabajo, copie estas carpetas:

- `data/`
- `uploads/`
- `exports/`

## Pruebas

```bash
python -m unittest discover -s tests
```
