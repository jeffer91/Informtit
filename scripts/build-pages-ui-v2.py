from pathlib import Path
import subprocess
import sys

site = Path(sys.argv[1] if len(sys.argv) > 1 else '_site')

# Reglas académicas definitivas: período/sedes normalizados, control 60/40,
# supletorio independiente, prioridad TT, incidencias y reconstrucción de Núcleo.
subprocess.run([sys.executable, str(Path(__file__).with_name('build-pages-academic-rules-v3.py')), str(site)], check=True)

index = site / 'index.html'
text = index.read_text(encoding='utf-8')
text = text.replace('results-import-ui.js?v=4.1', 'results-import-ui.js?v=4.2')


def insert_after(marker: str, addition: str) -> None:
    global text
    if addition in text:
        return
    if marker not in text:
        raise SystemExit(f'No se encontró el marcador de inserción: {marker}')
    text = text.replace(marker, marker + '\n  ' + addition, 1)


insert_after(
    '<script src="./results-import-ui.js?v=4.2"></script>',
    '<script src="./three-files-upload-ui.js?v=1.1"></script>'
)
insert_after(
    '<script src="./report-health-sheets-ui.js?v=4.0"></script>',
    '<script src="./period-status-colors-ui.js?v=1.0"></script>'
)

for filename, marker in [
    ('three-files-upload-ui.js', 'THREE_SISACAD_FILES_AUTODETECT_V1_1'),
    ('period-status-colors-ui.js', 'PERIOD_STATUS_COLORS_V1'),
]:
    path = site / filename
    if not path.exists():
        raise SystemExit(f'Falta {filename} en el bundle')
    if marker not in path.read_text(encoding='utf-8'):
        raise SystemExit(f'Falta marcador {marker} en {filename}')

index.write_text(text, encoding='utf-8')
print('UI v2 build corrections applied.')
