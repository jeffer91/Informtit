(() => {
  'use strict';

  if (!/(^|\.)github\.io$/i.test(window.location.hostname)) return;

  const VERSION = '4.0.0';
  const MARKER = 'CONCILIACION_CEDULA_V4';
  const XLSX_SRC = 'https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js';
  const PASS = new Set(['CUMPLE','SI','SÍ','APROBADO','OK','TRUE','1']);

  const stateImport = {
    master: null,
    complexive: { file: null, rows: [], saving: false },
    nuclei: { file: null, rows: [], saving: false },
    reconciling: false,
  };

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const clean = value => String(value ?? '').replace(/\u00a0/g, ' ').trim().replace(/\s+/g, ' ');
  const fold = value => clean(value).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toUpperCase();
  const keyOf = value => fold(value).replace(/[^A-Z0-9]/g, '');
  const digits = value => clean(value).replace(/\D/g, '');
  const esc = value => clean(value).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const now = () => new Date().toISOString();
  const pass = value => PASS.has(fold(value));
  const num = value => {
    if (value === null || value === undefined) return null;
    const text = clean(value);
    if (!text || fold(text) === 'NULL' || text === '-' || text === '—') return null;
    const n = Number(text.replace(',', '.'));
    return Number.isFinite(n) ? n : null;
  };
  const rowsOf = result => {
    if (result?.error) throw result.error;
    return Array.isArray(result?.data) ? result.data : [];
  };
  const activeReport = () => window.state?.activeReport || null;

  function canonicalCareer(value = '') {
    let text = fold(value)
      .replace(/^TECNOLOGIA SUPERIOR UNIVERSITARIA EN /, '')
      .replace(/^TECNOLOGIA SUPERIOR EN /, '')
      .replace(/^TECNICO SUPERIOR EN /, '')
      .replace(/ ONLINE$/, '')
      .replace(/ EN LINEA$/, '')
      .replace(/ VIRTUAL$/, '')
      .replace(/ PRESENCIAL$/, '')
      .trim();
    const aliases = {
      ADMINISTRACION: 'ADMINISTRACIÓN',
      CONTABILIDAD: 'CONTABILIDAD',
      'DESARROLLO DE SOFTWARE': 'DESARROLLO DE SOFTWARE',
      'EDUCACION BASICA': 'EDUCACIÓN BÁSICA',
      'EDUCACION INICIAL': 'EDUCACIÓN INICIAL',
      ENFERMERIA: 'ENFERMERÍA',
      'ESTETICA INTEGRAL': 'ESTÉTICA INTEGRAL',
      'GESTION DEL TALENTO HUMANO': 'GESTIÓN DEL TALENTO HUMANO',
      'MARKETING DIGITAL Y COMERCIO ELECTRONICO': 'MARKETING DIGITAL Y COMERCIO ELECTRÓNICO',
      'REDES Y TELECOMUNICACIONES': 'REDES Y TELECOMUNICACIONES',
      'SEGURIDAD CIUDADANA Y ORDEN PUBLICO': 'SEGURIDAD CIUDADANA Y ORDEN PÚBLICO',
    };
    if (text.includes('REDES') && text.includes('TELECOMUNICACIONES')) return 'REDES Y TELECOMUNICACIONES';
    return aliases[text] || text;
  }

  function normalizeModality(value = '', careerCode = '') {
    const text = fold(value);
    const code = clean(careerCode).toUpperCase();
    if (/EN LINEA|ONLINE|VIRTUAL/.test(text) || /-L-/.test(code)) return 'en_linea';
    if (/PRESENCIAL|EN VIVO|HIBRIDA/.test(text) || /-P-/.test(code)) return 'presencial';
    return 'otra';
  }

  function periodKey(value = '') {
    return fold(value).replace(/\bDE\b/g, ' ').replace(/\bA\b/g, ' ').replace(/\s+/g, ' ').trim();
  }

  async function activePeriodId() {
    const report = activeReport();
    if (!report) return '';
    return clean(await window.InformtitPagesData?.resolvePeriodId?.(report) || report.periodoId || report.firebase_period_id || report.period_id);
  }

  function activePeriodLabel() {
    const report = activeReport();
    return clean(report?.period || report?.period_name || $('#report-period')?.textContent || '');
  }

  async function client() {
    if (!window.InformtitNeon?.getClient) throw new Error('Neon no está disponible.');
    return await window.InformtitNeon.getClient();
  }

  async function loadXlsx() {
    if (window.XLSX) return window.XLSX;
    await new Promise((resolve, reject) => {
      const existing = document.querySelector(`script[src="${XLSX_SRC}"]`);
      if (existing) {
        if (window.XLSX) return resolve();
        existing.addEventListener('load', resolve, { once: true });
        existing.addEventListener('error', () => reject(new Error('No se pudo cargar el lector de Excel.')), { once: true });
        return;
      }
      const script = document.createElement('script');
      script.src = XLSX_SRC;
      script.onload = resolve;
      script.onerror = () => reject(new Error('No se pudo cargar el lector de Excel.'));
      document.head.appendChild(script);
    });
    return window.XLSX;
  }

  function sheetRows(workbook) {
    const first = workbook.SheetNames[0];
    if (!first) return [];
    return window.XLSX.utils.sheet_to_json(workbook.Sheets[first], { defval:'', raw:false });
  }

  function normalizedRow(raw = {}) {
    const out = {};
    Object.entries(raw).forEach(([key, value]) => { out[keyOf(key)] = value; });
    return out;
  }

  function pick(row, ...aliases) {
    for (const alias of aliases) {
      const value = row[keyOf(alias)];
      if (value !== undefined && clean(value) !== '') return value;
    }
    return '';
  }

  function nucleusNumber(row) {
    const matter = clean(pick(row, 'materia'));
    const code = clean(pick(row, 'cod_materia', 'codigo_materia'));
    const match = fold(matter).match(/NUCLEO\s*([1-4])/);
    if (match) return Number(match[1]);
    const codeMatch = code.match(/70([1-4])(?:\D|$)/);
    return codeMatch ? Number(codeMatch[1]) : 0;
  }

  async function readWorkbook(file) {
    const XLSX = await loadXlsx();
    const buffer = await file.arrayBuffer();
    const workbook = XLSX.read(buffer, { type:'array', cellDates:false });
    return { workbook, rows: sheetRows(workbook) };
  }

  function sourceType(rows) {
    if (!rows.length) return '';
    const keys = new Set(Object.keys(rows[0]).map(keyOf));
    if (keys.has(keyOf('identificacion_estudiante')) && keys.has(keyOf('notaTeorico')) && keys.has(keyOf('notaPromedioAcumulado'))) return 'complexive';
    if (keys.has(keyOf('numeroIdentificacion')) && keys.has(keyOf('nota_nucleo')) && keys.has(keyOf('resultado_aprobacion'))) return 'nuclei';
    return '';
  }

  async function loadMaster(force = false) {
    if (stateImport.master && !force) return stateImport.master;
    const periodId = await activePeriodId();
    if (!periodId) throw new Error('Seleccione primero el período activo.');
    const db = await client();
    const [studentsR, enrollmentsR, requirementsR, thesisR, complexiveR, nucleiR] = await Promise.all([
      db.from('students').select('id,identification,full_name'),
      db.from('enrollments').select('student_id,career_code,career_name,modality,campus,titulation_route').eq('period_id', periodId),
      db.from('requirements').select('*').eq('period_id', periodId),
      db.from('thesis_results').select('student_id').eq('period_id', periodId),
      db.from('complexive_results').select('student_id').eq('period_id', periodId),
      db.from('nuclei_results').select('student_id,nucleus_number').eq('period_id', periodId),
    ]);
    const students = rowsOf(studentsR);
    const enrollments = rowsOf(enrollmentsR);
    const requirements = rowsOf(requirementsR);
    const thesis = rowsOf(thesisR);
    const complexive = rowsOf(complexiveR);
    const nuclei = rowsOf(nucleiR);
    const studentById = new Map(students.map(row => [Number(row.id), row]));
    const enrollmentById = new Map(enrollments.map(row => [Number(row.student_id), row]));
    const requirementById = new Map(requirements.map(row => [Number(row.student_id), row]));
    const masterByCedula = new Map();
    requirements.forEach(req => {
      const student = studentById.get(Number(req.student_id));
      if (!student) return;
      const cedula = digits(student.identification);
      if (!cedula) return;
      masterByCedula.set(cedula, {
        student,
        enrollment: enrollmentById.get(Number(req.student_id)) || {},
        requirement: req,
      });
    });
    stateImport.master = {
      periodId,
      students,
      enrollments,
      requirements,
      thesisIds: new Set(thesis.map(row => Number(row.student_id))),
      complexiveIds: new Set(complexive.map(row => Number(row.student_id))),
      nucleiIds: new Set(nuclei.map(row => Number(row.student_id))),
      studentById,
      enrollmentById,
      requirementById,
      masterByCedula,
    };
    return stateImport.master;
  }

  function compareWarning(label, sourceValue, masterValue) {
    if (!clean(sourceValue) || !clean(masterValue)) return '';
    return fold(sourceValue) === fold(masterValue) ? '' : `${label}: archivo «${clean(sourceValue)}» / maestro «${clean(masterValue)}»`;
  }

  function reconcileComplexive(rawRows, master) {
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
      const warnings = [];
      const errors = [];
      if (!cedula || cedula.length !== 10) errors.push('Cédula inválida');
      if (!matched) errors.push('No existe en la población maestra de requisitos');
      if (studentId && master.thesisIds.has(studentId)) errors.push('Protegido: pertenece a Trabajo de Titulación');
      if (sourcePeriod && activeLabel && periodKey(sourcePeriod) !== activeLabel) errors.push(`Período del archivo: ${sourcePeriod}`);
      if (matched) {
        const w1 = compareWarning('Nombre', sourceName, matched.student.full_name);
        const w2 = compareWarning('Carrera', canonicalCareer(sourceCareer), canonicalCareer(matched.enrollment.career_name));
        const w3 = compareWarning('Sede', sourceCampus, matched.enrollment.campus);
        [w1,w2,w3].filter(Boolean).forEach(item => warnings.push(item));
      }
      return {
        index:index+2,
        cedula,
        studentId,
        nombre: sourceName,
        carrera: sourceCareer,
        modalidad: normalizeModality(sourceModality, matched?.enrollment?.career_code || ''),
        sede: sourceCampus,
        periodo: sourcePeriod,
        tipo: clean(pick(row, 'tipo_titulacion')),
        teorico: num(pick(row, 'notaTeorico')),
        practico: num(pick(row, 'notaPractico')),
        acumulado: num(pick(row, 'notaPromedioAcumulado')),
        supletorio: num(pick(row, 'notaSupletorio')),
        matched,
        warnings,
        errors,
        raw,
      };
    });
    parsed.forEach(item => { if (duplicateIds.has(item.cedula)) item.errors.push('Cédula duplicada dentro del archivo'); });
    return parsed;
  }

  function reconcileNuclei(rawRows, master) {
    const seen = new Set();
    const duplicateKeys = new Set();
    const parsed = rawRows.map((raw, index) => {
      const row = normalizedRow(raw);
      const cedula = digits(pick(row, 'numeroIdentificacion', 'identificacion_estudiante'));
      const nucleus = nucleusNumber(row);
      const uniqueKey = `${cedula}|${nucleus}`;
      if (cedula && nucleus && seen.has(uniqueKey)) duplicateKeys.add(uniqueKey);
      if (cedula && nucleus) seen.add(uniqueKey);
      const matched = cedula ? master.masterByCedula.get(cedula) : null;
      const studentId = Number(matched?.student?.id || 0);
      const sourceName = clean(pick(row, 'nombre_estudiante'));
      const sourceCareer = clean(pick(row, 'nombre_carrera'));
      const sourceCampus = clean(pick(row, 'sede'));
      const sourceModality = clean(pick(row, 'modalidad'));
      const warnings = [];
      const errors = [];
      if (!cedula || cedula.length !== 10) errors.push('Cédula inválida');
      if (!nucleus) errors.push('No se pudo identificar Núcleo 1, 2, 3 o 4');
      if (!matched) errors.push('No existe en la población maestra de requisitos');
      if (studentId && master.thesisIds.has(studentId)) errors.push('Protegido: pertenece a Trabajo de Titulación');
      if (matched) {
        const w1 = compareWarning('Nombre', sourceName, matched.student.full_name);
        const w2 = compareWarning('Carrera', canonicalCareer(sourceCareer), canonicalCareer(matched.enrollment.career_name));
        const w3 = compareWarning('Sede', sourceCampus, matched.enrollment.campus);
        [w1,w2,w3].filter(Boolean).forEach(item => warnings.push(item));
      }
      return {
        index:index+2,
        cedula,
        studentId,
        nucleus,
        nombre:sourceName,
        carrera:sourceCareer,
        modalidad:normalizeModality(sourceModality, clean(pick(row, 'codigo_carrera'))),
        sede:sourceCampus,
        codigoCarrera:clean(pick(row, 'codigo_carrera')),
        codigoMateria:clean(pick(row, 'cod_materia')),
        materia:clean(pick(row, 'materia')),
        docente:clean(pick(row, 'Pro_nombre')),
        nota:num(pick(row, 'nota_nucleo')),
        resultado:clean(pick(row, 'resultado_aprobacion')),
        matched,
        warnings,
        errors,
        raw,
      };
    });
    parsed.forEach(item => {
      if (duplicateKeys.has(`${item.cedula}|${item.nucleus}`)) item.errors.push(`Duplicado Núcleo ${item.nucleus}`);
    });
    return parsed;
  }

  function stats(rows) {
    return {
      total: rows.length,
      valid: rows.filter(row => !row.errors.length).length,
      errors: rows.filter(row => row.errors.length).length,
      warnings: rows.filter(row => row.warnings.length && !row.errors.length).length,
      orphans: rows.filter(row => row.errors.some(error => error.includes('población maestra'))).length,
      protected: rows.filter(row => row.errors.some(error => error.includes('Trabajo de Titulación'))).length,
    };
  }

  async function analyzeFile(kind, file) {
    const message = $(`#${kind}-import-message`);
    if (message) message.textContent = 'Analizando archivo…';
    const master = await loadMaster(true);
    if (!master.requirements.length) throw new Error('Primero cargue la población y requisitos del período. Sin base maestra no se guardan resultados.');
    const { rows } = await readWorkbook(file);
    const detected = sourceType(rows);
    if (detected !== kind) {
      const expected = kind === 'complexive' ? '01.xlsx / resultados de Examen Complexivo' : '02.xlsx / resultados de Núcleos';
      throw new Error(`El archivo no corresponde a ${expected}. Informtit detectó: ${detected || 'formato desconocido'}.`);
    }
    const parsed = kind === 'complexive' ? reconcileComplexive(rows, master) : reconcileNuclei(rows, master);
    stateImport[kind].file = file;
    stateImport[kind].rows = parsed;
    renderImportPreview(kind);
  }

  function rowStatus(row) {
    if (row.errors.length) return `<span class="academic-pill bad">Revisar</span><small>${esc(row.errors.join(' · '))}</small>`;
    if (row.warnings.length) return `<span class="academic-pill warn">Válido con aviso</span><small>${esc(row.warnings.join(' · '))}</small>`;
    return '<span class="academic-pill ok">Listo</span><small>Match exacto por cédula</small>';
  }

  function renderImportPreview(kind) {
    const container = $(`#${kind}-import-preview`);
    if (!container) return;
    const rows = stateImport[kind].rows;
    const s = stats(rows);
    const isNuclei = kind === 'nuclei';
    const students = new Set(rows.map(row => row.cedula).filter(Boolean)).size;
    container.innerHTML = `
      <div class="academic-kpis">
        <div><span>${isNuclei ? 'Registros' : 'Estudiantes'}</span><strong>${s.total}</strong></div>
        ${isNuclei ? `<div><span>Estudiantes únicos</span><strong>${students}</strong></div>` : ''}
        <div><span>Listos</span><strong>${s.valid}</strong></div>
        <div><span>Por revisar</span><strong class="${s.errors ? 'danger-text' : ''}">${s.errors}</strong></div>
        <div><span>Avisos</span><strong>${s.warnings}</strong></div>
      </div>
      <div class="academic-note">${esc(stateImport[kind].file?.name || '')} · conciliación exclusivamente por cédula · ${s.orphans} sin maestro · ${s.protected} protegidos por Trabajo de Titulación.</div>
      <div class="academic-table-wrap">
        <table class="academic-table">
          <thead><tr><th>Fila</th><th>Cédula</th><th>Estudiante</th>${isNuclei?'<th>Núcleo</th><th>Materia</th><th>Nota</th>':'<th>Teórico</th><th>Práctico</th><th>Acumulado</th><th>Supletorio</th>'}<th>Estado</th></tr></thead>
          <tbody>${rows.slice(0,200).map(row => `<tr>
            <td>${row.index}</td><td>${esc(row.cedula||'—')}</td><td><strong>${esc(row.matched?.student?.full_name || row.nombre || '—')}</strong></td>
            ${isNuclei?`<td>${row.nucleus||'—'}</td><td>${esc(row.materia||'—')}</td><td>${row.nota??'—'}</td>`:`<td>${row.teorico??'—'}</td><td>${row.practico??'—'}</td><td>${row.acumulado??'—'}</td><td>${row.supletorio??'—'}</td>`}
            <td>${rowStatus(row)}</td></tr>`).join('')}</tbody>
        </table>
      </div>
      ${rows.length>200?`<div class="academic-note">Vista previa: primeras 200 filas de ${rows.length}.</div>`:''}
      <div class="academic-actions">
        <button type="button" class="button primary" data-save-${kind} ${s.valid?'':'disabled'}>Guardar ${s.valid} válidos en Neon</button>
      </div>`;
    container.querySelector(`[data-save-${kind}]`)?.addEventListener('click', () => saveKind(kind));
  }

  async function chunkedUpsert(db, table, payload, onConflict, onProgress) {
    const chunkSize = 150;
    let done = 0;
    for (let start = 0; start < payload.length; start += chunkSize) {
      const chunk = payload.slice(start, start + chunkSize);
      const result = await db.from(table).upsert(chunk, { onConflict }).select('student_id');
      rowsOf(result);
      done += chunk.length;
      onProgress?.(done, payload.length);
    }
  }

  async function protectAndSetComplexiveRoute(db, periodId, ids) {
    if (!ids.length) return;
    const result = await db.from('enrollments')
      .update({ titulation_route:'COMPLEXIVO', updated_at:now() })
      .eq('period_id', periodId)
      .in('student_id', ids);
    if (result?.error) throw result.error;
  }

  async function logImport(db, periodId, type, fileName, total, saved, failed, details = {}) {
    const result = await db.from('import_batches').insert({
      period_id:periodId,
      import_type:type,
      file_name:clean(fileName),
      total_rows:total,
      inserted_rows:saved,
      updated_rows:0,
      failed_rows:failed,
      status:failed ? 'PARTIAL' : 'COMPLETED',
      details:{ provider:'NEON', matching_key:'CEDULA', ...details },
      finished_at:now(),
    });
    if (result?.error) console.warn('No se pudo registrar import_batch', result.error);
  }

  async function saveKind(kind) {
    if (stateImport[kind].saving) return;
    const rows = stateImport[kind].rows;
    const valid = rows.filter(row => !row.errors.length);
    if (!valid.length) return;
    const periodId = await activePeriodId();
    if (!periodId) throw new Error('No hay período activo.');
    const db = await client();
    stateImport[kind].saving = true;
    const button = $(`[data-save-${kind}]`);
    const original = button?.textContent || '';
    if (button) { button.disabled = true; button.textContent = 'Guardando…'; }
    try {
      if (kind === 'complexive') {
        const payload = valid.map(item => ({
          period_id:periodId,
          student_id:item.studentId,
          theoretical_grade:item.teorico,
          practical_grade:item.practico,
          supplementary_theoretical:item.supletorio,
          supplementary_practical:null,
          final_grade:null,
          final_status:[item.teorico,item.practico,item.acumulado,item.supletorio].some(value => value !== null) ? 'REGISTRADO' : 'SIN_NOTA',
          source:'SISACAD_COMPLEXIVO_XLSX',
          raw_data:{
            ...item.raw,
            cedula:item.cedula,
            notaPromedioAcumulado:item.acumulado,
            modalidad_normalizada:item.modalidad,
            archivo:stateImport.complexive.file?.name || '',
            import_policy:'CEDULA_MASTER_TT_PRIORITY',
          },
          updated_at:now(),
        }));
        await chunkedUpsert(db, 'complexive_results', payload, 'period_id,student_id', (done,total) => {
          if (button) button.textContent = `Guardando ${done}/${total}…`;
        });
        await protectAndSetComplexiveRoute(db, periodId, [...new Set(valid.map(item => item.studentId))]);
        await logImport(db, periodId, 'COMPLEXIVE_RESULTS', stateImport.complexive.file?.name, rows.length, valid.length, rows.length-valid.length, { accumulated_grade_kept_in_raw_data:true });
      } else {
        const payload = valid.map(item => ({
          period_id:periodId,
          student_id:item.studentId,
          nucleus_number:item.nucleus,
          career_name:item.matched?.enrollment?.career_name || canonicalCareer(item.carrera),
          course_name:item.materia,
          grade:item.nota,
          final_status:item.resultado,
          source:'SISACAD_NUCLEI_XLSX',
          raw_data:{
            ...item.raw,
            cedula:item.cedula,
            codigo_carrera:item.codigoCarrera,
            codigo_materia:item.codigoMateria,
            docente:item.docente,
            modalidad_normalizada:item.modalidad,
            sede_origen:item.sede,
            archivo:stateImport.nuclei.file?.name || '',
            import_policy:'CEDULA_MASTER_TT_PRIORITY',
          },
          updated_at:now(),
        }));
        await chunkedUpsert(db, 'nuclei_results', payload, 'period_id,student_id,nucleus_number', (done,total) => {
          if (button) button.textContent = `Guardando ${done}/${total}…`;
        });
        await protectAndSetComplexiveRoute(db, periodId, [...new Set(valid.map(item => item.studentId))]);
        await logImport(db, periodId, 'NUCLEI_RESULTS', stateImport.nuclei.file?.name, rows.length, valid.length, rows.length-valid.length);
      }
      stateImport.master = null;
      window.InformtitPagesData?.invalidate?.(periodId);
      if (typeof window.toast === 'function') window.toast(`${valid.length} registros guardados en Neon. ${rows.length-valid.length} quedaron por revisar.`);
      await renderReconciliation(true);
    } catch (error) {
      if (typeof window.toast === 'function') window.toast(error?.message || String(error), true);
      else alert(error?.message || String(error));
    } finally {
      stateImport[kind].saving = false;
      if (button?.isConnected) { button.disabled = false; button.textContent = original; }
    }
  }

  function approvedRequirement(req) {
    return pass(req?.titulation_approval || req?.aprobacionTitulacion)
      && pass(req?.complexive_approval || req?.aprobacionComplexivo || req?.aprobacionComplexivoProyecto);
  }

  function cedulasForIds(master, ids) {
    return [...ids].map(id => digits(master.studentById.get(Number(id))?.identification)).filter(Boolean);
  }

  function details(title, values) {
    if (!values.length) return '';
    return `<details class="recon-details"><summary>${esc(title)} · ${values.length}</summary><div>${values.slice(0,80).map(value=>`<code>${esc(value)}</code>`).join(' ')}${values.length>80?' …':''}</div></details>`;
  }

  async function renderReconciliation(force = false) {
    const host = $('#academic-reconciliation');
    if (!host || stateImport.reconciling) return;
    stateImport.reconciling = true;
    host.innerHTML = '<div class="academic-note">Conciliando información del período en Neon…</div>';
    try {
      const master = await loadMaster(force);
      const masterIds = new Set(master.requirements.map(row => Number(row.student_id)));
      const thesisIds = master.thesisIds;
      const complexiveEvidence = new Set([...master.complexiveIds, ...master.nucleiIds]);
      const complexiveClassified = new Set([...complexiveEvidence].filter(id => !thesisIds.has(id)));
      const undefinedIds = new Set([...masterIds].filter(id => !thesisIds.has(id) && !complexiveEvidence.has(id)));
      const conflictIds = new Set([...thesisIds].filter(id => complexiveEvidence.has(id)));
      const orphanEvidence = new Set([...complexiveEvidence, ...thesisIds].filter(id => !masterIds.has(id)));
      const approvedIds = new Set(master.requirements.filter(approvedRequirement).map(row => Number(row.student_id)));
      const nucleiWithoutApproval = new Set([...master.nucleiIds].filter(id => !approvedIds.has(id)));
      const complexiveWithoutNuclei = new Set([...master.complexiveIds].filter(id => !master.nucleiIds.has(id) && !thesisIds.has(id)));
      host.innerHTML = `
        <div class="recon-head"><div><h3>Conciliación del período</h3><p>Prioridad: Trabajo de Titulación → evidencia Complexivo/Núcleos → Sin definir. La cédula es la llave.</p></div><button type="button" class="button secondary small" id="refresh-reconciliation">Actualizar</button></div>
        <div class="academic-kpis recon-kpis">
          <div><span>Población maestra</span><strong>${masterIds.size}</strong></div>
          <div><span>Habilitados oficialmente</span><strong>${approvedIds.size}</strong></div>
          <div><span>Trabajo de Titulación</span><strong>${thesisIds.size}</strong></div>
          <div><span>Complexivo</span><strong>${complexiveClassified.size}</strong></div>
          <div><span>Sin ruta definida</span><strong>${undefinedIds.size}</strong></div>
          <div><span>Resultados sin maestro</span><strong class="${orphanEvidence.size?'danger-text':''}">${orphanEvidence.size}</strong></div>
          <div><span>Conflictos TT/Complexivo</span><strong class="${conflictIds.size?'danger-text':''}">${conflictIds.size}</strong></div>
          <div><span>Complexivo sin Núcleos</span><strong>${complexiveWithoutNuclei.size}</strong></div>
        </div>
        ${details('Sin ruta definida', cedulasForIds(master, undefinedIds))}
        ${details('Resultados sin población maestra', cedulasForIds(master, orphanEvidence))}
        ${details('Conflictos TT/Complexivo', cedulasForIds(master, conflictIds))}
        ${details('Núcleos sin habilitación oficial', cedulasForIds(master, nucleiWithoutApproval))}
        ${details('Complexivo sin Núcleos', cedulasForIds(master, complexiveWithoutNuclei))}
      `;
      $('#refresh-reconciliation')?.addEventListener('click', () => renderReconciliation(true));
    } catch (error) {
      host.innerHTML = `<div class="academic-error">${esc(error?.message || error)}</div>`;
    } finally {
      stateImport.reconciling = false;
    }
  }

  function switchToTab(name, then = null) {
    const button = document.querySelector(`[data-tab="${name}"]`);
    if (!button) return;
    button.click();
    if (typeof then === 'function') setTimeout(then, 80);
  }

  function card(title, text, body, status = '') {
    return `<section class="academic-source-card">
      <div class="academic-card-head"><div><span class="eyebrow">${esc(status)}</span><h3>${esc(title)}</h3><p>${esc(text)}</p></div></div>
      ${body}
    </section>`;
  }

  function renderShell() {
    const tab = $('#tab-imports');
    if (!tab) return;
    const period = activePeriodLabel() || 'Seleccione un período';
    tab.innerHTML = `<div class="panel academic-import-shell">
      <div class="academic-main-head">
        <div><h2>Importaciones del período</h2><p>Período activo: <strong>${esc(period)}</strong>. Cada fuente tiene una función distinta y todas se concilian por cédula.</p></div>
        <span class="academic-source-pill">Neon PostgreSQL</span>
      </div>
      <div class="academic-source-grid">
        ${card('1. Población y requisitos','Fuente maestra de estudiantes, carrera, sede, contactos y requisitos.',`
          <div class="academic-actions"><button type="button" class="button primary" id="open-requirements-import">Abrir importador de requisitos</button></div>
          <div class="academic-note">Esta carga crea/actualiza estudiantes. Los archivos de resultados no crean población.</div>`,'BASE MAESTRA')}
        ${card('2. Trabajo de Titulación','Cargue primero los pocos casos de Trabajo de Titulación. La ruta queda protegida por cédula.',`
          <div class="academic-actions"><button type="button" class="button primary" id="open-thesis-import">Abrir Trabajo de Titulación</button></div>
          <div class="academic-note">Si una cédula tiene Trabajo de Titulación, Núcleos y Complexivo no pueden reclasificarla.</div>`,'PRIORIDAD 1')}
        ${card('3. Examen Complexivo','Suba 01.xlsx. Se guardan Teórico, Práctico, Promedio Acumulado y Supletorio como datos independientes.',`
          <label class="academic-drop">Archivo 01.xlsx<input type="file" id="complexive-import-file" accept=".xlsx,.xls"></label>
          <div id="complexive-import-message" class="academic-note">Esperando archivo.</div>
          <div id="complexive-import-preview"></div>`,'RESULTADOS')}
        ${card('4. Núcleos','Suba 02.xlsx. Informtit detecta Núcleo 1–4 y guarda cada fila por cédula + número de Núcleo.',`
          <label class="academic-drop">Archivo 02.xlsx<input type="file" id="nuclei-import-file" accept=".xlsx,.xls"></label>
          <div id="nuclei-import-message" class="academic-note">Esperando archivo.</div>
          <div id="nuclei-import-preview"></div>`,'RESULTADOS')}
      </div>
      <section id="academic-reconciliation" class="academic-reconciliation"></section>
    </div>`;

    $('#open-requirements-import')?.addEventListener('click', () => switchToTab('roster', () => $('#neon-req-open')?.click()));
    $('#open-thesis-import')?.addEventListener('click', () => switchToTab('projects'));
    $('#complexive-import-file')?.addEventListener('change', event => {
      const file = event.currentTarget.files?.[0];
      if (file) analyzeFile('complexive', file).catch(error => {
        $('#complexive-import-message').textContent = error?.message || String(error);
        $('#complexive-import-message').className = 'academic-error';
      });
    });
    $('#nuclei-import-file')?.addEventListener('change', event => {
      const file = event.currentTarget.files?.[0];
      if (file) analyzeFile('nuclei', file).catch(error => {
        $('#nuclei-import-message').textContent = error?.message || String(error);
        $('#nuclei-import-message').className = 'academic-error';
      });
    });
    void renderReconciliation(true);
  }

  function ensureTab() {
    const tabs = $('#report-tabs');
    const workspace = $('#report-workspace');
    if (!tabs || !workspace || !activeReport()) return;
    let tab = $('#tab-imports');
    if (!tab) {
      tab = document.createElement('div');
      tab.id = 'tab-imports';
      tab.className = 'tab-content';
      const images = $('#tab-images');
      if (images) images.insertAdjacentElement('beforebegin', tab);
      else workspace.appendChild(tab);
    }
    if (!$('[data-tab="imports"]', tabs)) {
      const button = document.createElement('button');
      button.className = 'tab';
      button.dataset.tab = 'imports';
      button.textContent = 'Importaciones';
      const studentsButton = $('[data-tab="students"], [data-tab="roster"]', tabs);
      if (studentsButton) studentsButton.insertAdjacentElement('afterend', button);
      else tabs.appendChild(button);
    }
    if (tab.dataset.academicVersion !== VERSION) {
      tab.dataset.academicVersion = VERSION;
      stateImport.master = null;
      renderShell();
    }
  }

  function injectStyles() {
    if ($('#academic-import-style')) return;
    const style = document.createElement('style');
    style.id = 'academic-import-style';
    style.textContent = `
      .academic-import-shell{display:grid;gap:16px}.academic-main-head,.recon-head{display:flex;justify-content:space-between;align-items:flex-start;gap:14px}.academic-main-head h2,.recon-head h3{margin:0 0 4px}.academic-source-pill{border:1px solid #cfe0f3;background:#f4f8fd;color:#174b7a;border-radius:999px;padding:6px 10px;font-size:11px;font-weight:700;white-space:nowrap}.academic-source-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.academic-source-card{border:1px solid #dbe5ef;background:#fff;border-radius:13px;padding:14px;display:grid;gap:12px;min-width:0}.academic-card-head h3{margin:3px 0 4px;font-size:16px}.academic-card-head p{margin:0;color:#60758a;font-size:12px;line-height:1.45}.academic-drop{display:grid;gap:6px;border:1px dashed #9fb9d4;background:#fbfdff;border-radius:10px;padding:12px;font-size:12px;font-weight:700}.academic-drop input{width:100%}.academic-actions{display:flex;justify-content:flex-end;gap:8px;flex-wrap:wrap}.academic-note{font-size:11px;color:#60758a;line-height:1.45}.academic-error{padding:9px 10px;border:1px solid #f2c1c1;background:#fff6f6;color:#8c2727;border-radius:9px;font-size:11px}.academic-kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));border:1px solid #dbe5ef;border-radius:10px;overflow:hidden;background:#fff}.academic-kpis>div{padding:9px;border-right:1px solid #e8eef4}.academic-kpis>div:last-child{border-right:0}.academic-kpis span{display:block;font-size:9px;color:#60758a}.academic-kpis strong{font-size:16px;color:#102b46}.danger-text{color:#a12a2a!important}.academic-table-wrap{max-height:360px;overflow:auto;border:1px solid #e3eaf1;border-radius:10px}.academic-table{width:100%;border-collapse:collapse;font-size:10px}.academic-table th{position:sticky;top:0;background:#f7f9fc;text-align:left;padding:7px;border-bottom:1px solid #dde6ef;z-index:1}.academic-table td{padding:7px;border-bottom:1px solid #eef3f7;vertical-align:top}.academic-pill{display:inline-flex;border-radius:999px;padding:2px 6px;font-size:9px;font-weight:700}.academic-pill.ok{background:#eaf8ef;color:#08783e}.academic-pill.warn{background:#fff5dc;color:#8a5700}.academic-pill.bad{background:#fdecec;color:#982b2b}.academic-table small{display:block;max-width:360px;margin-top:3px;color:#60758a}.academic-reconciliation{border:1px solid #cfe0f3;background:#f8fbff;border-radius:13px;padding:14px}.recon-kpis{grid-template-columns:repeat(4,minmax(0,1fr));margin-top:10px}.recon-details{margin-top:8px;border-top:1px solid #e1e9f1;padding-top:7px}.recon-details summary{cursor:pointer;font-size:11px;font-weight:700;color:#294b6e}.recon-details div{display:flex;gap:5px;flex-wrap:wrap;margin-top:7px}.recon-details code{font-size:10px;background:#fff;border:1px solid #e1e9f1;border-radius:6px;padding:3px 5px}@media(max-width:980px){.academic-source-grid{grid-template-columns:1fr}.recon-kpis,.academic-kpis{grid-template-columns:repeat(2,1fr)}}`;
    document.head.appendChild(style);
  }

  window.InformtitResultsImport = Object.freeze({
    version:VERSION,
    marker:MARKER,
    sourceType,
    reconcileComplexive,
    reconcileNuclei,
    normalizeModality,
  });

  injectStyles();
  const observer = new MutationObserver(() => queueMicrotask(ensureTab));
  observer.observe(document.documentElement, { childList:true, subtree:true });
  document.addEventListener('DOMContentLoaded', ensureTab, { once:true });
  document.addEventListener('click', event => {
    if (event.target.closest?.('[data-tab="imports"]')) setTimeout(() => { renderShell(); }, 0);
  }, true);
  setTimeout(ensureTab, 0);
})();