from pathlib import Path
import sys

site = Path(sys.argv[1] if len(sys.argv) > 1 else '_site')
path = site / 'results-import-ui.js'
text = path.read_text(encoding='utf-8')


def must_replace(old, new, label):
    global text
    if new in text:
        return
    if old not in text:
        raise SystemExit(f'results-import-ui.js: no se encontró {label}')
    text = text.replace(old, new, 1)

must_replace("const VERSION = '4.1.0';", "const VERSION = '4.2.0';", 'versión 4.1')
must_replace(
"""  function periodKey(value = '') {
    return fold(value).replace(/\\bDE\\b/g, ' ').replace(/\\bA\\b/g, ' ').replace(/\\s+/g, ' ').trim();
  }
""",
"""  function periodKey(value = '') {
    return fold(value).replace(/[–—_-]+/g, ' ').replace(/\\bDE\\b/g, ' ').replace(/\\bA\\b/g, ' ').replace(/\\s+/g, ' ').trim();
  }

  function normalizeCampus(value = '') {
    return fold(value).replace(/\\b(SEDE|CAMPUS)\\b/g, ' ').replace(/\\s+/g, ' ').trim();
  }

  function validGrade(value) {
    return value === null || (Number.isFinite(Number(value)) && Number(value) >= 0 && Number(value) <= 10);
  }

  function round2(value) {
    return Number((Number(value) + Number.EPSILON).toFixed(2));
  }
""",
'normalización de período')

start = text.index('  function reconcileComplexive(rawRows, master) {')
end = text.index('\n  function reconcileNuclei(rawRows, master) {', start)
text = text[:start] + r'''  function reconcileComplexive(rawRows, master) {
    const activeLabel = periodKey(activePeriodLabel());
    const duplicateIds = new Set();
    const seen = new Set();
    const parsed = rawRows.map((raw, index) => {
      const row = normalizedRow(raw);
      const cedula = digits(pick(row, 'identificacion_estudiante'));
      if (cedula && seen.has(cedula)) duplicateIds.add(cedula);
      if (cedula) seen.add(cedula);
      const matched = cedula ? master.masterByCedula.get(cedula) : null;
      const studentId = Number(matched?.student?.id || 0);
      const sourcePeriod = clean(pick(row, 'periodo_academico'));
      const sourceName = clean(pick(row, 'nombre_estudiante'));
      const sourceCareer = clean(pick(row, 'nombre_carrera'));
      const sourceCampus = clean(pick(row, 'sede'));
      const sourceModality = clean(pick(row, 'modalidad'));
      const teorico = num(pick(row, 'notaTeorico'));
      const practico = num(pick(row, 'notaPractico'));
      const acumulado = num(pick(row, 'notaPromedioAcumulado'));
      const supletorio = num(pick(row, 'notaSupletorio'));
      const calculado = teorico !== null && practico !== null ? round2(practico * 0.60 + teorico * 0.40) : null;
      const final = supletorio !== null ? supletorio : (acumulado !== null ? acumulado : calculado);
      const estadoFinal = final === null ? 'SIN_NOTA' : final >= 7 ? 'APROBADO' : 'REPROBADO';
      const warnings = [];
      const errors = [];
      if (!cedula || cedula.length !== 10) errors.push('Cédula inválida');
      if (!matched) errors.push('No existe en la población maestra de requisitos');
      if (studentId && master.thesisIds.has(studentId)) errors.push('Trabajo de Titulación tiene prioridad; registro conservado solo como incidencia histórica');
      if (sourcePeriod && activeLabel && periodKey(sourcePeriod) !== activeLabel) errors.push(`Período del archivo: ${sourcePeriod}`);
      [['Teórico',teorico],['Práctico',practico],['Promedio acumulado',acumulado],['Supletorio',supletorio]].forEach(([label,value]) => {
        if (!validGrade(value)) errors.push(`${label} fuera de rango 0-10`);
      });
      if ((teorico === null || practico === null) && acumulado !== null) warnings.push('Nota oficial disponible · componentes Teórico/Práctico incompletos');
      if (teorico !== null && practico !== null && acumulado !== null && Math.abs(calculado - acumulado) > 0.01) warnings.push(`Promedio oficial ${acumulado} difiere del control 60/40 (${calculado})`);
      if (teorico === null && practico === null && acumulado === null && supletorio === null && !errors.some(e => e.includes('Trabajo de Titulación'))) errors.push('Sin nota oficial ni componentes para calcular Examen Complexivo');
      if (matched) {
        const w1 = compareWarning('Nombre', sourceName, matched.student.full_name);
        const w2 = compareWarning('Carrera', canonicalCareer(sourceCareer), canonicalCareer(matched.enrollment.career_name));
        const w3 = compareWarning('Sede', normalizeCampus(sourceCampus), normalizeCampus(matched.enrollment.campus));
        [w1,w2,w3].filter(Boolean).forEach(item => warnings.push(item));
      }
      return { index:index+2, cedula, studentId, nombre:sourceName, carrera:sourceCareer,
        modalidad:normalizeModality(sourceModality, matched?.enrollment?.career_code || ''), sede:sourceCampus,
        periodo:sourcePeriod, tipo:clean(pick(row, 'tipo_titulacion')), teorico, practico, acumulado, supletorio,
        calculado, final, estadoFinal, matched, warnings, errors, raw };
    });
    parsed.forEach(item => { if (duplicateIds.has(item.cedula)) item.errors.push('Cédula duplicada dentro del archivo'); });
    return parsed;
  }
''' + text[end:]

start = text.index('  function reconcileNuclei(rawRows, master) {')
end = text.index('\n  function stats(rows) {', start)
text = text[:start] + r'''  function reconcileNuclei(rawRows, master) {
    const seen = new Set();
    const duplicateKeys = new Set();
    const catalog = buildNucleusCatalog(rawRows);
    const parsed = rawRows.map((raw, index) => {
      const row = normalizedRow(raw);
      const cedula = digits(pick(row, 'numeroIdentificacion', 'identificacion_estudiante'));
      const nucleus = nucleusNumber(row, catalog.map);
      const uniqueKey = `${cedula}|${nucleus}`;
      if (cedula && nucleus && seen.has(uniqueKey)) duplicateKeys.add(uniqueKey);
      if (cedula && nucleus) seen.add(uniqueKey);
      const matched = cedula ? master.masterByCedula.get(cedula) : null;
      const studentId = Number(matched?.student?.id || 0);
      const sourceName = clean(pick(row, 'nombre_estudiante'));
      const sourceCareer = clean(pick(row, 'nombre_carrera'));
      const sourceCampus = clean(pick(row, 'sede'));
      const sourceModality = clean(pick(row, 'modalidad'));
      const nota = num(pick(row, 'nota_nucleo'));
      const resultado = clean(pick(row, 'resultado_aprobacion'));
      const warnings = [];
      const errors = [];
      if (!cedula || cedula.length !== 10) errors.push('Cédula inválida');
      if (!nucleus) errors.push('No se pudo identificar Núcleo 1, 2, 3 o 4 a partir de la materia/código de la carrera');
      if (catalog.errors.length) errors.push(...catalog.errors);
      if (!matched) errors.push('No existe en la población maestra de requisitos');
      if (studentId && master.thesisIds.has(studentId)) errors.push('Trabajo de Titulación tiene prioridad; registro conservado solo como incidencia histórica');
      if (!validGrade(nota)) errors.push('Nota de Núcleo fuera de rango 0-10');
      if (matched) {
        const w1 = compareWarning('Nombre', sourceName, matched.student.full_name);
        const w2 = compareWarning('Carrera', canonicalCareer(sourceCareer), canonicalCareer(matched.enrollment.career_name));
        const w3 = compareWarning('Sede', normalizeCampus(sourceCampus), normalizeCampus(matched.enrollment.campus));
        [w1,w2,w3].filter(Boolean).forEach(item => warnings.push(item));
      }
      return { index:index+2, cedula, studentId, nucleus, nombre:sourceName, carrera:sourceCareer,
        modalidad:normalizeModality(sourceModality, clean(pick(row, 'codigo_carrera'))), sede:sourceCampus,
        codigoCarrera:clean(pick(row, 'codigo_carrera')), codigoMateria:clean(pick(row, 'cod_materia')),
        materia:clean(pick(row, 'materia')), docente:clean(pick(row, 'Pro_nombre')), nota, resultado,
        calculated:false, matched, warnings, errors, raw };
    });
    const byStudent = new Map();
    parsed.forEach(item => {
      if (duplicateKeys.has(`${item.cedula}|${item.nucleus}`)) item.errors.push(`Duplicado Núcleo ${item.nucleus}`);
      if (!item.cedula) return;
      if (!byStudent.has(item.cedula)) byStudent.set(item.cedula, []);
      byStudent.get(item.cedula).push(item);
    });
    byStudent.forEach(items => {
      const unique = new Set(items.map(item => item.nucleus).filter(Boolean));
      if (items.length !== 4 || unique.size !== 4) {
        items.forEach(item => item.errors.push(`La cédula debe tener exactamente 4 Núcleos distintos; se detectaron ${unique.size} en ${items.length} filas`));
        return;
      }
      const studentId = Number(items[0]?.studentId || 0);
      if (studentId && master.thesisIds.has(studentId)) return;
      const candidates = items.filter(item => !item.resultado || item.nota === null || (item.nota === 0 && !fold(item.resultado).includes('REPROB')));
      if (!candidates.length) return;
      if (!(studentId && master.complexiveIds.has(studentId))) {
        candidates.forEach(item => item.errors.push('Núcleo incompleto y sin evidencia de Examen Complexivo para reconstruir la nota'));
        return;
      }
      if (candidates.length !== 1) {
        candidates.forEach(item => item.errors.push('No se puede reconstruir: existe más de un Núcleo incompleto'));
        return;
      }
      const target = candidates[0];
      const otherGrades = items.filter(item => item !== target && item.nota !== null && item.nota > 0 && item.nota <= 10).map(item => item.nota);
      if (otherGrades.length !== 3) {
        target.errors.push('No se puede reconstruir la nota: no existen 3 Núcleos válidos de referencia');
        return;
      }
      target.nota = round2(otherGrades.reduce((sum, value) => sum + value, 0) / 3);
      target.resultado = 'Aprobado';
      target.calculated = true;
      target.warnings.push(`Nota calculada con promedio de los otros 3 Núcleos: ${target.nota}`);
    });
    return parsed;
  }
''' + text[end:]

must_replace('          final_grade:null,', '          final_grade:item.final,', 'final_grade Complexivo')
must_replace("          final_status:[item.teorico,item.practico,item.acumulado,item.supletorio].some(value => value !== null) ? 'REGISTRADO' : 'SIN_NOTA',", "          final_status:item.estadoFinal,", 'estado final Complexivo')
must_replace('            notaPromedioAcumulado:item.acumulado,\n            modalidad_normalizada:item.modalidad,', '            notaPromedioAcumulado:item.acumulado,\n            notaControl60_40:item.calculado,\n            notaFinalAplicada:item.final,\n            reglaFinal:item.supletorio !== null ? \'SUPLETORIO\' : (item.acumulado !== null ? \'PROMEDIO_OFICIAL\' : \'CALCULO_60_40\'),\n            modalidad_normalizada:item.modalidad,', 'auditoría Complexivo')
must_replace('            docente:item.docente,\n            modalidad_normalizada:item.modalidad,', '            docente:item.docente,\n            nota_calculada:Boolean(item.calculated),\n            modalidad_normalizada:item.modalidad,', 'auditoría Núcleos')
must_replace('{ accumulated_grade_structured:true }', "{ accumulated_grade_structured:true, incidents:rows.filter(item=>item.errors.length).map(item=>({cedula:item.cedula,fila:item.index,motivos:item.errors})).slice(0,500) }", 'incidencias Complexivo')

# La llamada de Núcleos puede variar ligeramente; insertar incidencias junto al marcador estable.
if "calculated_nuclei:" not in text:
    marker = "four_nuclei_validated:true"
    if marker not in text:
        raise SystemExit('results-import-ui.js: no se encontró detalle de importación de Núcleos')
    text = text.replace(marker, "four_nuclei_validated:true, calculated_nuclei:valid.filter(item=>item.calculated).length, incidents:rows.filter(item=>item.errors.length).map(item=>({cedula:item.cedula,fila:item.index,motivos:item.errors})).slice(0,500)", 1)

must_replace('    buildNucleusCatalog,\n    nucleusNumber,\n  });', '    buildNucleusCatalog,\n    nucleusNumber,\n    periodKey,\n    normalizeCampus,\n    validGrade,\n  });', 'helpers públicos')

path.write_text(text, encoding='utf-8')
print('Academic rules v4.2 applied.')
