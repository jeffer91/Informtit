(() => {
  'use strict';

  const XLSX_SRC = 'https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js';
  const PASS = new Set(['CUMPLE', 'SI', 'SÍ', 'APROBADO', 'OK', 'TRUE', '1']);
  const REQS = [
    ['academico', 'Académico'],
    ['documentacion', 'Documentación'],
    ['financiero', 'Financiero'],
    ['titulacion', 'Titulación'],
    ['practicas', 'Prácticas/Vinculación'],
    ['vinculacion', 'Vinculación'],
    ['seguimientoGraduados', 'Seguimiento a Graduados'],
    ['ingles', 'Inglés'],
    ['actualizacionDatos', 'Actualización de Datos'],
  ];

  const pvc = window.InformtitPVCWorkspace = {
    periodId: '', periodLabel: '', requirementsFile: null, resultsFile: null,
    requirements: [], results: [], merged: [], query: '', filter: 'all', hydrated: false,
  };

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[ch]));
  const normalize = value => String(value ?? '')
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '').toUpperCase()
    .replace(/[^A-Z0-9]+/g, ' ').replace(/\s+/g, ' ').trim();
  const identification = value => String(value ?? '').replace(/\D/g, '').trim();
  const isPass = value => PASS.has(normalize(value));
  const numberOrNull = value => {
    const text = String(value ?? '').trim();
    if (!text || normalize(text) === 'NULL' || text === '—' || text === '-') return null;
    const number = Number(text.replace(',', '.'));
    return Number.isFinite(number) ? number : null;
  };
  const grade = value => Number.isFinite(Number(value)) ? Number(value).toFixed(2).replace('.', ',') : '—';
  const first = (row, aliases) => {
    const index = new Map(Object.entries(row || {}).map(([key, value]) => [normalize(key).replace(/ /g, ''), value]));
    for (const alias of aliases) {
      const value = index.get(normalize(alias).replace(/ /g, ''));
      if (value !== undefined && value !== '') return value;
    }
    return '';
  };
  const isPvc = () => String(state?.activeReport?.report_type || state?.activeReport?.project_summary?.report_type || '').toLowerCase() === 'pvc';
  const currentPeriodId = () => String(state?.activeReport?.firebase_period_id || state?.activeReport?.periodoId || state?.activeReport?.period_id || state?.activeReport?.id || '');
  const careerGroup = value => normalize(value).replace(/\b(ONLINE|EN LINEA|VIRTUAL|PRESENCIAL)\b/g, ' ').replace(/\s+/g, ' ').trim();

  function ensureStyle() {
    if ($('#pvc2-style')) return;
    const style = document.createElement('style');
    style.id = 'pvc2-style';
    style.textContent = `
      .pvc2{display:grid;gap:14px}.pvc2-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.pvc2-head h2{margin:0 0 4px}.pvc2-muted{font-size:12px;color:#60758a}.pvc2-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.pvc2-card{border:1px solid #dce6ef;border-radius:12px;background:#fff;padding:14px}.pvc2-card h3{font-size:14px;margin:0 0 5px}.pvc2-upload{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:10px}.pvc2-upload input{font-size:12px;max-width:100%}.pvc2-state{font-size:11px;margin-top:8px}.pvc2-ok{color:#08783e}.pvc2-warn{color:#a76100}.pvc2-bad{color:#a12a2a}.pvc2-kpis{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));border:1px solid #dce6ef;border-radius:12px;overflow:hidden;background:#fff}.pvc2-kpi{padding:11px;border-right:1px solid #e7edf3}.pvc2-kpi:last-child{border-right:0}.pvc2-kpi span{display:block;font-size:10px;color:#64788a}.pvc2-kpi strong{font-size:18px}.pvc2-flow{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:9px}.pvc2-flow button{background:#fff;border:1px solid #dde6ee;border-radius:10px;padding:11px;text-align:left;cursor:pointer}.pvc2-flow button:hover{background:#f7fafc}.pvc2-flow strong{display:block;font-size:12px;margin-bottom:3px}.pvc2-toolbar{display:flex;gap:7px;align-items:center;flex-wrap:wrap}.pvc2-toolbar input{min-width:260px;padding:8px 10px;border:1px solid #cdd9e4;border-radius:8px}.pvc2-filter{border:1px solid #d5e0ea;background:#fff;border-radius:8px;padding:7px 10px;font-size:11px;cursor:pointer}.pvc2-filter.active{background:#eaf3fb;border-color:#abc7e2;color:#174b7a;font-weight:700}.pvc2-table-wrap{border:1px solid #dce6ef;border-radius:12px;overflow:auto;max-height:560px;background:#fff}.pvc2-table{width:100%;border-collapse:collapse;font-size:11px}.pvc2-table th{position:sticky;top:0;background:#f6f9fc;padding:9px;text-align:left;border-bottom:1px solid #dce6ef;z-index:2}.pvc2-table td{padding:9px;border-bottom:1px solid #edf2f6;vertical-align:middle}.pvc2-table tbody tr{cursor:pointer}.pvc2-table tbody tr:hover{background:#f9fbfd}.pvc2-pill{display:inline-flex;padding:3px 7px;border-radius:999px;font-size:10px;font-weight:700;background:#eef3f7;color:#49647c}.pvc2-pill.ok{background:#e9f8ef;color:#08783e}.pvc2-pill.warn{background:#fff3df;color:#9a5a00}.pvc2-pill.bad{background:#fdecec;color:#9d2727}.pvc2-primary{border:0;background:#1f67a6;color:#fff;border-radius:8px;padding:8px 12px;font-weight:700;cursor:pointer}.pvc2-primary:disabled{opacity:.5}.pvc2-actions{display:flex;justify-content:flex-end;gap:8px}.pvc2-alert{border:1px solid #f1d4a2;background:#fff9ef;color:#7a5a22;border-radius:9px;padding:9px 11px;font-size:11px}.pvc2-alert.ok{border-color:#bce0c9;background:#f1faf4;color:#1c6a3e}.pvc2-drawer{position:fixed;inset:0;background:rgba(10,25,42,.28);z-index:10000;display:flex;justify-content:flex-end}.pvc2-drawer[hidden]{display:none}.pvc2-sheet{width:min(780px,96vw);height:100%;background:#fff;box-shadow:-8px 0 24px rgba(0,0,0,.12);overflow:auto;padding:18px}.pvc2-sheet-head{display:flex;justify-content:space-between;gap:12px;border-bottom:1px solid #e5ecf3;padding-bottom:12px}.pvc2-sheet-head h2{margin:0}.pvc2-close{border:0;background:#f0f4f7;border-radius:8px;padding:7px 10px;cursor:pointer}.pvc2-section{margin-top:16px}.pvc2-section h3{font-size:13px;margin:0 0 8px}.pvc2-info{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.pvc2-info>div{padding:9px;background:#f7f9fb;border-radius:8px;font-size:11px}.pvc2-req{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px}.pvc2-req>div{display:flex;justify-content:space-between;gap:8px;padding:8px;border:1px solid #e3eaf0;border-radius:8px;font-size:11px}.pvc2-tribunal{width:100%;border-collapse:collapse;font-size:11px}.pvc2-tribunal th,.pvc2-tribunal td{border:1px solid #e3eaf0;padding:7px;text-align:left}.pvc2-stat-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}@media(max-width:900px){.pvc2-grid,.pvc2-flow,.pvc2-stat-grid{grid-template-columns:1fr}.pvc2-kpis{grid-template-columns:repeat(2,1fr)}.pvc2-info,.pvc2-req{grid-template-columns:1fr}}`;
    document.head.appendChild(style);
  }

  async function loadXlsx() {
    if (window.XLSX) return window.XLSX;
    await new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = XLSX_SRC;
      script.onload = resolve;
      script.onerror = () => reject(new Error('No se pudo cargar el lector de Excel.'));
      document.head.appendChild(script);
    });
    return window.XLSX;
  }

  async function readRows(file) {
    const XLSX = await loadXlsx();
    const workbook = XLSX.read(await file.arrayBuffer(), { type: 'array', cellDates: false });
    const sheet = workbook.Sheets[workbook.SheetNames[0]];
    return XLSX.utils.sheet_to_json(sheet, { defval: '', raw: false });
  }

  function parseRequirements(rows) {
    const map = new Map();
    rows.forEach(row => {
      const cedula = identification(first(row, ['numeroIdentificacion', 'cedula', 'identificacion']));
      if (!cedula) return;
      const item = {
        cedula,
        nombre: String(first(row, ['Nombres', 'nombre']) || '').trim(),
        codigoCarrera: String(first(row, ['CodigoCarrera', 'codigoCarrera']) || '').trim(),
        carrera: String(first(row, ['NombreCarrera', 'carrera']) || '').trim(),
        academico: first(row, ['Academico']), documentacion: first(row, ['Documentacion']),
        financiero: first(row, ['Financiero']), titulacion: first(row, ['Titulacion']),
        practicas: first(row, ['PrácticasVinculacion', 'PracticasVinculacion']),
        vinculacion: first(row, ['Vinculacion']), seguimientoGraduados: first(row, ['SeguimientoGraduados']),
        ingles: first(row, ['Ingles']), actualizacionDatos: first(row, ['ActualizaciónDatos', 'ActualizacionDatos']),
        aprobacionGeneral: first(row, ['AprobacionTitulacion']),
      };
      item.pending = REQS.filter(([key]) => !isPass(item[key])).map(([, label]) => label);
      item.habilitado = item.pending.length === 0;
      map.set(cedula, item);
    });
    return [...map.values()];
  }

  function parseResults(rows) {
    const map = new Map();
    rows.forEach(row => {
      const cedula = identification(first(row, ['identificacion_estudiante', 'cedula', 'numeroIdentificacion', 'identificacion']));
      if (!cedula) return;
      map.set(cedula, {
        cedula,
        nombre: String(first(row, ['nombre_estudiante', 'Nombres', 'nombre']) || '').trim(),
        periodoFuente: String(first(row, ['periodo_academico', 'periodoAcademico', 'periodo']) || '').trim(),
        modalidad: String(first(row, ['trabajoTitulacion', 'modalidad']) || 'Artículo académico').trim(),
        acta: String(first(row, ['numeroActaGrado', 'numero_acta_grado', 'acta']) || '').trim(),
        fechaActa: String(first(row, ['fechaActaGrado', 'fecha_acta_grado']) || '').trim(),
        tutor: String(first(row, ['nombre_tutor', 'nombreTutor', 'tutor']) || '').trim(),
        lector: String(first(row, ['nombre_lector', 'nombreLector', 'lector']) || '').trim(),
        vocal1: String(first(row, ['nombre_vocal1', 'nombreVocal1', 'vocal1']) || '').trim(),
        vocal2: String(first(row, ['nombre_vocal2', 'nombreVocal2', 'vocal2']) || '').trim(),
        vocal3: String(first(row, ['nombre_vocal3', 'nombreVocal3', 'vocal3']) || '').trim(),
        evaluacionTutor: numberOrNull(first(row, ['evaluacionTutor', 'notaTutor'])),
        evaluacionLector: numberOrNull(first(row, ['evaluacionLector', 'notaLector'])),
        promedioEscrito: numberOrNull(first(row, ['promedio_trabajo_escrito', 'promedioTrabajoEscrito', 'promedioEscrito'])),
        practica1: numberOrNull(first(row, ['sumatoriaEvaluacionPractica_vocal1', 'evaluacionPracticaVocal1'])),
        practica2: numberOrNull(first(row, ['sumatoriaEvaluacionPractica_vocal2', 'evaluacionPracticaVocal2'])),
        practica3: numberOrNull(first(row, ['sumatoriaEvaluacionPractica_vocal3', 'evaluacionPracticaVocal3'])),
        defensa1: numberOrNull(first(row, ['sumatoriaEvaluacionDefensa_vocal1', 'evaluacionDefensaVocal1'])),
        defensa2: numberOrNull(first(row, ['sumatoriaEvaluacionDefensa_vocal2', 'evaluacionDefensaVocal2'])),
        defensa3: numberOrNull(first(row, ['sumatoriaEvaluacionDefensa_vocal3', 'evaluacionDefensaVocal3'])),
        defensaOral: numberOrNull(first(row, ['nota_defensa_oral', 'notaDefensaOral', 'promedioDefensa'])),
        notaFinal: numberOrNull(first(row, ['notaTrabajoTitulacion', 'notaFinal'])),
        promedioAcumulado: numberOrNull(first(row, ['notaPromedioAcumulado', 'promedioAcumulado'])),
        raw: row,
      });
    });
    return [...map.values()];
  }

  function studentStatus(requirement, result) {
    if (!requirement && result) return { key: 'incomplete', label: 'Información incompleta', cls: 'warn' };
    if (requirement && !requirement.habilitado) return { key: 'not_eligible', label: 'No habilitado', cls: 'bad' };
    if (requirement?.habilitado && !result) return { key: 'pending', label: 'Habilitado pendiente de evaluación', cls: 'warn' };
    if (requirement?.habilitado && result) {
      if (!Number.isFinite(Number(result.notaFinal))) return { key: 'pending', label: 'Habilitado pendiente de evaluación', cls: 'warn' };
      return Number(result.notaFinal) >= 7
        ? { key: 'approved', label: 'Habilitado y aprobado', cls: 'ok' }
        : { key: 'failed', label: 'Reprobado', cls: 'bad' };
    }
    return { key: 'incomplete', label: 'Información incompleta', cls: 'warn' };
  }

  function rebuild() {
    const req = new Map(pvc.requirements.map(item => [item.cedula, item]));
    const res = new Map(pvc.results.map(item => [item.cedula, item]));
    pvc.merged = [...new Set([...req.keys(), ...res.keys()])].map(cedula => {
      const requirement = req.get(cedula) || null;
      const result = res.get(cedula) || null;
      return { cedula, requirement, result, status: studentStatus(requirement, result) };
    }).sort((a, b) => String(a.requirement?.nombre || a.result?.nombre || '').localeCompare(String(b.requirement?.nombre || b.result?.nombre || ''), 'es'));
  }

  function metrics() {
    const requirements = pvc.requirements.length;
    const results = pvc.results.length;
    const matched = pvc.merged.filter(row => row.requirement && row.result).length;
    const onlyRequirements = pvc.merged.filter(row => row.requirement && !row.result).length;
    const onlyResults = pvc.merged.filter(row => !row.requirement && row.result).length;
    const eligible = pvc.requirements.filter(row => row.habilitado).length;
    return { requirements, results, matched, onlyRequirements, onlyResults, eligible, pendingRequirements: requirements - eligible };
  }

  function ensureSummaryTab() {
    const tabs = $('#report-tabs');
    const workspace = $('#report-workspace');
    if (!tabs || !workspace) return;
    let content = $('#tab-summary');
    if (!content) {
      content = document.createElement('div');
      content.id = 'tab-summary'; content.className = 'tab-content';
      $('#tab-roster')?.insertAdjacentElement('beforebegin', content);
    }
    let button = tabs.querySelector('[data-tab="summary"]');
    if (!button) {
      button = document.createElement('button'); button.className = 'tab'; button.dataset.tab = 'summary'; button.textContent = 'Control del Informe';
      tabs.prepend(button);
    }
  }

  function ensureExtraTabs() {
    const tabs = $('#report-tabs');
    const workspace = $('#report-workspace');
    if (!tabs || !workspace) return;
    [['statistics', 'Estadísticas'], ['final', 'Informe Final']].forEach(([key, label]) => {
      if (!tabs.querySelector(`[data-tab="${key}"]`)) {
        const button = document.createElement('button'); button.className = 'tab'; button.dataset.tab = key; button.textContent = label;
        const images = tabs.querySelector('[data-tab="images"]'); images ? images.insertAdjacentElement('beforebegin', button) : tabs.appendChild(button);
      }
      if (!$(`#tab-${key}`)) {
        const content = document.createElement('div'); content.id = `tab-${key}`; content.className = 'tab-content';
        $('#tab-images')?.insertAdjacentElement('beforebegin', content) || workspace.appendChild(content);
      }
    });
  }

  function configureTabs() {
    if (!isPvc()) return;
    ensureSummaryTab(); ensureExtraTabs();
    const tabs = $('#report-tabs');
    const labels = { summary: 'Control del Informe', students: 'Estudiantes', roster: 'Requisitos', projects: 'Resultados', schedules: 'Cronogramas', statistics: 'Estadísticas', final: 'Informe Final' };
    Object.entries(labels).forEach(([key, label]) => {
      const button = tabs?.querySelector(`[data-tab="${key}"]`); if (button) { button.hidden = false; button.textContent = label; }
    });
    ['nuclei', 'careers', 'imports', 'general', 'images'].forEach(key => {
      const button = tabs?.querySelector(`[data-tab="${key}"]`); if (button) button.hidden = true;
      const content = $(`#tab-${key}`); if (content) content.hidden = true;
    });
    const modality = $('#report-modality'); if (modality) modality.textContent = 'PVC · Artículo Académico';
  }

  function activateTab(key) {
    const tabs = $('#report-tabs');
    tabs?.querySelectorAll('.tab').forEach(button => button.classList.toggle('active', button.dataset.tab === key));
    $$('.tab-content').forEach(content => content.classList.toggle('active', content.id === `tab-${key}`));
  }

  function renderControl() {
    const host = $('#tab-summary'); if (!host || !isPvc()) return;
    const m = metrics();
    const sourcePeriods = [...new Set(pvc.results.map(row => row.periodoFuente).filter(Boolean))];
    const mismatch = sourcePeriods.length && pvc.periodLabel && !sourcePeriods.some(period => normalize(period) === normalize(pvc.periodLabel));
    host.innerHTML = `<div class="pvc2">
      <div class="pvc2-head"><div><h2>Fuentes de datos del período</h2><div class="pvc2-muted">Esta es la primera pantalla del PVC. Los Excel se leen, normalizan y cruzan únicamente por cédula.</div></div><span class="pvc2-pill">Google Sheets · base principal</span></div>
      <div class="pvc2-grid">
        <section class="pvc2-card"><h3>Excel 1 — Requisitos de Titulación</h3><div class="pvc2-muted">Cédula, nombre, carrera y requisitos del estudiante.</div><div class="pvc2-upload"><input id="pvc2-requirements-file" type="file" accept=".xls,.xlsx"></div>${m.requirements ? `<div class="pvc2-state pvc2-ok"><strong>Archivo cargado ✓</strong><br>${m.requirements} estudiantes detectados · ${m.eligible} cumplen todos · ${m.pendingRequirements} con pendientes</div>` : '<div class="pvc2-state">Sin archivo cargado</div>'}</section>
        <section class="pvc2-card"><h3>Excel 2 — Resultados del Proceso de Titulación</h3><div class="pvc2-muted">Acta, tutor, lector, tribunal, evaluaciones y calificación final.</div><div class="pvc2-upload"><input id="pvc2-results-file" type="file" accept=".xls,.xlsx"></div>${m.results ? `<div class="pvc2-state pvc2-ok"><strong>Archivo cargado ✓</strong><br>${m.results} registros de estudiantes</div>` : '<div class="pvc2-state">Sin archivo cargado</div>'}</section>
      </div>
      ${mismatch ? `<div class="pvc2-alert"><strong>Revisar asignación del período:</strong> el Excel declara ${esc(sourcePeriods.join(' · '))}, mientras el informe activo indica ${esc(pvc.periodLabel)}. Informtit no cambia esa información automáticamente.</div>` : ''}
      <div class="pvc2-kpis"><div class="pvc2-kpi"><span>Requisitos</span><strong>${m.requirements}</strong></div><div class="pvc2-kpi"><span>Resultados</span><strong>${m.results}</strong></div><div class="pvc2-kpi"><span>Coincidencias por cédula</span><strong class="pvc2-ok">${m.matched}</strong></div><div class="pvc2-kpi"><span>Solo en requisitos</span><strong class="pvc2-warn">${m.onlyRequirements}</strong></div><div class="pvc2-kpi"><span>Solo en resultados</span><strong class="${m.onlyResults ? 'pvc2-bad' : ''}">${m.onlyResults}</strong></div></div>
      <div class="pvc2-flow">
        <button data-go="students"><strong>Estudiantes</strong><span class="pvc2-muted">${pvc.merged.length} estudiantes consolidados</span></button>
        <button data-go="roster"><strong>Requisitos de Titulación</strong><span class="pvc2-muted">${m.eligible} cumplen · ${m.pendingRequirements} pendientes</span></button>
        <button data-go="projects"><strong>Resultados de Titulación</strong><span class="pvc2-muted">${m.results} registros académicos</span></button>
        <button data-go="schedules"><strong>Cronogramas de Artículo Académico</strong><span class="pvc2-muted">Varios cronogramas por PVC</span></button>
        <button data-go="statistics"><strong>Estadísticas y análisis</strong><span class="pvc2-muted">Generados desde la base consolidada</span></button>
        <button data-go="final"><strong>Informe Final</strong><span class="pvc2-muted">Validar y generar PDF</span></button>
      </div>
      <div class="pvc2-actions"><button class="pvc2-filter" id="pvc2-inconsistencies">Ver diferencias entre archivos</button><button class="pvc2-primary" id="pvc2-save" ${(!m.requirements || !m.results) ? 'disabled' : ''}>Guardar en Google Sheets</button></div>
    </div>`;
    $('#pvc2-requirements-file')?.addEventListener('change', handleRequirementsFile);
    $('#pvc2-results-file')?.addEventListener('change', handleResultsFile);
    $('#pvc2-inconsistencies')?.addEventListener('click', () => { pvc.filter = 'incomplete'; activateTab('students'); renderStudents(); });
    $('#pvc2-save')?.addEventListener('click', saveAll);
    $$('[data-go]', host).forEach(button => button.onclick = () => { activateTab(button.dataset.go); renderAll(); });
  }

  async function handleRequirementsFile(event) {
    const file = event.currentTarget.files?.[0]; if (!file) return;
    try { pvc.requirements = parseRequirements(await readRows(file)); pvc.requirementsFile = file; rebuild(); renderAll(); }
    catch (error) { toast(error.message || 'No se pudo leer el Excel de requisitos.', true); }
  }

  async function handleResultsFile(event) {
    const file = event.currentTarget.files?.[0]; if (!file) return;
    try { pvc.results = parseResults(await readRows(file)); pvc.resultsFile = file; rebuild(); renderAll(); }
    catch (error) { toast(error.message || 'No se pudo leer el Excel de resultados.', true); }
  }

  function detailPayload(result) {
    return JSON.stringify({
      version: 2, periodoFuente: result.periodoFuente, acta: result.acta, fechaActa: result.fechaActa,
      promedioAcumulado: result.promedioAcumulado,
      vocales: [1, 2, 3].map(numero => ({ numero, nombre: result[`vocal${numero}`], practica: result[`practica${numero}`], defensa: result[`defensa${numero}`] })),
      raw: result.raw,
    });
  }

  async function saveAll() {
    if (!window.InformtitSheets) return toast('No está disponible la conexión con Google Sheets.', true);
    const button = $('#pvc2-save'); if (button) button.disabled = true;
    try {
      const period = pvc.periodId || currentPeriodId(); if (!period) throw new Error('No se pudo identificar el período del informe.');
      const jobs = [];
      pvc.requirements.forEach(row => jobs.push({ action: 'guardar_requisito', data: {
        periodoId: period, cedula: row.cedula, academico: row.academico, documentacion: row.documentacion,
        financiero: row.financiero, titulacion: row.titulacion, practicas: row.practicas, vinculacion: row.vinculacion,
        seguimientoGraduados: row.seguimientoGraduados, ingles: row.ingles, actualizacionDatos: row.actualizacionDatos,
        updatedAt: new Date().toISOString(),
      }}));
      pvc.results.forEach(result => {
        const requirement = pvc.requirements.find(row => row.cedula === result.cedula);
        jobs.push({ action: 'guardar_trabajo_titulacion', data: {
          periodoId: period, cedula: result.cedula, nombre: requirement?.nombre || result.nombre,
          carrera: requirement?.carrera || '', modalidad: 'Articulo academico', titulo: 'Artículo académico',
          notaTutor: result.evaluacionTutor, notaLector: result.evaluacionLector, promedioEscrito: result.promedioEscrito,
          promedioDefensa: result.defensaOral, notaFinal: result.notaFinal,
          estado: Number(result.notaFinal) >= 7 ? 'APROBADO' : 'REPROBADO',
          tutor: result.tutor, lector: result.lector, tribunal1: result.vocal1, tribunal2: result.vocal2, tribunal3: result.vocal3,
          tribunal1Practico: result.practica1, tribunal2Practico: result.practica2, tribunal3Practico: result.practica3,
          tribunal1Defensa: result.defensa1, tribunal2Defensa: result.defensa2, tribunal3Defensa: result.defensa3,
          detalleTribunalJson: detailPayload(result), fuente: pvc.resultsFile?.name || 'PVC Excel', updatedAt: new Date().toISOString(),
        }});
      });
      const responses = await window.InformtitSheets.postMany(jobs, { concurrency: 3 });
      const failed = responses.filter(item => !item.ok);
      if (failed.length) throw new Error(`${failed.length} registros no pudieron guardarse.`);
      toast(`PVC guardado: ${jobs.length} registros actualizados en Google Sheets.`);
      await hydrate(true);
    } catch (error) { toast(error.message || 'No se pudo guardar el PVC.', true); }
    finally { if (button) button.disabled = false; }
  }

  function renderStudents() {
    const host = $('#tab-students'); if (!host || !isPvc()) return;
    const rows = pvc.merged.filter(row => {
      const query = normalize(pvc.query), name = normalize(row.requirement?.nombre || row.result?.nombre || '');
      if (query && !name.includes(query) && !row.cedula.includes(pvc.query.replace(/\D/g, ''))) return false;
      if (pvc.filter === 'all') return true;
      if (pvc.filter === 'eligible') return row.requirement?.habilitado;
      if (pvc.filter === 'requirements') return row.requirement && !row.requirement.habilitado;
      if (pvc.filter === 'approved') return row.status.key === 'approved';
      if (pvc.filter === 'failed') return row.status.key === 'failed';
      if (pvc.filter === 'pending') return row.status.key === 'pending';
      if (pvc.filter === 'incomplete') return !row.requirement || !row.result;
      return true;
    });
    host.innerHTML = `<div class="pvc2"><div class="pvc2-head"><div><h2>Estudiantes</h2><div class="pvc2-muted">Una fila por cédula. La cédula es la única llave de cruce.</div></div><span class="pvc2-pill">${pvc.merged.length} consolidados</span></div><div class="pvc2-toolbar"><input id="pvc2-search" placeholder="Buscar por nombre o cédula" value="${esc(pvc.query)}">${[['all','Todos'],['eligible','Cumplen requisitos'],['requirements','Con pendientes'],['approved','Aprobados'],['failed','Reprobados'],['pending','Sin resultado'],['incomplete','Diferencias entre archivos']].map(([key,label]) => `<button class="pvc2-filter ${pvc.filter === key ? 'active' : ''}" data-filter="${key}">${label}</button>`).join('')}</div><div class="pvc2-table-wrap"><table class="pvc2-table"><thead><tr><th>Estudiante</th><th>Cédula</th><th>Carrera</th><th>Requisitos</th><th>Resultado titulación</th><th>Nota final</th><th>Estado</th></tr></thead><tbody>${rows.map(row => { const req = row.requirement, res = row.result; return `<tr data-student="${row.cedula}"><td>${esc(req?.nombre || res?.nombre || '')}</td><td>${row.cedula}</td><td>${esc(req?.carrera || '—')}</td><td><span class="pvc2-pill ${req?.habilitado ? 'ok' : 'bad'}">${req ? (req.habilitado ? 'Cumple' : 'Pendiente') : 'Sin registro'}</span></td><td>${res ? 'Con resultado' : 'Sin resultado'}</td><td>${grade(res?.notaFinal)}</td><td><span class="pvc2-pill ${row.status.cls}">${esc(row.status.label)}</span></td></tr>`; }).join('')}</tbody></table></div></div>`;
    $('#pvc2-search')?.addEventListener('input', event => { pvc.query = event.currentTarget.value; renderStudents(); });
    $$('[data-filter]', host).forEach(button => button.onclick = () => { pvc.filter = button.dataset.filter; renderStudents(); });
    $$('[data-student]', host).forEach(row => row.onclick = () => openStudent(row.dataset.student));
  }

  function renderRequirements() {
    const host = $('#tab-roster'); if (!host || !isPvc()) return;
    const total = pvc.requirements.length, eligible = pvc.requirements.filter(row => row.habilitado).length;
    host.innerHTML = `<div class="pvc2"><div class="pvc2-head"><div><h2>Requisitos de Titulación</h2><div class="pvc2-muted">${total} estudiantes · ${eligible} habilitados · ${total - eligible} con pendientes</div></div></div><div class="pvc2-grid">${REQS.map(([key,label]) => { const pending = pvc.requirements.filter(row => !isPass(row[key])).length; return `<button class="pvc2-card pvc2-filter" data-requirement="${key}" style="text-align:left"><h3>${esc(label)}</h3><strong>${pending}</strong> pendientes</button>`; }).join('')}</div><div id="pvc2-requirement-list"></div></div>`;
    $$('[data-requirement]', host).forEach(button => button.onclick = () => {
      const key = button.dataset.requirement, label = REQS.find(item => item[0] === key)?.[1] || key;
      const pending = pvc.requirements.filter(row => !isPass(row[key]));
      $('#pvc2-requirement-list').innerHTML = `<section class="pvc2-card"><h3>${esc(label)} — ${pending.length} pendientes</h3><div class="pvc2-table-wrap"><table class="pvc2-table"><thead><tr><th>Estudiante</th><th>Cédula</th><th>Carrera</th><th>Estado</th></tr></thead><tbody>${pending.map(row => `<tr data-student="${row.cedula}"><td>${esc(row.nombre)}</td><td>${row.cedula}</td><td>${esc(row.carrera)}</td><td>${esc(row[key] || 'Pendiente')}</td></tr>`).join('')}</tbody></table></div></section>`;
      $$('[data-student]', $('#pvc2-requirement-list')).forEach(row => row.onclick = () => openStudent(row.dataset.student));
    });
  }

  function renderResults() {
    const host = $('#tab-projects'); if (!host || !isPvc()) return;
    const average = values => { const nums = values.filter(value => Number.isFinite(Number(value))).map(Number); return nums.length ? nums.reduce((a,b) => a+b,0) / nums.length : null; };
    const evaluated = pvc.results.filter(row => Number.isFinite(Number(row.notaFinal))).length;
    const approved = pvc.merged.filter(row => row.status.key === 'approved').length;
    const failed = pvc.merged.filter(row => row.status.key === 'failed').length;
    host.innerHTML = `<div class="pvc2"><div class="pvc2-head"><div><h2>Resultados de Titulación</h2><div class="pvc2-muted">Artículo Académico. La carga se realiza en Control del Informe.</div></div></div><div class="pvc2-kpis"><div class="pvc2-kpi"><span>Evaluados</span><strong>${evaluated}</strong></div><div class="pvc2-kpi"><span>Aprobados</span><strong class="pvc2-ok">${approved}</strong></div><div class="pvc2-kpi"><span>Reprobados</span><strong class="pvc2-bad">${failed}</strong></div><div class="pvc2-kpi"><span>Promedio escrito</span><strong>${grade(average(pvc.results.map(row => row.promedioEscrito)))}</strong></div><div class="pvc2-kpi"><span>Promedio final</span><strong>${grade(average(pvc.results.map(row => row.notaFinal)))}</strong></div></div><div class="pvc2-table-wrap"><table class="pvc2-table"><thead><tr><th>Estudiante</th><th>Cédula</th><th>Carrera</th><th>Tutor</th><th>Lector</th><th>Escrito</th><th>Defensa</th><th>Final</th><th>Estado</th></tr></thead><tbody>${pvc.merged.filter(row => row.result).map(row => `<tr data-student="${row.cedula}"><td>${esc(row.requirement?.nombre || row.result.nombre)}</td><td>${row.cedula}</td><td>${esc(row.requirement?.carrera || '—')}</td><td>${esc(row.result.tutor || '—')}</td><td>${esc(row.result.lector || '—')}</td><td>${grade(row.result.promedioEscrito)}</td><td>${grade(row.result.defensaOral)}</td><td>${grade(row.result.notaFinal)}</td><td><span class="pvc2-pill ${row.status.cls}">${esc(row.status.label)}</span></td></tr>`).join('')}</tbody></table></div></div>`;
    $$('[data-student]', host).forEach(row => row.onclick = () => openStudent(row.dataset.student));
  }

  function renderStatistics() {
    const host = $('#tab-statistics'); if (!host || !isPvc()) return;
    const groups = new Map();
    pvc.merged.forEach(row => {
      const career = row.requirement?.carrera || 'Sin carrera'; const key = careerGroup(career) || 'SIN CARRERA';
      if (!groups.has(key)) groups.set(key, { career, total:0, eligible:0, results:0, approved:0, failed:0, grades:[] });
      const g = groups.get(key); g.total += 1; if (row.requirement?.habilitado) g.eligible += 1; if (row.result) g.results += 1;
      if (row.status.key === 'approved') g.approved += 1; if (row.status.key === 'failed') g.failed += 1; if (Number.isFinite(Number(row.result?.notaFinal))) g.grades.push(Number(row.result.notaFinal));
    });
    const rows = [...groups.values()].sort((a,b) => a.career.localeCompare(b.career,'es'));
    host.innerHTML = `<div class="pvc2"><div class="pvc2-head"><div><h2>Estadísticas y análisis</h2><div class="pvc2-muted">Todos los indicadores se calculan desde la misma base consolidada por cédula.</div></div></div><div class="pvc2-table-wrap"><table class="pvc2-table"><thead><tr><th>Carrera</th><th>Estudiantes</th><th>Habilitados</th><th>Con resultado</th><th>Aprobados</th><th>Reprobados</th><th>Promedio final</th></tr></thead><tbody>${rows.map(row => { const avg = row.grades.length ? row.grades.reduce((a,b)=>a+b,0)/row.grades.length : null; return `<tr><td>${esc(row.career)}</td><td>${row.total}</td><td>${row.eligible}</td><td>${row.results}</td><td>${row.approved}</td><td>${row.failed}</td><td>${grade(avg)}</td></tr>`; }).join('')}</tbody></table></div></div>`;
  }

  function renderFinal() {
    const host = $('#tab-final'); if (!host || !isPvc()) return;
    const m = metrics();
    const ready = m.requirements > 0 && m.results > 0 && m.onlyResults === 0;
    host.innerHTML = `<div class="pvc2"><div class="pvc2-head"><div><h2>Informe Final</h2><div class="pvc2-muted">Validación final antes de generar el PDF institucional.</div></div><span class="pvc2-pill ${ready ? 'ok' : 'warn'}">${ready ? 'Datos principales listos' : 'Revisión pendiente'}</span></div><div class="pvc2-grid"><section class="pvc2-card"><h3>Fuentes de datos</h3><div class="pvc2-muted">Requisitos: ${m.requirements ? '✓' : 'pendiente'} · Resultados: ${m.results ? '✓' : 'pendiente'}</div></section><section class="pvc2-card"><h3>Consolidación</h3><div class="pvc2-muted">${m.matched} coincidencias · ${m.onlyRequirements} sin resultado · ${m.onlyResults} solo en resultados</div></section></div><div class="pvc2-actions"><button class="pvc2-primary" id="pvc2-generate">Validar y generar PDF</button></div></div>`;
    $('#pvc2-generate')?.addEventListener('click', () => $('#open-generate-pdfs')?.click());
  }

  function criteria(raw, vocal) {
    return [
      ['Diseño', first(raw, [`diseño_vocal${vocal}`, `diseno_vocal${vocal}`])],
      ['Construcción', first(raw, [`construccion_vocal${vocal}`])],
      ['Funcionamiento', first(raw, [`funcionamiento_vocal${vocal}`])],
      ['Aplicación', first(raw, [`aplicacion_vocal${vocal}`])],
      ['Sustento marco teórico', first(raw, [`sustentoMarcoTeorico_vocal${vocal}`])],
      ['Sustento propuesta', first(raw, [`sustentoPropuesta_vocal${vocal}`])],
      ['Utilización de recursos', first(raw, [`utilizacionRecursos_vocal${vocal}`])],
      ['Solvencia en preguntas', first(raw, [`solvenciaPreguntas_vocal${vocal}`])],
    ].filter(([, value]) => String(value ?? '').trim() !== '');
  }

  function openStudent(cedula) {
    const row = pvc.merged.find(item => item.cedula === cedula); if (!row) return;
    const req = row.requirement, res = row.result;
    let drawer = $('#pvc2-drawer');
    if (!drawer) { drawer = document.createElement('div'); drawer.id = 'pvc2-drawer'; drawer.className = 'pvc2-drawer'; document.body.appendChild(drawer); }
    const reqMarkup = req ? REQS.map(([key,label]) => `<div><span>${esc(label)}</span><strong class="${isPass(req[key]) ? 'pvc2-ok' : 'pvc2-bad'}">${isPass(req[key]) ? '✓ Cumple' : 'Pendiente'}</strong></div>`).join('') : '<div>Sin información de requisitos</div>';
    const tribunal = res ? [1,2,3].map(vocal => {
      const detail = criteria(res.raw || {}, vocal);
      return `<tr><td>Vocal ${vocal}</td><td>${esc(res[`vocal${vocal}`] || '—')}</td><td>${grade(res[`practica${vocal}`])}</td><td>${grade(res[`defensa${vocal}`])}</td></tr>${detail.length ? `<tr><td colspan="4"><details><summary>Ver detalle del vocal ${vocal}</summary><div class="pvc2-req">${detail.map(([label,value]) => `<div><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`).join('')}</div></details></td></tr>` : ''}`;
    }).join('') : '';
    drawer.hidden = false;
    drawer.innerHTML = `<aside class="pvc2-sheet"><div class="pvc2-sheet-head"><div><h2>${esc(req?.nombre || res?.nombre || 'Estudiante')}</h2><div class="pvc2-muted">${cedula} · ${esc(req?.codigoCarrera || '')} · ${esc(req?.carrera || '')}</div></div><button class="pvc2-close" id="pvc2-close">Cerrar</button></div><section class="pvc2-section"><h3>1. Información general</h3><div class="pvc2-info"><div><strong>Nombre</strong><br>${esc(req?.nombre || res?.nombre || '—')}</div><div><strong>Cédula</strong><br>${cedula}</div><div><strong>Carrera</strong><br>${esc(req?.carrera || '—')}</div><div><strong>Período</strong><br>${esc(res?.periodoFuente || pvc.periodLabel || '—')}</div><div><strong>Modalidad</strong><br>${esc(res?.modalidad || 'Artículo académico')}</div></div></section><section class="pvc2-section"><h3>2. Requisitos de titulación</h3><div class="pvc2-alert"><strong>Estado de requisitos:</strong> ${req ? (req.habilitado ? 'HABILITADO' : `NO HABILITADO · ${req.pending.length} requisitos pendientes`) : 'SIN INFORMACIÓN'}</div><div class="pvc2-req" style="margin-top:8px">${reqMarkup}</div></section><section class="pvc2-section"><h3>3. Trabajo de titulación</h3><div class="pvc2-info"><div><strong>Modalidad</strong><br>${esc(res?.modalidad || 'Artículo académico')}</div><div><strong>Tutor</strong><br>${esc(res?.tutor || '—')}</div><div><strong>Lector</strong><br>${esc(res?.lector || '—')}</div><div><strong>Acta de grado</strong><br>${esc(res?.acta || '—')}</div><div><strong>Fecha de acta</strong><br>${esc(res?.fechaActa || '—')}</div></div></section><section class="pvc2-section"><h3>4. Tribunal</h3>${res ? `<table class="pvc2-tribunal"><thead><tr><th>Rol</th><th>Nombre</th><th>Evaluación práctica</th><th>Evaluación defensa</th></tr></thead><tbody>${tribunal}</tbody></table>` : 'Sin resultado cargado'}</section><section class="pvc2-section"><h3>5. Evaluaciones</h3><div class="pvc2-info"><div><strong>Evaluación tutor</strong><br>${grade(res?.evaluacionTutor)}</div><div><strong>Evaluación lector</strong><br>${grade(res?.evaluacionLector)}</div><div><strong>Promedio trabajo escrito</strong><br>${grade(res?.promedioEscrito)}</div><div><strong>Defensa oral</strong><br>${grade(res?.defensaOral)}</div><div><strong>Nota trabajo de titulación</strong><br>${grade(res?.notaFinal)}</div><div><strong>Promedio acumulado</strong><br>${grade(res?.promedioAcumulado)}</div></div></section><section class="pvc2-section"><div class="pvc2-alert ${row.status.cls === 'ok' ? 'ok' : ''}"><strong>Estado automático:</strong> ${esc(row.status.label)}</div></section></aside>`;
    $('#pvc2-close', drawer).onclick = () => drawer.hidden = true;
    drawer.onclick = event => { if (event.target === drawer) drawer.hidden = true; };
  }

  function decodeSaved(row) {
    let detail = {};
    try { detail = row.detalleTribunalJson ? JSON.parse(row.detalleTribunalJson) : {}; } catch {}
    const vocals = Array.isArray(detail.vocales) ? detail.vocales : [];
    return {
      cedula: identification(row.cedula), nombre: row.nombre || '', periodoFuente: detail.periodoFuente || '', modalidad: row.modalidad || 'Artículo académico',
      acta: detail.acta || '', fechaActa: detail.fechaActa || '', tutor: row.tutor || '', lector: row.lector || '',
      vocal1: row.tribunal1 || vocals[0]?.nombre || '', vocal2: row.tribunal2 || vocals[1]?.nombre || '', vocal3: row.tribunal3 || vocals[2]?.nombre || '',
      evaluacionTutor: numberOrNull(row.notaTutor), evaluacionLector: numberOrNull(row.notaLector), promedioEscrito: numberOrNull(row.promedioEscrito),
      practica1: numberOrNull(row.tribunal1Practico ?? vocals[0]?.practica), practica2: numberOrNull(row.tribunal2Practico ?? vocals[1]?.practica), practica3: numberOrNull(row.tribunal3Practico ?? vocals[2]?.practica),
      defensa1: numberOrNull(row.tribunal1Defensa ?? vocals[0]?.defensa), defensa2: numberOrNull(row.tribunal2Defensa ?? vocals[1]?.defensa), defensa3: numberOrNull(row.tribunal3Defensa ?? vocals[2]?.defensa),
      defensaOral: numberOrNull(row.promedioDefensa), notaFinal: numberOrNull(row.notaFinal), promedioAcumulado: numberOrNull(detail.promedioAcumulado), raw: detail.raw || {},
    };
  }

  function renderAll() {
    if (!isPvc()) return;
    ensureStyle(); configureTabs(); renderControl(); renderStudents(); renderRequirements(); renderResults(); renderStatistics(); renderFinal();
  }

  async function hydrate(force = false) {
    if (!isPvc() || !window.InformtitSheets || (pvc.hydrated && !force)) return;
    pvc.periodId = currentPeriodId(); pvc.periodLabel = ($('#report-period')?.textContent || '').trim();
    try {
      const [requirementsData, resultsData] = await Promise.all([
        window.InformtitSheets.requisitos(pvc.periodId), window.InformtitSheets.trabajoTitulacion(pvc.periodId)
      ]);
      pvc.requirements = (requirementsData.requisitos || []).map(row => {
        const item = { ...row, cedula: identification(row.cedula) };
        item.pending = REQS.filter(([key]) => !isPass(item[key])).map(([,label]) => label); item.habilitado = item.pending.length === 0; return item;
      }).filter(row => row.cedula);
      pvc.results = (resultsData.trabajoTitulacion || []).filter(row => normalize(row.modalidad || row.titulo).includes('ARTICULO')).map(decodeSaved).filter(row => row.cedula);
      pvc.hydrated = true; rebuild(); renderAll();
    } catch (error) { console.warn('[PVC v2] No se pudo hidratar desde Google Sheets:', error); renderAll(); }
  }

  function boot() {
    if (!isPvc()) return;
    pvc.periodId = currentPeriodId(); pvc.periodLabel = ($('#report-period')?.textContent || '').trim();
    renderAll(); hydrate();
  }

  const previousRenderReport = window.renderReport;
  if (typeof previousRenderReport === 'function') {
    window.renderReport = async function(...args) {
      const result = await previousRenderReport.apply(this, args);
      pvc.hydrated = false;
      setTimeout(boot, 140);
      return result;
    };
  }
  document.addEventListener('click', event => {
    const tab = event.target.closest?.('.tab');
    if (tab && isPvc()) setTimeout(renderAll, 30);
  });
  new MutationObserver(() => { if (isPvc()) configureTabs(); }).observe(document.body, { childList: true, subtree: true });
})();
