(() => {
  'use strict';

  if (!/(^|\.)github\.io$/i.test(window.location.hostname)) return;
  if (typeof window.renderReport !== 'function' || !window.InformtitNeon || !window.InformtitSheets) return;

  const previousRenderReport = window.renderReport;
  const thesisImport = { html: '', parsed: null, match: null, saving: false };

  const $ = (selector, root = document) => root.querySelector(selector);
  const clean = value => String(value ?? '').replace(/\u00a0/g, ' ').trim().replace(/\s+/g, ' ');
  const digits = value => clean(value).replace(/\D/g, '');
  const fold = value => clean(value).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toUpperCase();
  const esc = value => typeof window.escapeHtml === 'function'
    ? window.escapeHtml(String(value ?? ''))
    : String(value ?? '').replace(/[&<>"']/g, char => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;' }[char]));
  const num = value => {
    const text = clean(value);
    if (!text || text === '—' || text === '-') return null;
    const parsed = Number(text.replace(',', '.').replace(/[^0-9.-]/g, ''));
    return Number.isFinite(parsed) ? parsed : null;
  };
  const fmt = value => Number.isFinite(Number(value)) ? Number(value).toFixed(2).replace('.', ',') : '—';
  const isPvc = () => clean(window.state?.activeReport?.report_type).toLowerCase() === 'pvc';
  const activeReportId = () => Number(window.state?.activeReport?.id || 0);

  async function activePeriodId() {
    const report = window.state?.activeReport;
    if (!report) return '';
    return clean(await window.InformtitPagesData?.resolvePeriodId?.(report) || report.periodoId || report.firebase_period_id || report.period_id);
  }

  function toastMessage(message, error = false) {
    if (typeof window.toast === 'function') window.toast(message, error);
  }

  function resultRows(result) {
    if (result?.error) throw result.error;
    return Array.isArray(result?.data) ? result.data : [];
  }

  function scheduleRow(item = {}, thesis = false) {
    return `<tr>
      ${thesis ? `<td><input class="table-input" name="phase" value="${esc(item.phase || item.notes || '')}" placeholder="Fase"></td>` : ''}
      <td><input class="table-input" name="activity" value="${esc(item.activity || '')}" placeholder="Actividad"></td>
      <td><input class="table-input date-input" name="start_date" value="${esc(item.start_date || '')}" placeholder="dd/mm/aaaa"></td>
      <td><input class="table-input date-input" name="end_date" value="${esc(item.end_date || '')}" placeholder="dd/mm/aaaa"></td>
      <td><button class="button danger small" type="button" data-remove-schedule>Eliminar</button></td>
    </tr>`;
  }

  function scheduleCard(type, title, rows) {
    const thesis = type === 'thesis';
    return `<section class="panel pages-schedule-card" data-pages-schedule="${type}">
      <div class="panel-head">
        <div><h2>${esc(title)}</h2><p>Se guarda en Neon para el período activo.</p></div>
        <div class="process-actions">
          <button class="button secondary small" type="button" data-add-schedule>Agregar actividad</button>
          <button class="button primary small" type="button" data-save-schedule>Guardar cronograma</button>
        </div>
      </div>
      <div class="student-table-wrap"><table class="student-table schedule-table">
        <thead><tr>${thesis ? '<th>Fase</th>' : ''}<th>Actividad</th><th>Fecha inicio</th><th>Fecha fin</th><th></th></tr></thead>
        <tbody>${(rows || []).map(row => scheduleRow(row, thesis)).join('')}</tbody>
      </table></div>
      <p class="field-help">Fuente: Neon PostgreSQL · cronograma compartido por período.</p>
    </section>`;
  }

  function collectSchedule(card, type) {
    return [...card.querySelectorAll('tbody tr')].map(row => ({
      phase: type === 'thesis' ? clean(row.querySelector('[name="phase"]')?.value) : '',
      activity: clean(row.querySelector('[name="activity"]')?.value),
      start_date: clean(row.querySelector('[name="start_date"]')?.value),
      end_date: clean(row.querySelector('[name="end_date"]')?.value),
      notes: type === 'thesis' ? clean(row.querySelector('[name="phase"]')?.value) : '',
    })).filter(row => row.activity);
  }

  function bindScheduleCard(card, type, periodId, onSaved = null) {
    const thesis = type === 'thesis';
    card.querySelector('[data-add-schedule]')?.addEventListener('click', () => {
      card.querySelector('tbody')?.insertAdjacentHTML('beforeend', scheduleRow({}, thesis));
      bindRemoveButtons(card);
    });
    bindRemoveButtons(card);
    card.querySelector('[data-save-schedule]')?.addEventListener('click', async event => {
      const button = event.currentTarget;
      button.disabled = true;
      button.textContent = 'Guardando…';
      try {
        const entries = collectSchedule(card, type);
        const result = await window.InformtitNeon.saveSchedule(periodId, type, entries);
        toastMessage(`${Number(result.count || entries.length)} actividades guardadas en Neon.`);
        if (typeof onSaved === 'function') await onSaved();
      } catch (error) {
        toastMessage(error?.message || 'No se pudo guardar el cronograma.', true);
      } finally {
        if (button.isConnected) { button.disabled = false; button.textContent = 'Guardar cronograma'; }
      }
    });
  }

  function bindRemoveButtons(card) {
    card.querySelectorAll('[data-remove-schedule]').forEach(button => {
      if (button.dataset.bound) return;
      button.dataset.bound = '1';
      button.addEventListener('click', () => button.closest('tr')?.remove());
    });
  }

  async function renderSchedules() {
    if (isPvc()) return;
    const reportId = activeReportId();
    const tab = $('#tab-schedules');
    if (!reportId || !tab) return;
    tab.innerHTML = '<div class="panel"><div class="empty-mini">Cargando cronogramas desde Neon…</div></div>';
    try {
      const periodId = await activePeriodId();
      if (!periodId) throw new Error('No se pudo identificar el período académico.');
      const data = await window.InformtitNeon.schedules(periodId);
      if (activeReportId() !== reportId) return;
      const schedules = data.schedules || {};
      tab.innerHTML = `<div class="process-stack pages-process-stack">
        ${scheduleCard('complexive', 'Cronograma de Núcleos y Examen Complexivo', schedules.complexive || [])}
        ${scheduleCard('thesis', 'Cronograma de Trabajo de Titulación', schedules.thesis || [])}
      </div>`;
      tab.querySelectorAll('[data-pages-schedule]').forEach(card => bindScheduleCard(card, card.dataset.pagesSchedule, periodId, renderSchedules));
    } catch (error) {
      tab.innerHTML = `<div class="panel"><div class="empty-mini">${esc(error?.message || 'No se pudieron cargar los cronogramas.')}</div></div>`;
    }
  }

  function markdownClean(value) {
    return clean(String(value ?? '').replace(/<br\s*\/?>/gi, ' ').replace(/\*\*/g, '').replace(/^[:|\s]+|[:|\s]+$/g, ''));
  }

  function splitCells(line) {
    if (line.includes('|')) return line.split('|').map(markdownClean).filter(Boolean);
    if (line.includes('\t')) return line.split('\t').map(markdownClean).filter(Boolean);
    return [markdownClean(line)].filter(Boolean);
  }

  function fieldFromLines(lines, labels) {
    const wanted = labels.map(fold);
    for (let i = 0; i < lines.length; i += 1) {
      const cells = splitCells(lines[i]);
      for (let c = 0; c < cells.length; c += 1) {
        const key = fold(cells[c]);
        if (!wanted.some(label => key.includes(label))) continue;
        if (cells[c + 1]) return markdownClean(cells[c + 1]);
        const colon = cells[c].split(/:\s*/).slice(1).join(':').trim();
        if (colon) return markdownClean(colon);
        if (lines[i + 1]) {
          const next = splitCells(lines[i + 1])[0];
          if (next && !wanted.some(label => fold(next).includes(label))) return markdownClean(next);
        }
      }
    }
    return '';
  }

  function fieldFromHtml(doc, labels) {
    const wanted = labels.map(fold);
    for (const row of doc.querySelectorAll('tr')) {
      const cells = [...row.querySelectorAll('th,td')].map(cell => clean(cell.textContent));
      for (let i = 0; i < cells.length; i += 1) {
        const key = fold(cells[i]);
        if (!wanted.some(label => key.includes(label))) continue;
        for (let j = i + 1; j < cells.length; j += 1) if (clean(cells[j])) return clean(cells[j]);
      }
    }
    return '';
  }

  function vocalFromText(text, label) {
    const lines = String(text || '').split(/\r?\n/).map(markdownClean).filter(Boolean);
    const wanted = fold(label);
    for (let i = 0; i < lines.length; i += 1) {
      const current = lines[i];
      if (!fold(current).includes(wanted)) continue;
      const stripped = clean(current.replace(new RegExp(label, 'i'), ''));
      if (stripped && fold(stripped) !== wanted) return stripped;
      if (lines[i + 1] && !/PUNTAJE|VOCAL|EVALUACION/i.test(fold(lines[i + 1]))) return lines[i + 1];
    }
    return '';
  }

  function identityFromHtml(doc) {
    for (const row of doc.querySelectorAll('tr')) {
      const cells = [...row.querySelectorAll('th,td')].map(cell => clean(cell.textContent));
      const index = cells.findIndex(cell => /^\d{10}$/.test(digits(cell)) && digits(cell).length === 10);
      if (index < 0) continue;
      return {
        nombre: clean(cells[index - 1] || ''),
        cedula: digits(cells[index]),
        codigoCarrera: clean(cells[index + 1] || ''),
        carrera: clean(cells[index + 2] || ''),
      };
    }
    return {};
  }

  function identityFromText(text) {
    const lines = String(text || '').split(/\r?\n/).map(line => line.trim()).filter(Boolean);
    for (let i = 0; i < lines.length; i += 1) {
      const line = markdownClean(lines[i]);
      const match = line.match(/^(.*?)\b(\d{10})\b(.*)$/);
      if (!match) continue;
      const before = markdownClean(match[1]);
      const after = markdownClean(match[3]);
      const codeMatch = after.match(/\b([A-Z0-9]+-[PL]-\d+)\b/i);
      const code = codeMatch?.[1] || '';
      const career = code ? markdownClean(after.slice(after.indexOf(code) + code.length)) : '';
      return {
        nombre: before || markdownClean(lines[i - 1] || ''),
        cedula: match[2],
        codigoCarrera: code,
        carrera: career || markdownClean(lines[i + 1] || ''),
      };
    }
    const cedulaMatch = String(text || '').match(/\b\d{10}\b/);
    return cedulaMatch ? { cedula: cedulaMatch[0] } : {};
  }

  function parseThesisSource(text, html = '') {
    const sourceText = String(text || '');
    const lines = sourceText.split(/\r?\n/).filter(Boolean);
    let doc = null;
    if (html && /<table[\s>]/i.test(html)) doc = new DOMParser().parseFromString(html, 'text/html');
    const identity = doc ? identityFromHtml(doc) : identityFromText(sourceText);
    const get = labels => clean((doc && fieldFromHtml(doc, labels)) || fieldFromLines(lines, labels));
    const getNum = labels => num(get(labels));
    const codigoCarrera = clean(identity.codigoCarrera || get(['CODIGO DE CARRERA','CÓDIGO DE CARRERA']));
    const carrera = clean(identity.carrera || get(['CARRERA']));
    const modality = /-L-/i.test(codigoCarrera) || /ONLINE|EN LINEA|VIRTUAL/i.test(fold(carrera)) ? 'en_linea' : 'presencial';
    const promedioEscrito = getNum(['PROMEDIO TRABAJO ESCRITO']);
    const promedioDefensa = getNum(['PROMEDIO EVALUACION DEFENSA','PROMEDIO EVALUACIÓN DEFENSA']);
    const promedioPractica = getNum(['PROMEDIO EVALUACION PRACTICA','PROMEDIO EVALUACIÓN PRACTICA']);
    const defensaOral = getNum(['PROMEDIO DEFENSA ORAL DEL PROYECTO DE TITULACION','PROMEDIO DEFENSA ORAL']);
    const notaFinal = getNum(['CALIFICACION FINAL DEL PROYECTO DE TITULACION','CALIFICACIÓN FINAL DEL PROYECTO DE TITULACIÓN']);
    const parsed = {
      cedula: digits(identity.cedula),
      nombre: clean(identity.nombre),
      codigoCarrera,
      carrera,
      modalidad,
      titulo: get(['TITULO DEL PROYECTO','TÍTULO DEL PROYECTO','TITULO','TÍTULO']),
      numeroActa: get(['NUMERO DE ACTA DE GRADO','NÚMERO DE ACTA DE GRADO']),
      fechaActa: get(['FECHA ACTA DE GRADO']),
      tutor: get(['TUTOR']),
      lector: get(['LECTOR']),
      notaTutor: getNum(['CALIFICACION TUTOR','CALIFICACIÓN TUTOR']),
      notaLector: getNum(['CALIFICACION LECTOR','CALIFICACIÓN LECTOR']),
      promedioEscrito,
      promedioPractica,
      promedioDefensa,
      defensaOral,
      notaFinal,
      tribunal1: doc ? vocalFromText(doc.body.innerText, 'PRIMER VOCAL') : vocalFromText(sourceText, 'PRIMER VOCAL'),
      tribunal2: doc ? vocalFromText(doc.body.innerText, 'SEGUNDO VOCAL') : vocalFromText(sourceText, 'SEGUNDO VOCAL'),
      tribunal3: doc ? vocalFromText(doc.body.innerText, 'TERCER VOCAL') : vocalFromText(sourceText, 'TERCER VOCAL'),
      fuenteTexto: clean(sourceText).slice(0, 30000),
    };
    parsed.estado = parsed.notaFinal === null ? 'INCOMPLETO' : parsed.notaFinal >= 7 ? 'APROBADO' : 'REPROBADO';
    if (!parsed.cedula || parsed.cedula.length !== 10) throw new Error('No se pudo identificar una cédula de 10 dígitos en el bloque de Trabajo de Titulación.');
    return parsed;
  }

  async function decodeLegacyFile(file) {
    const bytes = new Uint8Array(await file.arrayBuffer());
    let text = '';
    try { text = new TextDecoder('utf-8', { fatal: true }).decode(bytes); } catch (_) {}
    if (!text || text.includes('\uFFFD')) text = new TextDecoder('windows-1252').decode(bytes);
    return text;
  }

  async function analyzeThesisImport() {
    const textarea = $('#thesis-sisacad-text');
    const preview = $('#thesis-import-preview');
    if (!textarea || !preview) return;
    try {
      const parsed = parseThesisSource(textarea.value, thesisImport.html);
      const data = await window.InformtitSheets.estudiantes();
      const match = (data.estudiantes || []).find(student => digits(student.cedula || student.identificacion) === parsed.cedula) || null;
      thesisImport.parsed = parsed;
      thesisImport.match = match;
      preview.innerHTML = `<div class="summary-grid">
        <div class="summary-item"><span>Cédula</span><strong>${esc(parsed.cedula)}</strong></div>
        <div class="summary-item"><span>Estudiante</span><strong>${esc(match?.nombre || parsed.nombre || 'Sin nombre')}</strong></div>
        <div class="summary-item"><span>Trabajo escrito</span><strong>${fmt(parsed.promedioEscrito)}</strong></div>
        <div class="summary-item"><span>Defensa</span><strong>${fmt(parsed.promedioDefensa)}</strong></div>
      </div>
      <div class="empty-mini">${match ? 'Coincidencia exacta por cédula en Neon.' : 'La cédula aún no existe en Neon; se creará con esta importación.'}</div>
      <div class="project-meta"><strong>Carrera:</strong> ${esc(parsed.carrera || '—')} · <strong>Acta:</strong> ${esc(parsed.numeroActa || '—')}</div>
      <div class="project-meta"><strong>Tribunal:</strong> ${esc(parsed.tribunal1 || '—')} · ${esc(parsed.tribunal2 || '—')} · ${esc(parsed.tribunal3 || '—')}</div>`;
      const save = $('#thesis-import-save');
      if (save) save.disabled = false;
    } catch (error) {
      thesisImport.parsed = null;
      thesisImport.match = null;
      preview.innerHTML = `<div class="empty-mini">${esc(error?.message || error)}</div>`;
      const save = $('#thesis-import-save');
      if (save) save.disabled = true;
    }
  }

  async function saveThesisImport() {
    if (thesisImport.saving || !thesisImport.parsed) return;
    const button = $('#thesis-import-save');
    thesisImport.saving = true;
    if (button) { button.disabled = true; button.textContent = 'Guardando…'; }
    try {
      const periodId = await activePeriodId();
      if (!periodId) throw new Error('No se pudo identificar el período académico.');
      const p = thesisImport.parsed;
      const payload = {
        periodoId: periodId,
        cedula: p.cedula,
        nombre: thesisImport.match?.nombre || p.nombre || p.cedula,
        codigoCarrera: p.codigoCarrera,
        carrera: p.carrera,
        modalidad: p.modalidad,
        titulo: p.titulo,
        tutor: p.tutor,
        lector: p.lector,
        notaTutor: p.notaTutor,
        notaLector: p.notaLector,
        promedioEscrito: p.promedioEscrito,
        promedioPractica: p.promedioPractica,
        promedioDefensa: p.promedioDefensa,
        defensaOral: p.defensaOral,
        notaFinal: p.notaFinal,
        estado: p.estado,
        numeroActa: p.numeroActa,
        fechaActa: p.fechaActa,
        tribunal1: p.tribunal1,
        tribunal2: p.tribunal2,
        tribunal3: p.tribunal3,
        detalleTribunalJson: JSON.stringify({ vocal1:p.tribunal1, vocal2:p.tribunal2, vocal3:p.tribunal3 }),
        fuente: 'SISACAD_TRABAJO_TITULACION',
        fuenteTexto: p.fuenteTexto,
      };
      await window.InformtitSheets.guardarTrabajoTitulacion(payload);
      window.InformtitPagesData?.invalidate?.(periodId);
      toastMessage(`Trabajo de Titulación guardado por cédula ${p.cedula}.`);
      thesisImport.parsed = null;
      thesisImport.match = null;
      thesisImport.html = '';
      await renderThesis();
    } catch (error) {
      toastMessage(error?.message || 'No se pudo guardar Trabajo de Titulación.', true);
    } finally {
      thesisImport.saving = false;
      if (button?.isConnected) { button.disabled = !thesisImport.parsed; button.textContent = 'Guardar en Neon'; }
    }
  }

  async function loadThesisRows(periodId) {
    const client = await window.InformtitNeon.requireAccess();
    const result = await client.from('thesis_results').select('*').eq('period_id', periodId).order('updated_at', { ascending:false });
    const rows = resultRows(result);
    const ids = [...new Set(rows.map(row => Number(row.student_id)).filter(Number.isFinite))];
    if (!ids.length) return [];
    const [studentsResult, enrollmentsResult] = await Promise.all([
      client.from('students').select('id,identification,full_name').in('id', ids),
      client.from('enrollments').select('student_id,career_code,career_name,modality,titulation_route').eq('period_id', periodId).in('student_id', ids),
    ]);
    const students = new Map(resultRows(studentsResult).map(row => [Number(row.id), row]));
    const enrollments = new Map(resultRows(enrollmentsResult).map(row => [Number(row.student_id), row]));
    return rows.map(row => {
      const raw = row.raw_data || {};
      const student = students.get(Number(row.student_id)) || {};
      const enrollment = enrollments.get(Number(row.student_id)) || {};
      return {
        identification: student.identification || raw.cedula || '',
        full_name: student.full_name || raw.nombre || '',
        career_name: enrollment.career_name || raw.carrera || '',
        career_code: enrollment.career_code || raw.codigoCarrera || '',
        modality: enrollment.modality || raw.modalidad || '',
        title: row.title || raw.titulo || '',
        tutor: row.tutor || raw.tutor || '',
        lector: raw.lector || '',
        tutor_grade: num(raw.notaTutor),
        reader_grade: num(raw.notaLector),
        written_average: num(raw.promedioEscrito),
        practical_average: num(raw.promedioPractica),
        defense_average: num(raw.promedioDefensa),
        oral_average: num(raw.defensaOral),
        final_grade: row.final_grade === null ? num(raw.notaFinal) : num(row.final_grade),
        final_status: row.final_status || raw.estado || 'INCOMPLETO',
        act_number: raw.numeroActa || raw.acta || '',
        act_date: raw.fechaActa || '',
        vocal_1: raw.tribunal1 || '', vocal_2: raw.tribunal2 || '', vocal_3: raw.tribunal3 || '',
      };
    });
  }

  function thesisCard(project) {
    const status = project.final_grade === null ? (project.written_average !== null ? 'Defensa pendiente' : 'Pendiente') : project.final_grade >= 7 ? 'Aprobado' : 'Reprobado';
    return `<article class="career-card project-card pages-thesis-card">
      <div class="career-head"><div><span class="badge">${esc(status)}</span><h3>${esc(project.full_name || 'Sin nombre')}</h3><p>${esc(project.identification || 'Sin cédula')} · ${esc(project.career_name || 'Sin carrera')}</p></div></div>
      <div class="summary-grid">
        <div class="summary-item"><span>Tutor</span><strong>${fmt(project.tutor_grade)}</strong></div>
        <div class="summary-item"><span>Lector</span><strong>${fmt(project.reader_grade)}</strong></div>
        <div class="summary-item"><span>Trabajo escrito</span><strong>${fmt(project.written_average)}</strong></div>
        <div class="summary-item"><span>Defensa</span><strong>${fmt(project.defense_average)}</strong></div>
        <div class="summary-item"><span>Nota final</span><strong>${fmt(project.final_grade)}</strong></div>
      </div>
      <div class="project-meta"><strong>Código carrera:</strong> ${esc(project.career_code || '—')} · <strong>Acta:</strong> ${esc(project.act_number || '—')} · ${esc(project.act_date || '—')}</div>
      <div class="project-meta"><strong>Tutor:</strong> ${esc(project.tutor || '—')} · <strong>Lector:</strong> ${esc(project.lector || '—')}</div>
      <div class="project-meta"><strong>Tribunal:</strong> ${esc(project.vocal_1 || '—')} · ${esc(project.vocal_2 || '—')} · ${esc(project.vocal_3 || '—')}</div>
    </article>`;
  }

  function thesisImportPanel() {
    return `<section class="panel">
      <div class="panel-head"><div><h2>Cargar Trabajo de Titulación</h2><p>Pegue el bloque de SISACAD o cargue un .xls/.html antiguo. Informtit hace la conciliación exclusivamente por cédula.</p></div></div>
      <div class="form-grid">
        <label>Bloque SISACAD<textarea id="thesis-sisacad-text" rows="8" placeholder="Pegue aquí la información del estudiante y su proyecto…"></textarea></label>
        <label>Archivo opcional<input id="thesis-sisacad-file" type="file" accept=".xls,.html,.htm,.txt"></label>
      </div>
      <div class="process-actions"><button type="button" class="button secondary" id="thesis-import-analyze">Analizar por cédula</button><button type="button" class="button primary" id="thesis-import-save" disabled>Guardar en Neon</button></div>
      <div id="thesis-import-preview" class="empty-mini">Todavía no se ha analizado ningún registro.</div>
    </section>`;
  }

  function bindThesisImport() {
    const textarea = $('#thesis-sisacad-text');
    const file = $('#thesis-sisacad-file');
    textarea?.addEventListener('paste', event => { thesisImport.html = event.clipboardData?.getData('text/html') || ''; });
    textarea?.addEventListener('input', () => { if (!textarea.value) thesisImport.html = ''; thesisImport.parsed = null; thesisImport.match = null; $('#thesis-import-save')?.setAttribute('disabled',''); });
    file?.addEventListener('change', async event => {
      const selected = event.currentTarget.files?.[0];
      if (!selected || !textarea) return;
      try {
        const text = await decodeLegacyFile(selected);
        thesisImport.html = /<table[\s>]/i.test(text) ? text : '';
        textarea.value = thesisImport.html ? clean(new DOMParser().parseFromString(text, 'text/html').body.innerText) : text;
        await analyzeThesisImport();
      } catch (error) { toastMessage(error?.message || error, true); }
    });
    $('#thesis-import-analyze')?.addEventListener('click', analyzeThesisImport);
    $('#thesis-import-save')?.addEventListener('click', saveThesisImport);
  }

  async function renderThesis() {
    if (isPvc()) return;
    const reportId = activeReportId();
    const tab = $('#tab-projects');
    if (!reportId || !tab) return;
    tab.innerHTML = '<div class="panel"><div class="empty-mini">Cargando Trabajo de Titulación desde Neon…</div></div>';
    try {
      const periodId = await activePeriodId();
      if (!periodId) throw new Error('No se pudo identificar el período académico.');
      const [projects, schedulesData] = await Promise.all([loadThesisRows(periodId), window.InformtitNeon.schedules(periodId)]);
      if (activeReportId() !== reportId) return;
      const grades = projects.map(row => row.final_grade).filter(Number.isFinite);
      tab.innerHTML = `<div class="process-stack pages-process-stack">
        <section class="panel"><div class="panel-head"><div><h2>Trabajo de Titulación</h2><p>Fuente principal: Neon PostgreSQL · identificación por cédula.</p></div></div>
          <div class="summary-grid project-summary">
            <div class="summary-item"><span>Registrados</span><strong>${projects.length}</strong></div>
            <div class="summary-item"><span>Con nota final</span><strong>${grades.length}</strong></div>
            <div class="summary-item"><span>Defensa pendiente</span><strong>${projects.filter(row => row.final_grade === null).length}</strong></div>
            <div class="summary-item"><span>Promedio final</span><strong>${fmt(grades.length ? grades.reduce((a,b)=>a+b,0)/grades.length : null)}</strong></div>
          </div>
        </section>
        ${thesisImportPanel()}
        ${scheduleCard('thesis', 'Cronograma de Trabajo de Titulación', schedulesData.schedules?.thesis || [])}
        <section class="panel"><div class="panel-head"><div><h2>Registros</h2><p>Los campos vacíos permanecen pendientes; no se convierten en cero.</p></div></div>
          <div class="project-list">${projects.length ? projects.map(thesisCard).join('') : '<div class="empty-mini">No existen registros de Trabajo de Titulación para este período.</div>'}</div>
        </section>
      </div>`;
      bindThesisImport();
      const card = tab.querySelector('[data-pages-schedule="thesis"]');
      if (card) bindScheduleCard(card, 'thesis', periodId, renderThesis);
    } catch (error) {
      tab.innerHTML = `<div class="panel"><div class="empty-mini">${esc(error?.message || 'No se pudo cargar Trabajo de Titulación.')}</div></div>`;
    }
  }

  function refreshProcesses() {
    if (isPvc()) return;
    void renderSchedules();
    void renderThesis();
  }

  window.renderReport = function renderReportWithPagesProcesses(...args) {
    const result = previousRenderReport.apply(this, args);
    refreshProcesses();
    return result;
  };

  document.addEventListener('click', event => {
    const tab = event.target.closest?.('[data-tab]');
    if (!tab || isPvc()) return;
    if (tab.dataset.tab === 'schedules') void renderSchedules();
    if (tab.dataset.tab === 'projects') void renderThesis();
  });
})();