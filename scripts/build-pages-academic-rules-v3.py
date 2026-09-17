from pathlib import Path
import sys

source_path = Path(__file__).with_name('build-pages-academic-rules-v2.py')
source = source_path.read_text(encoding='utf-8')
old = '''# La llamada de Núcleos puede variar ligeramente; insertar incidencias junto al marcador estable.\nif "calculated_nuclei:" not in text:\n    marker = "four_nuclei_validated:true"\n    if marker not in text:\n        raise SystemExit('results-import-ui.js: no se encontró detalle de importación de Núcleos')\n    text = text.replace(marker, "four_nuclei_validated:true, calculated_nuclei:valid.filter(item=>item.calculated).length, incidents:rows.filter(item=>item.errors.length).map(item=>({cedula:item.cedula,fila:item.index,motivos:item.errors})).slice(0,500)", 1)\n'''
new = '''# Persistir incidencias y cantidad de notas reconstruidas en el lote de Núcleos.\nif "calculated_nuclei:" not in text:\n    old_call = "await logImport(db, periodId, 'NUCLEI_RESULTS', stateImport.nuclei.file?.name, rows.length, valid.length, rows.length-valid.length);"\n    new_call = "await logImport(db, periodId, 'NUCLEI_RESULTS', stateImport.nuclei.file?.name, rows.length, valid.length, rows.length-valid.length, { calculated_nuclei:valid.filter(item=>item.calculated).length, incidents:rows.filter(item=>item.errors.length).map(item=>({cedula:item.cedula,fila:item.index,motivos:item.errors})).slice(0,500) });"\n    if old_call not in text:\n        raise SystemExit('results-import-ui.js: no se encontró logImport de Núcleos')\n    text = text.replace(old_call, new_call, 1)\n'''
if old not in source:
    raise SystemExit('No se encontró el bloque v2 a corregir')
source = source.replace(old, new, 1)
namespace = {'__file__': str(source_path), '__name__': '__main__'}
exec(compile(source, str(source_path), 'exec'), namespace, namespace)
