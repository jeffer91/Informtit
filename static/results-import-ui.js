(() => {
  'use strict';

  const SHEETJS_SRC = 'https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js';
  const state = {
    workbook: null,
    fileName: '',
    periodos: [],
    students: [],
    matriculas: [],
    candidates: [],
    complexivo: [],
    trabajos: [],
    loadingOfficial: false,
    saving: false,
  };

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

  function esc(value = '') {
    return String(value).replace(/[&<>'\"]/g, char => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '\"': '&quot;',
    }[char]));
  }

  function normalize(value = '') {
    return String(value ?? '')
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .toUpperCase()
      .replace(/[^A-Z0-9]+/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  }

  function canonicalCareer(value = '') {
    let text = normalize(value)
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
      'TECNICO SUPERIOR EN ENFERMERIA': 'ENFERMERÍA',
      'ESTETICA INTEGRAL': 'ESTÉTICA INTEGRAL',
      'GESTION DEL TALENTO HUMANO': 'GESTIÓN DEL TALENTO HUMANO',
      'MARKETING DIGITAL Y COMERCIO ELECTRONICO': 'MARKETING DIGITAL Y COMERCIO ELECTRÓNICO',
      'REDES Y TELECOMUNICACIONES': 'REDES Y TELECOMUNICACIONES',
      'SEGURIDAD CIUDADANA Y ORDEN PUBLICO': 'SEGURIDAD CIUDADANA Y ORDEN PÚBLICO',
    };
    if (text.includes('REDES') && text.includes('TELECOMUNICACIONES')) return 'REDES Y TELECOMUNICACIONES';
    return aliases[text] || text;
  }

  function careerKey(value = '') {
    return normalize(canonicalCareer(value));
  }

  function modalityFrom(value = '') {
    const key = normalize(value);
    return key.includes('ONLINE') || key.includes('EN LINEA') || key.includes('VIRTUAL') ? 'en_linea' : 'presencial';
  }

  function numberOrNull(value) {
    if (value === null || value === undefined) return null;
    const text = String(value).trim();
    if (!text || normalize(text) === 'NULL' || text === '-' || text === '—') return null;
    const number = Number(text.replace(',', '.'));
    return Number.isFinite(number) ? number : null;
  }

  function round2(value) {
    return value === null || value === undefined || !Number.isFinite(Number(value))
      ? null
      : Math.round(Number(value) * 100) / 100;
  }

  function average(values) {
    const nums = values.filter(value => Number.isFinite(Number(value))).map(Number);
    return nums.length ? nums.reduce((sum, value) => sum + value, 0) / nums.length : null;
  }

  function formatGrade(value) {
    return Number.isFinite(Number(value)) ? Number(value).toFixed(2).replace('.', ',') : '—';
  }

  function periodKey(value = '') {
    return normalize(value)
      .replace(/\bDE\b/g, ' ')
      .replace(/\bA\b/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  }

  function activePeriodText() {
    return ($('#report-period')?.textContent || '').trim();
  }

  function selectedPeriodId() {
    return $('#results-import-period')?.value || '';
  }

  function activePeriodMatch() {
    const wanted = periodKey(activePeriodText());
    if (!wanted) return '';
    const match = state.periodos.find(period => {
      const labels = [period.nombre, period.label, period.periodoId, period.id]
        .filter(Boolean)
        .map(periodKey);
      return labels.includes(wanted);
    });
    return String(match?.periodoId || match?.id || '');
  }

  function injectStyles() {
    if ($('#results-import-style')) return;
    const style = document.createElement('style');
    style.id = 'results-import-style';
    style.textContent = `
      .results-import-shell{display:grid;gap:16px}.results-import-head{display:flex;justify-content:space-between;align-items:flex-start;gap:16px}.results-import-head h2{margin:0 0 4px}.results-source-pill{white-space:nowrap;border:1px solid #cfe0f3;background:#f4f8fd;color:#174b7a;border-radius:999px;padding:6px 10px;font-size:12px;font-weight:700}.results-import-grid{display:grid;grid-template-columns:minmax(220px,320px) minmax(300px,1fr);gap:12px;align-items:end}.results-import-grid label{display:grid;gap:6px;font-size:12px;color:#294b6e}.results-import-grid select,.results-import-grid input[type=file]{width:100%;box-sizing:border-box;border:1px solid #c8d6e6;border-radius:9px;background:white;padding:10px;font:inherit}.results-drop{border:1px dashed #9fb9d4;border-radius:12px;padding:14px;background:#fbfdff}.results-import-summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));border:1px solid #dbe5ef;border-radius:12px;overflow:hidden;background:white}.results-import-summary>div{padding:12px;border-right:1px solid #e5ecf3}.results-import-summary>div:last-child{border-right:0}.results-import-summary span{display:block;font-size:11px;color:#60758a;margin-bottom:4px}.results-import-summary strong{font-size:20px;color:#102b46}.results-import-summary strong.warn{color:#b86200}.results-preview-panel{border:1px solid #dbe5ef;border-radius:12px;background:white;overflow:hidden}.results-preview-title{display:flex;justify-content:space-between;gap:12px;align-items:center;padding:12px 14px;border-bottom:1px solid #e5ecf3}.results-preview-title h3{margin:0;font-size:14px}.results-preview-body{padding:0;overflow:auto;max-height:420px}.results-preview-table{width:100%;border-collapse:collapse;font-size:12px}.results-preview-table th{position:sticky;top:0;background:#f6f9fc;text-align:left;color:#47647f;padding:9px 10px;border-bottom:1px solid #dbe5ef;z-index:1}.results-preview-table td{padding:9px 10px;border-bottom:1px solid #edf2f7;vertical-align:middle}.results-preview-table tr:last-child td{border-bottom:0}.results-preview-table select{max-width:280px;width:100%;padding:6px;border:1px solid #c8d6e6;border-radius:7px}.match-ok{color:#08783e;font-weight:700}.match-warn{color:#b86200;font-weight:700}.results-import-actions{display:flex;justify-content:flex-end;align-items:center;gap:10px}.results-import-progress{height:8px;background:#e7eef5;border-radius:999px;overflow:hidden;min-width:220px}.results-import-progress>span{display:block;height:100%;background:#2470b8;width:0%;transition:width .15s ease}.results-note{font-size:12px;color:#60758a}.results-error-box{border:1px solid #f3c6c6;background:#fff7f7;color:#8c2727;border-radius:10px;padding:10px 12px}.results-success-box{border:1px solid #b8dfc7;background:#f4fbf6;color:#176137;border-radius:10px;padding:10px 12px}.results-empty{padding:18px;color:#60758a;text-align:center}.results-tabs-mini{display:flex;gap:6px}.results-tabs-mini button{border:1px solid #d4e0eb;background:white;border-radius:8px;padding:6px 9px;font-size:12px;cursor:pointer}.results-tabs-mini button.active{background:#eaf3fb;border-color:#abc7e2;color:#174b7a;font-weight:700}@media(max-width:900px){.results-import-grid{grid-template-columns:1fr}.results-import-summary{grid-template-columns:repeat(2,1fr)}.results-import-summary>div:nth-child(2){border-right:0}.results-import-summary>div:nth-child(-n+2){border-bottom:1px solid #e5ecf3}}`;
    document.head.appendChild(style);
  }

  function ensureTab() {
    const tabs = $('#report-tabs');
    const workspace = $('#report-workspace');
    if (!tabs || !workspace) return;

    if (!$('#tab-imports')) {
      const content = document.createElement('div');
      content.id = 'tab-imports';
      content.className = 'tab-content';
      const images = $('#tab-images');
      if (images) images.insertAdjacentElement('beforebegin', content);
      else workspace.appendChild(content);
    }

    if (!$('[data-tab="imports"]', tabs)) {
      const button = document.createElement('button');
      button.className = 'tab';
      button.dataset.tab = 'imports';
      button.textContent = 'Importaciones';
      const studentsButton = $('[data-tab="students"]', tabs);
      if (studentsButton) studentsButton.insertAdjacentElement('afterend', button);
      else tabs.appendChild(button);
    }

    const tab = $('#tab-imports');
    if (tab && !tab.dataset.rendered) {
      tab.dataset.rendered = '1';
      renderShell();
      initializeData().catch(showError);
    }
  }

  function renderShell() {
    injectStyles();
    const tab = $('#tab-imports');
    if (!tab) return;
    tab.innerHTML = `
      <div class="panel results-import-shell">
        <div class="results-import-head">
          <div>
            <h2>Importar resultados académicos</h2>
            <p>Cargue un solo Excel con las hojas <strong>EXÁMEN COMPLEXIVO</strong> y <strong>Trabajo_Titulacion</strong>. Informtit concilia a los estudiantes y guarda los resultados en la base principal.</p>
          </div>
          <span class="results-source-pill">Google Sheets · base principal</span>
        </div>
        <div class="results-import-grid">
          <label>Período
            <select id="results-import-period"><option value="">Cargando períodos…</option></select>
          </label>
          <label class="results-drop">Archivo de resultados (.xlsx / .xls)
            <input id="results-import-file" type="file" accept=".xlsx,.xls,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel">
          </label>
        </div>
        <div class="results-note" id="results-import-period-note">Se intentará seleccionar automáticamente el período del informe activo.</div>
        <div id="results-import-message"></div>
        <div id="results-import-preview" class="results-empty">Seleccione el archivo para analizarlo antes de guardar.</div>
      </div>`;

    $('#results-import-file').addEventListener('change', event => {
      const file = event.currentTarget.files?.[0];
      if (file) analyzeFile(file).catch(showError);
    });
    $('#results-import-period').addEventListener('change', async () => {
      if (!state.workbook) return;
      await loadOfficialData(true);
      reconcileAll();
      renderPreview();
    });
  }

  async function initializeData() {
    if (!window.InformtitSheets) throw new Error('No se cargó la conexión con Google Sheets.');
    const [ping, periodData] = await Promise.all([
      window.InformtitSheets.ping(),
      window.InformtitSheets.periodos(),
    ]);
    if (!ping?.ok) throw new Error('Google Sheets no respondió correctamente.');
    state.periodos = periodData.periodos || [];
    renderPeriods();
  }

  function renderPeriods() {
    const select = $('#results-import-period');
    if (!select) return;
    const matched = activePeriodMatch();
    select.innerHTML = '<option value="">Seleccione un período</option>' + state.periodos.map(period => {
      const id = String(period.periodoId || period.id || '');
      const label = String(period.nombre || period.label || id);
      return `<option value="${esc(id)}" ${id === matched ? 'selected' : ''}>${esc(label)}</option>`;
    }).join('');
    const note = $('#results-import-period-note');
    if (note) {
      note.textContent = matched
        ? `Período conciliado con el informe activo: ${activePeriodText()}.`
        : 'Seleccione el período al que pertenecen estas calificaciones.';
    }
  }

  async function loadSheetJS() {
    if (window.XLSX) return window.XLSX;
    await new Promise((resolve, reject) => {
      const existing = document.querySelector(`script[src="${SHEETJS_SRC}"]`);
      if (existing) {
        existing.addEventListener('load', resolve, { once: true });
        existing.addEventListener('error', () => reject(new Error('No se pudo cargar el lector de Excel.')), { once: true });
        return;
      }
      const script = document.createElement('script');
      script.src = SHEETJS_SRC;
      script.onload = resolve;
      script.onerror = () => reject(new Error('No se pudo cargar el lector de Excel.'));
      document.head.appendChild(script);
    });
    return window.XLSX;
  }

  function findSheet(workbook, expected) {
    const target = normalize(expected).replace(/ /g, '');
    return workbook.SheetNames.find(name => normalize(name).replace(/ /g, '') === target) || null;
  }

  function sheetRows(workbook, sheetName) {
    return window.XLSX.utils.sheet_to_json(workbook.Sheets[sheetName], {
      defval: '',
      raw: false,
    });
  }

  async function analyzeFile(file) {
    clearMessage();
    const periodId = selectedPeriodId();
    if (!periodId) throw new Error('Seleccione primero el período del informe.');
    const XLSX = await loadSheetJS();
    const buffer = await file.arrayBuffer();
    const workbook = XLSX.read(buffer, { type: 'array', cellDates: false });
    const complexName = findSheet(workbook, 'EXAMEN COMPLEXIVO');
    const workName = findSheet(workbook, 'TRABAJO TITULACION');
    if (!complexName && !workName) {
      throw new Error('El archivo no contiene las hojas EXÁMEN COMPLEXIVO ni Trabajo_Titulacion.');
    }

    state.workbook = workbook;
    state.fileName = file.name;
    state.complexivo = complexName ? parseComplexivo(sheetRows(workbook, complexName)) : [];
    state.trabajos = workName ? parseTrabajo(sheetRows(workbook, workName)) : [];

    await loadOfficialData(true);
    reconcileAll();
    renderPreview();
  }

  function parseComplexivo(rows) {
    return rows
      .filter(row => normalize(row.trabajoTitulacion || 'EXAMEN COMPLEXIVO').includes('EXAMEN COMPLEXIVO'))
      .map((row, index) => {
        const practical = numberOrNull(row.notaPractico);
        const theory = numberOrNull(row.notaTeorico);
        const supplementary = numberOrNull(row.notaSupletorio);
        const ordinary = average([practical, theory]);
        const finalGrade = supplementary ?? ordinary;
        return {
          kind: 'complexivo',
          sourceIndex: index + 2,
          nombre: String(row.nombre_estudiante || '').trim(),
          carreraRaw: String(row.nombre_carrera || '').trim(),
          carrera: canonicalCareer(row.nombre_carrera),
          modalidad: modalityFrom(row.nombre_carrera),
          notaPractico: practical,
          notaTeorico: theory,
          notaSupletorio: supplementary,
          notaPromedioAcumulado: numberOrNull(row.notaPromedioAcumulado),
          notaOrdinaria: round2(ordinary),
          notaFinal: round2(finalGrade),
          estado: Number.isFinite(finalGrade) ? (finalGrade >= 7 ? 'APROBADO' : 'REPROBADO') : 'SIN NOTA',
          _matched: null,
          _suggestions: [],
        };
      })
      .filter(item => item.nombre);
  }

  function parseTrabajo(rows) {
    const groups = new Map();
    rows.forEach((row, index) => {
      const name = String(row.nombre_estudiante || '').trim();
      if (!name) return;
      const careerRaw = String(row.nombre_carrera || '').trim();
      const key = `${normalize(name)}|${careerKey(careerRaw)}`;
      if (!groups.has(key)) groups.set(key, { name, careerRaw, rows: [], firstIndex: index + 2 });
      groups.get(key).rows.push(row);
    });

    return [...groups.values()].map(group => {
      const role = wanted => group.rows.find(row => normalize(row.persona_califica) === normalize(wanted)) || null;
      const tutor = role('Tutor');
      const lector = role('Lector');
      const tribunals = ['Tribunal_1', 'Tribunal_2', 'Tribunal_3'].map(role).filter(Boolean);
      const notaTutor = numberOrNull(tutor?.evaluacionTutor);
      const notaLector = numberOrNull(lector?.evaluacionLector);
      const promedioEscrito = average([notaTutor, notaLector]);
      const tribunalComponents = tribunals.map(row => average([
        numberOrNull(row.sumatoriaEvaluacionPractica),
        numberOrNull(row.sumatoriaEvaluacionDefensa),
      ]));
      const promedioDefensa = average(tribunalComponents);
      const finalGrade = Number.isFinite(promedioEscrito) && Number.isFinite(promedioDefensa)
        ? (promedioEscrito * 0.70) + (promedioDefensa * 0.30)
        : null;
      const approved = Number.isFinite(promedioEscrito) && Number.isFinite(promedioDefensa)
        ? promedioEscrito >= 7 && promedioDefensa >= 7
        : false;

      const tribunalData = tribunals.map((row, index) => ({
        index: index + 1,
        docente: String(row.nombre_docente || '').trim(),
        practica: numberOrNull(row.sumatoriaEvaluacionPractica),
        defensa: numberOrNull(row.sumatoriaEvaluacionDefensa),
        diseño: numberOrNull(row['diseño']),
        construccion: numberOrNull(row.construccion),
        funcionamiento: numberOrNull(row.funcionamiento),
        aplicacion: numberOrNull(row.aplicacion),
        sustentoMarcoTeorico: numberOrNull(row.sustentoMarcoTeorico),
        sustentoPropuesta: numberOrNull(row.sustentoPropuesta),
        utilizacionRecursos: numberOrNull(row.utilizacionRecursos),
        solvenciaPreguntas: numberOrNull(row.solvenciaPreguntas),
      }));

      return {
        kind: 'trabajo',
        sourceIndex: group.firstIndex,
        nombre: group.name,
        carreraRaw: group.careerRaw,
        carrera: canonicalCareer(group.careerRaw),
        modalidad: modalityFrom(group.careerRaw),
        tutor: String(tutor?.nombre_docente || '').trim(),
        lector: String(lector?.nombre_docente || '').trim(),
        notaTutor: round2(notaTutor),
        notaLector: round2(notaLector),
        promedioEscrito: round2(promedioEscrito),
        promedioDefensa: round2(promedioDefensa),
        notaFinal: round2(finalGrade),
        estado: finalGrade === null ? 'INCOMPLETO' : (approved ? 'APROBADO' : 'REPROBADO'),
        tribunales: tribunalData,
        evaluadoresDetectados: group.rows.length,
        _matched: null,
        _suggestions: [],
      };
    });
  }

  async function loadOfficialData(force = false) {
    if (state.loadingOfficial) return;
    const periodId = selectedPeriodId();
    if (!periodId) return;
    if (!force && state.candidates.length) return;
    state.loadingOfficial = true;
    try {
      const [studentData, matriculaData] = await Promise.all([
        window.InformtitSheets.estudiantes(),
        window.InformtitSheets.matriculas(periodId),
      ]);
      state.students = studentData.estudiantes || [];
      state.matriculas = matriculaData.matriculas || [];
      state.candidates = buildCandidates(state.students, state.matriculas);
    } finally {
      state.loadingOfficial = false;
    }
  }

  function buildCandidates(students, matriculas) {
    const studentById = new Map(students.map(student => [String(student.cedula || '').trim(), student]));
    const activeMats = (matriculas || []).filter(mat => !['TRUE', '1', 'SI', 'SÍ'].includes(normalize(mat.retirado)));
    if (activeMats.length) {
      return activeMats.map(mat => {
        const cedula = String(mat.cedula || '').trim();
        const student = studentById.get(cedula) || {};
        return candidateFrom({ ...student, ...mat, cedula, nombre: student.nombre || mat.nombre });
      }).filter(candidate => candidate.cedula && candidate.nombre);
    }
    return students.map(candidateFrom).filter(candidate => candidate.cedula && candidate.nombre);
  }

  function candidateFrom(source) {
    return {
      cedula: String(source.cedula || '').trim(),
      nombre: String(source.nombre || source.nombres || '').trim(),
      carrera: canonicalCareer(source.carrera || source.nombreCarrera || ''),
      modalidad: String(source.modalidad || '').trim() || modalityFrom(source.carrera || source.nombreCarrera || ''),
      sede: String(source.sede || '').trim(),
    };
  }

  function scoreName(sourceName, candidateName) {
    const a = normalize(sourceName).split(' ').filter(Boolean);
    const b = normalize(candidateName).split(' ').filter(Boolean);
    if (!a.length || !b.length) return 0;
    const setA = new Set(a);
    const setB = new Set(b);
    const common = [...setA].filter(token => setB.has(token)).length;
    return common / Math.max(setA.size, setB.size);
  }

  function reconcileItem(item) {
    const name = normalize(item.nombre);
    const career = careerKey(item.carrera);
    const modality = item.modalidad;
    const sameName = state.candidates.filter(candidate => normalize(candidate.nombre) === name);
    let matches = sameName.filter(candidate => careerKey(candidate.carrera) === career && (!modality || !candidate.modalidad || candidate.modalidad === modality));
    if (matches.length !== 1) matches = sameName.filter(candidate => careerKey(candidate.carrera) === career);
    if (matches.length === 1) {
      item._matched = matches[0];
      item._suggestions = [];
      return;
    }

    item._matched = null;
    const sameCareer = state.candidates.filter(candidate => careerKey(candidate.carrera) === career);
    item._suggestions = sameCareer
      .map(candidate => ({ candidate, score: scoreName(item.nombre, candidate.nombre) }))
      .filter(entry => entry.score > 0.25)
      .sort((a, b) => b.score - a.score)
      .slice(0, 6)
      .map(entry => entry.candidate);
  }

  function reconcileAll() {
    [...state.complexivo, ...state.trabajos].forEach(reconcileItem);
  }

  function allItems() {
    return [...state.complexivo, ...state.trabajos];
  }

  function countMatched(items) {
    return items.filter(item => item._matched).length;
  }

  function renderPreview() {
    const root = $('#results-import-preview');
    if (!root) return;
    const items = allItems();
    if (!state.workbook) {
      root.className = 'results-empty';
      root.innerHTML = 'Seleccione el archivo para analizarlo antes de guardar.';
      return;
    }

    const matched = countMatched(items);
    const review = items.length - matched;
    root.className = '';
    root.innerHTML = `
      <div class="results-import-summary">
        <div><span>Examen Complexivo</span><strong>${state.complexivo.length}</strong></div>
        <div><span>Trabajo de Titulación</span><strong>${state.trabajos.length}</strong></div>
        <div><span>Conciliados</span><strong>${matched}</strong></div>
        <div><span>Por revisar</span><strong class="${review ? 'warn' : ''}">${review}</strong></div>
      </div>
      <div class="results-preview-panel">
        <div class="results-preview-title">
          <div><h3>${esc(state.fileName)}</h3><div class="results-note">${items.length} estudiantes/resultados listos para revisar</div></div>
          <div class="results-tabs-mini">
            <button type="button" data-import-filter="all" class="active">Todos</button>
            <button type="button" data-import-filter="review">Por revisar</button>
          </div>
        </div>
        <div class="results-preview-body">
          <table class="results-preview-table">
            <thead><tr><th>Origen</th><th>Estudiante</th><th>Carrera</th><th>Resultado</th><th>Conciliación</th></tr></thead>
            <tbody id="results-preview-rows"></tbody>
          </table>
        </div>
      </div>
      <div class="results-import-actions">
        <div id="results-import-progress-wrap" hidden>
          <div class="results-import-progress"><span id="results-import-progress"></span></div>
          <div class="results-note" id="results-import-progress-text"></div>
        </div>
        <button type="button" class="button primary" id="results-import-save" ${matched ? '' : 'disabled'}>Guardar ${matched} conciliados</button>
      </div>`;

    renderRows('all');
    $$('[data-import-filter]', root).forEach(button => {
      button.addEventListener('click', () => {
        $$('[data-import-filter]', root).forEach(node => node.classList.remove('active'));
        button.classList.add('active');
        renderRows(button.dataset.importFilter);
      });
    });
    $('#results-import-save')?.addEventListener('click', saveImport);
  }

  function resultLabel(item) {
    if (item.kind === 'complexivo') {
      const ordinary = `Ord. ${formatGrade(item.notaOrdinaria)}`;
      const supplementary = item.notaSupletorio !== null ? ` · Sup. ${formatGrade(item.notaSupletorio)}` : '';
      return `${ordinary}${supplementary} · Final ${formatGrade(item.notaFinal)}`;
    }
    return `Escrito ${formatGrade(item.promedioEscrito)} · Defensa ${formatGrade(item.promedioDefensa)} · Final ${formatGrade(item.notaFinal)}`;
  }

  function renderRows(filter = 'all') {
    const tbody = $('#results-preview-rows');
    if (!tbody) return;
    const all = allItems();
    const items = all.filter(item => filter !== 'review' || !item._matched);
    if (!items.length) {
      tbody.innerHTML = '<tr><td colspan="5" class="results-empty">No hay registros en este filtro.</td></tr>';
      return;
    }
    tbody.innerHTML = items.map(item => {
      const index = all.indexOf(item);
      const matched = item._matched;
      const options = item._suggestions.map(candidate => `<option value="${esc(candidate.cedula)}">${esc(candidate.nombre)} · ${esc(candidate.carrera)}</option>`).join('');
      const matchHtml = matched
        ? `<span class="match-ok">✓ ${esc(matched.cedula)}</span><div class="results-note">${esc(matched.nombre)}</div>`
        : `<span class="match-warn">Revisar</span><select data-manual-match="${index}"><option value="">Seleccionar estudiante…</option>${options}</select>`;
      return `<tr data-import-row="${index}">
        <td>${item.kind === 'complexivo' ? 'Complexivo' : 'Trabajo'}</td>
        <td><strong>${esc(item.nombre)}</strong></td>
        <td>${esc(item.carrera)}<div class="results-note">${item.modalidad === 'en_linea' ? 'En línea' : 'Presencial'}</div></td>
        <td>${esc(resultLabel(item))}<div class="results-note">${esc(item.estado)}</div></td>
        <td>${matchHtml}</td>
      </tr>`;
    }).join('');

    $$('[data-manual-match]', tbody).forEach(select => {
      select.addEventListener('change', () => {
        const item = allItems()[Number(select.dataset.manualMatch)];
        const candidate = state.candidates.find(candidate => candidate.cedula === select.value) || null;
        item._matched = candidate;
        renderPreview();
      });
    });
  }

  function complexivoPayload(item, periodId) {
    const match = item._matched;
    return {
      periodoId,
      cedula: match.cedula,
      nombre: match.nombre || item.nombre,
      carrera: match.carrera || item.carrera,
      modalidad: match.modalidad || item.modalidad,
      notaPractico: item.notaPractico,
      notaTeorico: item.notaTeorico,
      notaSupletorio: item.notaSupletorio,
      notaPromedioAcumulado: item.notaPromedioAcumulado,
      notaOrdinaria: item.notaOrdinaria,
      notaFinal: item.notaFinal,
      estado: item.estado,
      fuente: 'IMPORTACION_RESULTADOS_XLSX',
    };
  }

  function trabajoPayload(item, periodId) {
    const match = item._matched;
    const tribunal = index => item.tribunales[index] || {};
    return {
      periodoId,
      cedula: match.cedula,
      nombre: match.nombre || item.nombre,
      carrera: match.carrera || item.carrera,
      modalidad: match.modalidad || item.modalidad,
      tutor: item.tutor,
      lector: item.lector,
      notaTutor: item.notaTutor,
      notaLector: item.notaLector,
      promedioEscrito: item.promedioEscrito,
      promedioDefensa: item.promedioDefensa,
      notaFinal: item.notaFinal,
      estado: item.estado,
      tribunal1: tribunal(0).docente || '',
      tribunal2: tribunal(1).docente || '',
      tribunal3: tribunal(2).docente || '',
      tribunal1Practico: tribunal(0).practica ?? null,
      tribunal2Practico: tribunal(1).practica ?? null,
      tribunal3Practico: tribunal(2).practica ?? null,
      tribunal1Defensa: tribunal(0).defensa ?? null,
      tribunal2Defensa: tribunal(1).defensa ?? null,
      tribunal3Defensa: tribunal(2).defensa ?? null,
      detalleTribunalJson: JSON.stringify(item.tribunales),
      fuente: 'IMPORTACION_RESULTADOS_XLSX',
    };
  }

  async function saveImport() {
    if (state.saving) return;
    clearMessage();
    const periodId = selectedPeriodId();
    if (!periodId) return showError(new Error('Seleccione el período.'));
    const matchedItems = allItems().filter(item => item._matched);
    if (!matchedItems.length) return showError(new Error('No hay registros conciliados para guardar.'));

    const jobs = matchedItems.map(item => item.kind === 'complexivo'
      ? { action: 'guardar_complexivo', data: complexivoPayload(item, periodId) }
      : { action: 'guardar_trabajo_titulacion', data: trabajoPayload(item, periodId) });

    state.saving = true;
    const button = $('#results-import-save');
    if (button) button.disabled = true;
    const wrap = $('#results-import-progress-wrap');
    if (wrap) wrap.hidden = false;
    try {
      const results = await window.InformtitSheets.postMany(jobs, {
        concurrency: 4,
        onProgress(done, total) {
          const percentage = total ? Math.round((done / total) * 100) : 0;
          const bar = $('#results-import-progress');
          const text = $('#results-import-progress-text');
          if (bar) bar.style.width = `${percentage}%`;
          if (text) text.textContent = `${done} de ${total} guardados · ${percentage}%`;
        },
      });
      const failures = results.filter(result => !result.ok);
      const success = results.length - failures.length;
      if (failures.length) {
        showMessage(`${success} registros guardados. ${failures.length} no pudieron guardarse; puede volver a intentar la importación.`, true);
      } else {
        showMessage(`${success} registros guardados correctamente en Google Sheets. La importación puede repetirse: los estudiantes existentes se actualizan y no se duplican.`, false);
      }
    } catch (error) {
      showError(error);
    } finally {
      state.saving = false;
      if (button) button.disabled = false;
    }
  }

  function showMessage(message, error = false) {
    const node = $('#results-import-message');
    if (!node) return;
    node.className = error ? 'results-error-box' : 'results-success-box';
    node.textContent = message;
  }

  function clearMessage() {
    const node = $('#results-import-message');
    if (!node) return;
    node.className = '';
    node.textContent = '';
  }

  function showError(error) {
    showMessage(error?.message || String(error), true);
  }

  const observer = new MutationObserver(ensureTab);
  observer.observe(document.documentElement, { childList: true, subtree: true });
  document.addEventListener('DOMContentLoaded', ensureTab, { once: true });
  setTimeout(ensureTab, 0);
})();
