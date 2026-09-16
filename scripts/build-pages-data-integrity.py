from pathlib import Path
import sys

site = Path(sys.argv[1] if len(sys.argv) > 1 else '_site')


def patch_file(name, replacements, markers=()):
    path = site / name
    text = path.read_text(encoding='utf-8')
    for old, new in replacements:
        if new in text:
            continue
        if old not in text:
            raise SystemExit(f'{name}: no se encontró bloque esperado para la corrección')
        text = text.replace(old, new, 1)
    for marker in markers:
        if marker not in text:
            raise SystemExit(f'{name}: falta marcador final {marker!r}')
    path.write_text(text, encoding='utf-8')

# Resultados SISACAD: Núcleos por catálogo carrera/materia, cédula maestra,
# TT protegido y columnas estructuradas de Complexivo/Núcleos.
patch_file('results-import-ui.js', [
    ("const VERSION = '4.0.0';", "const VERSION = '4.1.0';"),
    ("""  function nucleusNumber(row) {
    const matter = clean(pick(row, 'materia'));
    const code = clean(pick(row, 'cod_materia', 'codigo_materia'));
    const match = fold(matter).match(/NUCLEO\\s*([1-4])/);
    if (match) return Number(match[1]);
    const codeMatch = code.match(/70([1-4])(?:\\D|$)/);
    return codeMatch ? Number(codeMatch[1]) : 0;
  }
""", """  function explicitNucleusNumber(row) {
    const direct = Number(pick(row, 'nucleo', 'numero_nucleo', 'nucleus_number'));
    if (Number.isInteger(direct) && direct >= 1 && direct <= 4) return direct;
    const matter = fold(pick(row, 'materia'));
    const match = matter.match(/NUCLEO\\s*([1-4])(?:\\D|$)/);
    return match ? Number(match[1]) : 0;
  }

  function buildNucleusCatalog(rawRows = []) {
    const coursesByCareer = new Map();
    rawRows.forEach((raw, index) => {
      const row = normalizedRow(raw);
      const careerCode = clean(pick(row, 'codigo_carrera'));
      const courseCode = clean(pick(row, 'cod_materia', 'codigo_materia'));
      if (!careerCode || !courseCode) return;
      if (!coursesByCareer.has(careerCode)) coursesByCareer.set(careerCode, new Map());
      const courses = coursesByCareer.get(careerCode);
      if (!courses.has(courseCode)) courses.set(courseCode, { courseCode, explicit: explicitNucleusNumber(row), firstIndex:index });
      else if (!courses.get(courseCode).explicit) courses.get(courseCode).explicit = explicitNucleusNumber(row);
    });
    const map = new Map();
    const errors = [];
    coursesByCareer.forEach((courseMap, careerCode) => {
      const courses = [...courseMap.values()].sort((a,b) =>
        a.courseCode.localeCompare(b.courseCode, 'es', { numeric:true, sensitivity:'base' }) || a.firstIndex - b.firstIndex
      );
      if (courses.length !== 4) {
        errors.push(`${careerCode}: se esperaban 4 materias de Núcleos y se detectaron ${courses.length}.`);
        return;
      }
      const explicitValues = courses.map(item => item.explicit).filter(value => value >= 1 && value <= 4);
      const used = new Set(explicitValues);
      if (used.size !== explicitValues.length) {
        errors.push(`${careerCode}: hay números de Núcleo repetidos en los nombres de materia.`);
        return;
      }
      const available = [1,2,3,4].filter(value => !used.has(value));
      let cursor = 0;
      courses.forEach(item => {
        const nucleus = item.explicit || available[cursor++];
        map.set(`${careerCode}|${item.courseCode}`, nucleus || 0);
      });
    });
    return { map, errors };
  }

  function nucleusNumber(row, catalog = null) {
    const explicit = explicitNucleusNumber(row);
    if (explicit) return explicit;
    const careerCode = clean(pick(row, 'codigo_carrera'));
    const courseCode = clean(pick(row, 'cod_materia', 'codigo_materia'));
    return Number(catalog?.get(`${careerCode}|${courseCode}`) || 0);
  }
"""),
    ("""      if (!matched) errors.push('No existe en la población maestra de requisitos');
      if (studentId && master.thesisIds.has(studentId)) errors.push('Protegido: pertenece a Trabajo de Titulación');
      if (sourcePeriod && activeLabel && periodKey(sourcePeriod) !== activeLabel) errors.push(`Período del archivo: ${sourcePeriod}`);
""", """      if (!matched) errors.push('No existe en la población maestra de requisitos');
      if (studentId && master.thesisIds.has(studentId)) errors.push('Protegido: pertenece a Trabajo de Titulación');
      if (studentId && !master.thesisIds.has(studentId) && num(pick(row, 'notaTeorico')) === null && num(pick(row, 'notaPractico')) === null && !master.nucleiIds.has(studentId)) errors.push('Sin evidencia suficiente de Examen Complexivo: Teórico y Práctico están vacíos y no existen Núcleos');
      if (sourcePeriod && activeLabel && periodKey(sourcePeriod) !== activeLabel) errors.push(`Período del archivo: ${sourcePeriod}`);
"""),
    ("""  function reconcileNuclei(rawRows, master) {
    const seen = new Set();
    const duplicateKeys = new Set();
    const parsed = rawRows.map((raw, index) => {
      const row = normalizedRow(raw);
      const cedula = digits(pick(row, 'numeroIdentificacion', 'identificacion_estudiante'));
      const nucleus = nucleusNumber(row);
""", """  function reconcileNuclei(rawRows, master) {
    const seen = new Set();
    const duplicateKeys = new Set();
    const catalog = buildNucleusCatalog(rawRows);
    const parsed = rawRows.map((raw, index) => {
      const row = normalizedRow(raw);
      const cedula = digits(pick(row, 'numeroIdentificacion', 'identificacion_estudiante'));
      const nucleus = nucleusNumber(row, catalog.map);
"""),
    ("""      if (!cedula || cedula.length !== 10) errors.push('Cédula inválida');
      if (!nucleus) errors.push('No se pudo identificar Núcleo 1, 2, 3 o 4');
      if (!matched) errors.push('No existe en la población maestra de requisitos');
""", """      if (!cedula || cedula.length !== 10) errors.push('Cédula inválida');
      if (!nucleus) errors.push('No se pudo identificar Núcleo 1, 2, 3 o 4 a partir de la materia/código de la carrera');
      if (catalog.errors.length) errors.push(...catalog.errors);
      if (!matched) errors.push('No existe en la población maestra de requisitos');
"""),
    ("""    parsed.forEach(item => {
      if (duplicateKeys.has(`${item.cedula}|${item.nucleus}`)) item.errors.push(`Duplicado Núcleo ${item.nucleus}`);
    });
    return parsed;
""", """    const byStudent = new Map();
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
      }
    });
    return parsed;
"""),
    ("""  async function protectAndSetComplexiveRoute(db, periodId, ids) {
    if (!ids.length) return;
    const result = await db.from('enrollments')
      .update({ titulation_route:'COMPLEXIVO', updated_at:now() })
      .eq('period_id', periodId)
      .in('student_id', ids);
    if (result?.error) throw result.error;
  }
""", """  async function protectAndSetComplexiveRoute(db, periodId, ids) {
    if (!ids.length) return;
    const thesisResult = await db.from('thesis_results').select('student_id').eq('period_id', periodId).in('student_id', ids);
    const thesisIds = new Set(rowsOf(thesisResult).map(row => Number(row.student_id)));
    const eligible = [...new Set(ids.map(Number).filter(id => Number.isFinite(id) && !thesisIds.has(id)))];
    if (!eligible.length) return;
    const result = await db.from('enrollments')
      .update({ titulation_route:'COMPLEXIVO', updated_at:now() })
      .eq('period_id', periodId)
      .in('student_id', eligible);
    if (result?.error) throw result.error;
  }
"""),
    ("""          theoretical_grade:item.teorico,
          practical_grade:item.practico,
          supplementary_theoretical:item.supletorio,
          supplementary_practical:null,
          final_grade:null,
""", """          theoretical_grade:item.teorico,
          practical_grade:item.practico,
          accumulated_grade:item.acumulado,
          supplementary_theoretical:item.supletorio,
          supplementary_practical:null,
          final_grade:null,
          source_modality:item.modalidad,
          source_campus:item.sede,
          source_file:stateImport.complexive.file?.name || '',
"""),
    ("{ accumulated_grade_kept_in_raw_data:true }", "{ accumulated_grade_structured:true }"),
    ("""          nucleus_number:item.nucleus,
          career_name:item.matched?.enrollment?.career_name || canonicalCareer(item.carrera),
          course_name:item.materia,
          grade:item.nota,
""", """          nucleus_number:item.nucleus,
          career_code:item.codigoCarrera,
          career_name:item.matched?.enrollment?.career_name || canonicalCareer(item.carrera),
          course_code:item.codigoMateria,
          course_name:item.materia,
          teacher_name:item.docente,
          source_modality:item.modalidad,
          source_campus:item.sede,
          source_file:stateImport.nuclei.file?.name || '',
          grade:item.nota,
"""),
    ("""    reconcileNuclei,
    normalizeModality,
  });
""", """    reconcileNuclei,
    normalizeModality,
    buildNucleusCatalog,
    nucleusNumber,
  });
"""),
], markers=("const VERSION = '4.1.0'", 'buildNucleusCatalog', 'accumulated_grade:item.acumulado'))

# Capa Neon: resultados no crean estudiantes, TT tiene prioridad, columnas migradas
# y la población maestra nueva marca ausentes como inactivos sin borrarlos.
patch_file('neon-data-runtime.js', [
    ("  const digits = value => clean(value).replace(/\\D/g, '');\n", "  const digits = value => clean(value).replace(/\\D/g, '');\n  const fold = value => clean(value).normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').toUpperCase();\n"),
    ("""    return { ok:true, matriculas:rows.map(row => { const s=map.get(Number(row.student_id))||{}; return { cedula:s.identification||'',identificacion:s.identification||'',nombre:s.full_name||'',codigoCarrera:row.career_code,carrera:row.career_name,nombreCarrera:row.career_name,modalidad:row.modality,sede:row.campus,jornada:row.shift,retirado:false,route:row.titulation_route||'UNDEFINED',source:'NEON' }; }) };
""", """    return { ok:true, matriculas:rows.map(row => { const s=map.get(Number(row.student_id))||{}; const academicStatus=fold(row.academic_status||'ACTIVO'); return { cedula:s.identification||'',identificacion:s.identification||'',nombre:s.full_name||'',codigoCarrera:row.career_code,carrera:row.career_name,nombreCarrera:row.career_name,modalidad:row.modality,sede:row.campus,jornada:row.shift,academicStatus,retirado:academicStatus!=='ACTIVO',route:row.titulation_route||'UNDEFINED',source:'NEON' }; }) };
"""),
    ("return{cedula:s.identification||'',nombre:s.full_name||'',carrera:row.career_name,nucleo:row.nucleus_number,curso:row.course_name,notaFinal:row.grade,estado:row.final_status,source:'NEON'};", "return{cedula:s.identification||'',nombre:s.full_name||'',codigoCarrera:row.career_code,carrera:row.career_name,nucleo:row.nucleus_number,codigoMateria:row.course_code,curso:row.course_name,docente:row.teacher_name,modalidadOrigen:row.source_modality,sedeOrigen:row.source_campus,archivoOrigen:row.source_file,notaFinal:row.grade,estado:row.final_status,source:'NEON'};"),
    ("return{cedula:s.identification||'',nombre:s.full_name||'',notaTeorico:row.theoretical_grade,notaPractico:row.practical_grade,notaSupletorio:row.supplementary_theoretical??row.supplementary_practical,notaFinal:row.final_grade,estado:row.final_status,source:'NEON'};", "return{cedula:s.identification||'',nombre:s.full_name||'',notaTeorico:row.theoretical_grade,notaPractico:row.practical_grade,notaPromedioAcumulado:row.accumulated_grade,notaSupletorio:row.supplementary_theoretical??row.supplementary_practical,notaFinal:row.final_grade,estado:row.final_status,modalidadOrigen:row.source_modality,sedeOrigen:row.source_campus,archivoOrigen:row.source_file,source:'NEON'};"),
    ("return{cedula:s.identification||'',nombre:s.full_name||'',titulo:row.title,tutor:row.tutor,notaFinal:row.final_grade,estado:row.final_status,source:'NEON'};", "return{cedula:s.identification||'',nombre:s.full_name||'',titulo:row.title,tutor:row.tutor,lector:row.reader,notaTutor:row.tutor_grade,notaLector:row.reader_grade,promedioEscrito:row.written_average,promedioPractica:row.practical_average,promedioDefensa:row.defense_average,defensaOral:row.oral_average,numeroActa:row.act_number,fechaActa:row.act_date,tribunal1:row.vocal_1,tribunal2:row.vocal_2,tribunal3:row.vocal_3,notaFinal:row.final_grade,estado:row.final_status,source:'NEON'};"),
    ("""  async function guardarNucleo(data={}) {
    const client=await requireAccess(); const periodId=clean(data.periodoId),student=await findOrCreateStudent(data); await ensureEnrollment(periodId,student,data,'COMPLEXIVO');
    const payload={period_id:periodId,student_id:Number(student.id),nucleus_number:Number(data.nucleo||data.nucleus_number),career_name:clean(data.carrera),course_name:clean(data.curso||`Núcleo ${data.nucleo||''}`),grade:data.notaFinal===''||data.notaFinal==null?null:Number(data.notaFinal),final_status:clean(data.estado),source:'NEON_IMPORT',raw_data:data,updated_at:now()};
""", """  async function findExistingStudent(data={}) {
    const identification=digits(data.cedula||data.identificacion||data.identification);
    if(!identification) throw new Error('Cédula requerida.');
    const rows=await rowsFor('students','id,identification',q=>q.eq('identification',identification).limit(1));
    if(!rows.length) throw new Error(`La cédula ${identification} no existe en la población maestra.`);
    return rows[0];
  }

  async function assertMasterStudent(periodId, studentId) {
    const rows=await rowsFor('requirements','student_id',q=>q.eq('period_id',periodId).eq('student_id',Number(studentId)).limit(1));
    if(!rows.length) throw new Error('El estudiante no pertenece a la población maestra de requisitos del período.');
  }

  async function assertNotThesis(periodId, studentId) {
    const rows=await rowsFor('thesis_results','student_id',q=>q.eq('period_id',periodId).eq('student_id',Number(studentId)).limit(1));
    if(rows.length) throw new Error('La cédula está protegida como Trabajo de Titulación y no puede registrarse como Complexivo.');
    const enrollment=await rowsFor('enrollments','titulation_route',q=>q.eq('period_id',periodId).eq('student_id',Number(studentId)).limit(1));
    if(fold(enrollment[0]?.titulation_route).includes('TRABAJO')) throw new Error('La ruta Trabajo de Titulación está protegida para esta cédula.');
  }

  async function guardarNucleo(data={}) {
    const client=await requireAccess(); const periodId=clean(data.periodoId),student=await findExistingStudent(data);
    await assertMasterStudent(periodId,student.id); await assertNotThesis(periodId,student.id); await ensureEnrollment(periodId,student,data,'COMPLEXIVO');
    const payload={period_id:periodId,student_id:Number(student.id),nucleus_number:Number(data.nucleo||data.nucleus_number),career_code:clean(data.codigoCarrera||data.career_code),career_name:clean(data.carrera||data.career_name),course_code:clean(data.codigoMateria||data.course_code),course_name:clean(data.curso||data.materia||`Núcleo ${data.nucleo||''}`),teacher_name:clean(data.docente||data.teacher_name),source_modality:clean(data.modalidadOrigen||data.modalidad||data.source_modality),source_campus:clean(data.sedeOrigen||data.sede||data.source_campus),source_file:clean(data.archivoOrigen||data.archivo||data.source_file),grade:data.notaFinal===''||data.notaFinal==null?null:Number(data.notaFinal),final_status:clean(data.estado),source:'NEON_IMPORT',raw_data:data,updated_at:now()};
"""),
    ("""  async function guardarComplexivo(data={}) {
    const client=await requireAccess(); const periodId=clean(data.periodoId),student=await findOrCreateStudent(data); await ensureEnrollment(periodId,student,data,'COMPLEXIVO'); const n=v=>v===''||v==null?null:Number(v);
    const payload={period_id:periodId,student_id:Number(student.id),theoretical_grade:n(data.notaTeorico??data.theoretical_grade),practical_grade:n(data.notaPractico??data.practical_grade),supplementary_theoretical:n(data.notaSupletorio??data.supplementary_theoretical),supplementary_practical:n(data.supplementary_practical),final_grade:n(data.notaFinal??data.final_grade),final_status:clean(data.estado||data.final_status),source:'NEON_IMPORT',raw_data:data,updated_at:now()};
""", """  async function guardarComplexivo(data={}) {
    const client=await requireAccess(); const periodId=clean(data.periodoId),student=await findExistingStudent(data); await assertMasterStudent(periodId,student.id); await assertNotThesis(periodId,student.id); await ensureEnrollment(periodId,student,data,'COMPLEXIVO'); const n=v=>v===''||v==null?null:Number(v);
    const payload={period_id:periodId,student_id:Number(student.id),theoretical_grade:n(data.notaTeorico??data.theoretical_grade),practical_grade:n(data.notaPractico??data.practical_grade),accumulated_grade:n(data.notaPromedioAcumulado??data.accumulated_grade),supplementary_theoretical:n(data.notaSupletorio??data.supplementary_theoretical),supplementary_practical:n(data.supplementary_practical),final_grade:n(data.notaFinal??data.final_grade),final_status:clean(data.estado||data.final_status),source_modality:clean(data.modalidadOrigen||data.modalidad||data.source_modality),source_campus:clean(data.sedeOrigen||data.sede||data.source_campus),source_file:clean(data.archivoOrigen||data.archivo||data.source_file),source:'NEON_IMPORT',raw_data:data,updated_at:now()};
"""),
    ("""    const payload={period_id:periodId,student_id:Number(student.id),title:clean(data.titulo||data.title),tutor:clean(data.tutor),final_grade:data.notaFinal===''||data.notaFinal==null?null:Number(data.notaFinal??data.final_grade),final_status:clean(data.estado||data.final_status),source:'NEON_IMPORT',raw_data:data,updated_at:now()};
""", """    const n=v=>v===''||v==null?null:Number(v);
    const payload={period_id:periodId,student_id:Number(student.id),title:clean(data.titulo||data.title),tutor:clean(data.tutor),reader:clean(data.lector||data.reader),tutor_grade:n(data.notaTutor??data.tutor_grade),reader_grade:n(data.notaLector??data.reader_grade),written_average:n(data.promedioEscrito??data.written_average),practical_average:n(data.promedioPractica??data.practical_average),defense_average:n(data.promedioDefensa??data.defense_average),oral_average:n(data.defensaOral??data.oral_average),act_number:clean(data.numeroActa||data.act_number),act_date:clean(data.fechaActa||data.act_date),vocal_1:clean(data.tribunal1||data.vocal_1),vocal_2:clean(data.tribunal2||data.vocal_2),vocal_3:clean(data.tribunal3||data.vocal_3),final_grade:n(data.notaFinal??data.final_grade),final_status:clean(data.estado||data.final_status),source:'NEON_IMPORT',raw_data:data,updated_at:now()};
"""),
    ("""    const enrollmentPayload=source.map(row=>({period_id:periodId,student_id:idMap.get(digits(row.cedula)),career_code:clean(row.codigoCarrera),career_name:clean(row.carrera),modality:['presencial','en_linea','otra'].includes(row.modalidad)?row.modalidad:'otra',campus:clean(row.sede),shift:clean(row.jornada),source:'IMPORT',raw_data:row,updated_at:now()})).filter(row=>row.student_id);
    result=await client.from('enrollments').upsert(enrollmentPayload,{onConflict:'period_id,student_id'}).select('student_id');resultData(result,[]);progress(Math.ceil(source.length*.62),'Matrículas guardadas');
""", """    const priorEnrollments=await rowsFor('enrollments','student_id',q=>q.eq('period_id',periodId));
    const incomingStudentIds=new Set([...idMap.values()].map(Number));
    const staleStudentIds=priorEnrollments.map(row=>Number(row.student_id)).filter(studentId=>Number.isFinite(studentId)&&!incomingStudentIds.has(studentId));
    const enrollmentPayload=source.map(row=>({period_id:periodId,student_id:idMap.get(digits(row.cedula)),career_code:clean(row.codigoCarrera),career_name:clean(row.carrera),modality:['presencial','en_linea','otra'].includes(row.modalidad)?row.modalidad:'otra',campus:clean(row.sede),shift:clean(row.jornada),academic_status:'ACTIVO',source:'IMPORT',raw_data:row,updated_at:now()})).filter(row=>row.student_id);
    result=await client.from('enrollments').upsert(enrollmentPayload,{onConflict:'period_id,student_id'}).select('student_id');resultData(result,[]);
    if(staleStudentIds.length){const stale=await client.from('enrollments').update({academic_status:'INACTIVO_FUENTE',updated_at:now()}).eq('period_id',periodId).in('student_id',staleStudentIds);if(stale?.error)throw stale.error;}
    progress(Math.ceil(source.length*.62),'Matrículas guardadas y población conciliada');
"""),
    ("""    await client.from('import_batches').insert({period_id:periodId,import_type:'STUDENTS_REQUIREMENTS',file_name:clean(fileName),total_rows:source.length,inserted_rows:inserted,updated_rows:updated,failed_rows:0,status:'COMPLETED',details:{provider:'NEON'},finished_at:now()});
    await client.from('audit_log').insert({period_id:periodId,entity_type:'IMPORT_BATCH',entity_key:clean(fileName),action:'BULK_UPSERT_STUDENTS_REQUIREMENTS',payload:{total:source.length,inserted,updated,provider:'NEON'}});
    progress(source.length,'Completado');return{ok:true,total:source.length,inserted,updated,source:'NEON'};
""", """    await client.from('import_batches').insert({period_id:periodId,import_type:'STUDENTS_REQUIREMENTS',file_name:clean(fileName),total_rows:source.length,inserted_rows:inserted,updated_rows:updated,failed_rows:0,status:'COMPLETED',details:{provider:'NEON',inactive_from_previous_source:staleStudentIds.length},finished_at:now()});
    await client.from('audit_log').insert({period_id:periodId,entity_type:'IMPORT_BATCH',entity_key:clean(fileName),action:'BULK_UPSERT_STUDENTS_REQUIREMENTS',payload:{total:source.length,inserted,updated,inactive_from_previous_source:staleStudentIds.length,provider:'NEON'}});
    progress(source.length,'Completado');return{ok:true,total:source.length,inserted,updated,inactivated:staleStudentIds.length,source:'NEON'};
"""),
], markers=('assertNotThesis', 'accumulated_grade', "academic_status:'INACTIVO_FUENTE'"))

# Semántica de requisitos: NO CUMPLE es resultado válido; solo vacío/inválido es falta de dato.
patch_file('pages-data-runtime.js', [
    ("""      row.pending_requirements = pending;
      row.blank_requirements = blank;
      row.requirements_complete = !pending.length && !blank.length;
      row.missing_requirement_labels = [...pending, ...blank];
""", """      row.pending_requirements = pending;
      row.blank_requirements = blank;
      row.noncompliant_requirement_labels = pending;
      row.missing_requirement_labels = blank;
      row.requirement_issue_labels = [...pending, ...blank];
      row.requirements_data_complete = blank.length === 0;
      row.requirements_approved = pending.length === 0 && blank.length === 0;
      row.requirements_complete = row.requirements_approved;
"""),
    ("""    const requirements = REQUIREMENTS.map(([output, , label]) => ({
      label,
      complies: rows.filter(row => pass(row[output])).length,
      does_not_comply: rows.filter(row => !pass(row[output])).length,
    }));
    const complete = rows.filter(row => row.requirements_complete).length;
""", """    const requirements = REQUIREMENTS.map(([output, , label]) => ({
      label,
      complies: rows.filter(row => pass(row[output])).length,
      does_not_comply: rows.filter(row => fold(row[output]) === 'NO CUMPLE').length,
      missing: rows.filter(row => !pass(row[output]) && fold(row[output]) !== 'NO CUMPLE').length,
    }));
    const complete = rows.filter(row => row.requirements_complete).length;
    const dataComplete = rows.filter(row => row.requirements_data_complete).length;
"""),
    ("""        requirements_complete: complete, requirements_pending: rows.length - complete,
        notes_loaded: rows.filter(row => row.notes_loaded).length,
""", """        requirements_complete: complete, requirements_pending: rows.length - complete,
        requirements_data_complete: dataComplete, requirements_data_missing: rows.length - dataComplete,
        requirements_not_approved: rows.filter(row => row.requirements_data_complete && !row.requirements_approved).length,
        notes_loaded: rows.filter(row => row.notes_loaded).length,
"""),
    ("source: 'GOOGLE_SHEETS', synced_at: context.data.syncedAt", "source: 'NEON_POSTGRESQL', synced_at: context.data.syncedAt"),
], markers=('requirements_data_missing', 'noncompliant_requirement_labels'))

patch_file('pages-stability-runtime.js', [
    ("""    const requirements = REQUIREMENTS.map(([key, label]) => ({
      label,
      complies: students.filter(row => pass(row[key])).length,
      does_not_comply: students.filter(row => !pass(row[key])).length,
    }));
    const complete = students.filter(row => row.requirements_complete === true || row.requirements_complete === 1).length;
""", """    const requirements = REQUIREMENTS.map(([key, label]) => ({
      label,
      complies: students.filter(row => pass(row[key])).length,
      does_not_comply: students.filter(row => fold(row[key]) === 'NO CUMPLE').length,
      missing: students.filter(row => !clean(row[key]) || (!pass(row[key]) && fold(row[key]) !== 'NO CUMPLE')).length,
    }));
    const complete = students.filter(row => row.requirements_complete === true || row.requirements_complete === 1).length;
    const dataComplete = students.filter(row => row.requirements_data_complete === true || row.requirements_data_complete === 1 || !(row.missing_requirement_labels || []).length).length;
    const notApproved = students.filter(row => (row.noncompliant_requirement_labels || []).length > 0).length;
"""),
    ("""      requirements_complete: complete,
      requirements_pending: students.length - complete,
""", """      requirements_complete: complete,
      requirements_pending: students.length - complete,
      requirements_data_complete: dataComplete,
      requirements_data_missing: students.length - dataComplete,
      requirements_not_approved: notApproved,
"""),
    ("""    const pending = Number(summary.requirements_pending || 0);
    push('Requisitos', pending ? 'warning' : 'ok', pending ? `${pending} estudiantes tienen requisitos pendientes o incompletos.` : 'No se detectaron requisitos pendientes.');
""", """    const notApproved = Number(summary.requirements_not_approved ?? summary.requirements_pending ?? 0);
    const missingData = Number(summary.requirements_data_missing || 0);
    push('Integridad de requisitos', missingData ? 'warning' : 'ok', missingData ? `${missingData} estudiantes tienen uno o más requisitos sin dato.` : 'Los requisitos tienen datos completos.');
    push('Resultado de requisitos', 'ok', notApproved ? `${notApproved} estudiantes registran NO CUMPLE; es un resultado institucional válido, no un dato faltante.` : 'No se registran estudiantes con NO CUMPLE.');
"""),
    ("""        requirements_complete: Number(summary.requirements_complete || 0),
        requirements_pending: pending,
""", """        requirements_complete: Number(summary.requirements_complete || 0),
        requirements_not_approved: notApproved,
        requirements_data_missing: missingData,
        requirements_pending: notApproved,
"""),
], markers=('Integridad de requisitos', 'requirements_data_missing'))

# Importación de población: detectar bajas entre versiones antes de guardar.
patch_file('requirements-import-sheets-ui.js', [
    ("const local = { rows: [], file: null, fileInfo: null, existingIds: new Set(), saving: false };", "const local = { rows: [], file: null, fileInfo: null, existingIds: new Set(), periodIds: new Set(), staleIds: [], saving: false };"),
    ("""        const studentData=await window.InformtitNeon.estudiantes();
        local.existingIds=new Set((studentData.estudiantes||[]).map(row=>id(row.cedula)).filter(Boolean));
        renderPreview();
""", """        const studentData=await window.InformtitNeon.estudiantes();
        local.existingIds=new Set((studentData.estudiantes||[]).map(row=>id(row.cedula)).filter(Boolean));
        const periodoId=await currentPeriodId();
        if(!periodoId) throw new Error('Seleccione primero el período activo.');
        const enrollmentData=await window.InformtitNeon.matriculas(periodoId);
        local.periodIds=new Set((enrollmentData.matriculas||[]).filter(row=>!row.retirado).map(row=>id(row.cedula)).filter(Boolean));
        const incomingIds=new Set(rows.map(row=>row.cedula));
        local.staleIds=[...local.periodIds].filter(cedula=>!incomingIds.has(cedula));
        renderPreview();
"""),
    ("""      <div class=\"reqs-muted\"><strong>Altas:</strong> ${newIds.length} · <strong>Actualizaciones:</strong> ${rows.length-newIds.length} · <strong>Duplicados:</strong> ${local.duplicates?.length||0} · <strong>Filas sin cédula:</strong> ${local.invalidRows?.length||0}</div>
""", """      <div class=\"reqs-muted\"><strong>Altas:</strong> ${newIds.length} · <strong>Actualizaciones:</strong> ${rows.length-newIds.length} · <strong>Ausentes de la nueva base:</strong> ${local.staleIds?.length||0} · <strong>Duplicados:</strong> ${local.duplicates?.length||0} · <strong>Filas sin cédula:</strong> ${local.invalidRows?.length||0}</div>
      ${local.staleIds?.length ? `<div class=\"req-warning\"><strong>${local.staleIds.length} estudiante(s) ya no aparecen en el nuevo archivo.</strong> Al confirmar se marcarán como fuera de la población activa del período; no se eliminarán. ${esc(local.staleIds.slice(0,8).join(', '))}${local.staleIds.length>8?'…':''}</div>`:''}
"""),
    ("""      await window.InformtitNeon.bulkUpsertStudentsRequirements(local.rows,periodoId,local.file?.name||'',(completed,_total,stage)=>{
        const pct=Math.max(2,Math.min(100,Math.round((Number(completed||0)/Math.max(1,total))*100)));
        bar.value=pct; label.textContent=`${stage || 'Guardando'} · ${pct}%`;
      });
      bar.value=100; label.textContent=`Completado · ${total} estudiantes`;
""", """      const result=await window.InformtitNeon.bulkUpsertStudentsRequirements(local.rows,periodoId,local.file?.name||'',(completed,_total,stage)=>{
        const pct=Math.max(2,Math.min(100,Math.round((Number(completed||0)/Math.max(1,total))*100)));
        bar.value=pct; label.textContent=`${stage || 'Guardando'} · ${pct}%`;
      });
      const inactivated=Number(result?.inactivated||0);
      bar.value=100; label.textContent=`Completado · ${total} estudiantes${inactivated?` · ${inactivated} fuera de población`:''}`;
"""),
    ("if(typeof toast==='function') toast(`${total} estudiantes, matrículas y requisitos guardados en Neon.`);", "if(typeof toast==='function') toast(`${total} estudiantes, matrículas y requisitos guardados en Neon.${inactivated?` ${inactivated} registro(s) anterior(es) quedaron fuera de la población activa.`:''}`);"),
    ("${esc((row.missing_requirement_labels||[]).join(' · ')||'—')}", "${esc((row.requirement_issue_labels || [...(row.noncompliant_requirement_labels||[]), ...(row.missing_requirement_labels||[])]).join(' · ')||'—')}"),
    ("local.rows=[];local.file=null;local.fileInfo=null;", "local.rows=[];local.file=null;local.fileInfo=null;local.periodIds=new Set();local.staleIds=[];"),
], markers=('Ausentes de la nueva base', 'inactivated'))

# Cache-busting de módulos corregidos.
index = site / 'index.html'
text = index.read_text(encoding='utf-8')
for old, new in [
    ('neon-data-runtime.js?v=1.4', 'neon-data-runtime.js?v=1.5'),
    ('pages-data-runtime.js?v=3.2', 'pages-data-runtime.js?v=3.3'),
    ('requirements-import-sheets-ui.js?v=4.3', 'requirements-import-sheets-ui.js?v=4.4'),
    ('results-import-ui.js?v=3.0', 'results-import-ui.js?v=4.1'),
    ('pages-stability-runtime.js?v=1.2', 'pages-stability-runtime.js?v=1.3'),
]:
    text = text.replace(old, new)
index.write_text(text, encoding='utf-8')
print('Data integrity build corrections applied.')
