(() => {
  'use strict';

  window.INFORMTIT_MINIMAL_NUCLEI = true;

  const previousRenderReport = renderReport;
  let activeNucleiReportId = 0;
  let searchText = '';
  let filterMode = 'all';
  let lastGroups = [];
  let loadTarget = null;

  function esc(value = '') {
    return typeof escapeHtml === 'function'
      ? escapeHtml(String(value))
      : String(value).replace(/[&<>"']/g, character => ({
          '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;',
        })[character]);
  }

  function normalize(value = '') {
    return String(value)
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, ' ')
      .trim();
  }

  function compareText(left, right) {
    return String(left || '').localeCompare(String(right || ''), 'es', { sensitivity: 'base' });
  }

  function fmt(value) {
    if (value === null || value === undefined || value === '') return '—';
    const number = Number(value);
    return Number.isFinite(number) ? number.toFixed(2).replace('.', ',') : '—';
  }

  const CANONICAL_LABELS = new Map([
    ['administracion', 'ADMINISTRACIÓN'],
    ['educacion basica', 'EDUCACIÓN BÁSICA'],
    ['educacion inicial', 'EDUCACIÓN INICIAL'],
    ['gestion del talento humano', 'GESTIÓN DEL TALENTO HUMANO'],
    ['marketing digital y comercio electronico', 'MARKETING DIGITAL Y COMERCIO ELECTRÓNICO'],
    ['redes y telecomunicaciones', 'REDES Y TELECOMUNICACIONES'],
  ]);

  function canonicalCareer(value = '') {
    const external = window.informtitNucleiCareer?.canonicalCareer;
    let text = typeof external === 'function' ? external(value) : String(value || '');
    text = String(text || '').replace(/\u00a0/g, ' ').trim().replace(/\s+/g, ' ')
      .replace(/^(?:TECNOLOG[IÍ]A|T[EÉ]CNICO)\s+SUPERIOR(?:\s+UNIVERSITARIA)?\s+EN\s+/i, '')
      .replace(/\s+(?:ONLINE|EN\s+L[IÍ]NEA|VIRTUAL|PRESENCIAL)\s*$/i, '')
      .trim();
    const key = normalize(text);
    if (key.includes('redes') && key.includes('telecomunicaciones')) return 'REDES Y TELECOMUNICACIONES';
    return CANONICAL_LABELS.get(key) || (text ? text.toLocaleUpperCase('es') : 'SIN CARRERA');
  }

  function studentIdentity(student = {}) {
    const identification = String(student.identification || student.cedula || '').trim();
    if (identification) return `id:${identification}`;
    const email = String(student.email || student.correo || '').trim().toLowerCase();
    if (email) return `email:${email}`;
    const name = normalize(student.full_name || student.nombre || student.nombres || '');
    return name ? `name:${name}` : '';
  }

  function numericGrade(student = {}) {
    const value = Number(student.final_grade ?? student.notaFinal ?? student.nota_final);
    return Number.isFinite(value) ? value : null;
  }

  function isReviewStudent(student = {}) {
    const matchStatus = normalize(student.matchStatus || student.match_status || '');
    return matchStatus === 'review' || matchStatus === 'sin coincidencia' || !studentIdentity(student);
  }

  function statusCounts(students) {
    const approved = students.filter(student => normalize(student.final_status || student.estado) === 'aprobado').length;
    const failed = students.filter(student => normalize(student.final_status || student.estado) === 'reprobado').length;
    const pending = students.length - approved - failed;
    return { approved, failed, pending };
  }

  function courseTimestamp(course = {}) {
    const value = Date.parse(course.updated_at || course.updatedAt || course._updateTime || '');
    return Number.isFinite(value) ? value : 0;
  }

  function blankNucleus(number) {
    return {
      number,
      studentsByIdentity: new Map(),
      students: [],
      sources: [],
      duplicateCount: 0,
      conflictCount: 0,
      reviewCount: 0,
      average: null,
      counts: { approved: 0, failed: 0, pending: 0 },
    };
  }

  function organizeCareers(courses, catalogCareers = []) {
    const groups = new Map();

    function ensure(rawCareer) {
      const career = canonicalCareer(rawCareer);
      const key = normalize(career);
      if (!groups.has(key)) {
        groups.set(key, {
          career,
          nuclei: { 1: blankNucleus(1), 2: blankNucleus(2), 3: blankNucleus(3), 4: blankNucleus(4) },
          uniqueStudents: 0,
          loadedNuclei: 0,
          reviewCount: 0,
          search: '',
        });
      }
      return groups.get(key);
    }

    (catalogCareers || []).forEach(ensure);

    (courses || []).forEach(course => {
      const group = ensure(course.career_name);
      const nucleusNumber = Number(course.nucleus_number || 0);
      if (![1, 2, 3, 4].includes(nucleusNumber)) return;
      const slot = group.nuclei[nucleusNumber];
      const sourceTimestamp = courseTimestamp(course);
      slot.sources.push(course);

      (course.students || []).forEach((student, index) => {
        const identity = studentIdentity(student) || `anonymous:${normalize(student.full_name)}:${index}`;
        const candidate = { ...student, _sourceTimestamp: sourceTimestamp };
        const existing = slot.studentsByIdentity.get(identity);
        if (!existing) {
          slot.studentsByIdentity.set(identity, candidate);
          return;
        }

        slot.duplicateCount += 1;
        const existingGrade = numericGrade(existing);
        const candidateGrade = numericGrade(candidate);
        const existingStatus = normalize(existing.final_status || existing.estado);
        const candidateStatus = normalize(candidate.final_status || candidate.estado);
        if (
          (existingGrade !== null && candidateGrade !== null && Math.abs(existingGrade - candidateGrade) > 0.001)
          || (existingStatus && candidateStatus && existingStatus !== candidateStatus)
        ) slot.conflictCount += 1;

        const candidateIsNewer = candidate._sourceTimestamp > (existing._sourceTimestamp || 0);
        const candidateHasBetterData = existingGrade === null && candidateGrade !== null;
        if (candidateIsNewer || candidateHasBetterData) slot.studentsByIdentity.set(identity, candidate);
      });
    });

    const output = [...groups.values()];
    output.forEach(group => {
      const careerStudents = new Set();
      for (let number = 1; number <= 4; number += 1) {
        const slot = group.nuclei[number];
        slot.students = [...slot.studentsByIdentity.values()].sort((a, b) => compareText(a.full_name, b.full_name));
        slot.students.forEach(student => {
          const identity = studentIdentity(student);
          if (identity) careerStudents.add(identity);
        });
        const grades = slot.students.map(numericGrade).filter(value => value !== null);
        slot.average = grades.length ? grades.reduce((sum, value) => sum + value, 0) / grades.length : null;
        slot.counts = statusCounts(slot.students);
        slot.reviewCount = slot.students.filter(isReviewStudent).length + slot.conflictCount;
        group.reviewCount += slot.reviewCount;
      }
      group.uniqueStudents = careerStudents.size;
      group.loadedNuclei = [1, 2, 3, 4].filter(number => group.nuclei[number].students.length > 0).length;
      group.search = normalize([
        group.career,
        ...[1, 2, 3, 4].flatMap(number => group.nuclei[number].students.map(student => (
          `${student.full_name || ''} ${student.identification || student.cedula || ''} ${student.email || ''}`
        ))),
      ].join(' '));
    });

    return output.sort((a, b) => compareText(a.career, b.career));
  }

  renderReport = function renderReportWithNucleiMatrix() {
    previousRenderReport();
    if (state.activeReport?.id) renderNucleiModule();
  };

  async function renderNucleiModule() {
    const tab = document.querySelector('#tab-nuclei');
    const reportId = Number(state.activeReport?.id || 0);
    if (!tab || !reportId) return;

    if (activeNucleiReportId !== reportId) {
      activeNucleiReportId = reportId;
      searchText = '';
      filterMode = 'all';
    }

    bindDelegatedEvents(tab);
    tab.innerHTML = '<div class="panel"><div class="empty-mini">Cargando Núcleos...</div></div>';

    try {
      const data = await api(`/api/reports/${reportId}/nuclei`);
      if (Number(state.activeReport?.id || 0) !== reportId) return;
      lastGroups = organizeCareers(data?.courses || [], data?.careers || []);
      tab.innerHTML = markup(lastGroups);
      applyFilters(tab);
    } catch (error) {
      tab.innerHTML = `<div class="panel"><div class="empty-mini">${esc(error.message)}</div></div>`;
    }
  }

  function summary(groups) {
    const students = new Set();
    let loaded = 0;
    let review = 0;
    groups.forEach(group => {
      review += group.reviewCount;
      [1, 2, 3, 4].forEach(number => {
        const slot = group.nuclei[number];
        if (slot.students.length) loaded += 1;
        slot.students.forEach(student => {
          const identity = studentIdentity(student);
          if (identity) students.add(`${normalize(group.career)}|${identity}`);
        });
      });
    });
    return { students: students.size, careers: groups.length, loaded, total: groups.length * 4, review };
  }

  function markup(groups) {
    const totals = summary(groups);
    return `
      <div class="nuclei-matrix-shell" data-nuclei-matrix>
        <div class="nuclei-matrix-heading">
          <div>
            <h2>Núcleos</h2>
            <p>${esc(state.activeReport?.period || '')}</p>
          </div>
          <div class="nuclei-legend"><span><i class="dot ok"></i>Cargado</span><span><i class="dot warn"></i>Revisar</span><span><i class="dot pending"></i>Pendiente</span></div>
        </div>

        <div class="nuclei-kpis">
          ${kpi(totals.students, 'Estudiantes')}
          ${kpi(totals.careers, 'Carreras')}
          ${kpi(`${totals.loaded}/${totals.total}`, 'Núcleos cargados')}
          ${kpi(totals.review, 'Por revisar', totals.review > 0 ? 'attention' : '')}
        </div>

        <div class="nuclei-toolbar">
          <label class="nuclei-search"><span>Buscar</span><input type="search" data-nuclei-search value="${esc(searchText)}" placeholder="Carrera, estudiante o cédula"></label>
          <div class="nuclei-filter-tabs" role="group" aria-label="Filtrar Núcleos">
            ${filterButton('all', 'Todos')}
            ${filterButton('pending', 'Pendientes')}
            ${filterButton('review', 'Con errores')}
          </div>
        </div>

        ${matrixMarkup(groups)}
        ${loadDialogMarkup()}
        ${detailDialogMarkup()}
      </div>`;
  }

  function kpi(value, label, className = '') {
    return `<div class="nuclei-kpi ${className}"><strong>${esc(value)}</strong><span>${esc(label)}</span></div>`;
  }

  function filterButton(mode, label) {
    return `<button type="button" class="nuclei-filter-button ${filterMode === mode ? 'active' : ''}" data-nuclei-filter="${mode}">${label}</button>`;
  }

  function matrixMarkup(groups) {
    if (!groups.length) return '<div class="empty-mini">No se encontraron carreras para este período.</div>';
    return `
      <div class="nuclei-matrix-wrap">
        <table class="nuclei-matrix-table">
          <thead><tr><th>Carrera</th><th>Núcleo 1</th><th>Núcleo 2</th><th>Núcleo 3</th><th>Núcleo 4</th></tr></thead>
          <tbody>
            ${groups.map(group => `
              <tr data-nuclei-row data-career="${esc(group.career)}" data-search="${esc(group.search)}" data-loaded="${group.loadedNuclei}" data-review="${group.reviewCount}">
                <th scope="row"><strong>${esc(group.career)}</strong><span>${group.loadedNuclei}/4 cargados${group.reviewCount ? ` · ${group.reviewCount} por revisar` : ''}</span></th>
                ${[1, 2, 3, 4].map(number => matrixCell(group, group.nuclei[number])).join('')}
              </tr>`).join('')}
          </tbody>
        </table>
      </div>`;
  }

  function matrixCell(group, slot) {
    const loaded = slot.students.length > 0;
    const hasReview = slot.reviewCount > 0;
    const statusClass = hasReview ? 'review' : loaded ? 'loaded' : 'pending';
    const icon = hasReview ? '!' : loaded ? '✓' : '+';
    const label = hasReview ? `${slot.students.length} · revisar` : loaded ? `${slot.students.length}` : 'Cargar';
    const title = loaded
      ? `${group.career} · Núcleo ${slot.number}: ${slot.students.length} estudiantes, promedio ${fmt(slot.average)}${hasReview ? `, ${slot.reviewCount} por revisar` : ''}`
      : `${group.career} · Núcleo ${slot.number}: pendiente`;
    return `<td>
      <button type="button" class="nuclei-cell ${statusClass}" data-nuclei-cell data-career="${esc(group.career)}" data-nucleus="${slot.number}" title="${esc(title)}">
        <span class="nuclei-cell-icon">${icon}</span>
        <span class="nuclei-cell-label">${esc(label)}</span>
      </button>
    </td>`;
  }

  function loadDialogMarkup() {
    return `
      <dialog class="nuclei-dialog" data-nuclei-load-dialog>
        <form method="dialog" class="nuclei-dialog-card" data-nuclei-load-form>
          <div class="nuclei-dialog-head">
            <div><span class="eyebrow">Cargar calificaciones</span><h3 data-load-title>Núcleo</h3><p data-load-subtitle></p></div>
            <button class="icon-button" value="cancel" aria-label="Cerrar">×</button>
          </div>
          <label class="nuclei-paste-field">Pega aquí la tabla copiada desde Moodle
            <textarea name="text" rows="10" required placeholder="Pega la tabla completa de calificaciones..."></textarea>
          </label>
          <p class="nuclei-dialog-help">Informtit identificará los estudiantes y verificará la carrera antes de guardar.</p>
          <div data-load-result></div>
          <div class="nuclei-dialog-actions">
            <button class="button secondary" value="cancel">Cancelar</button>
            <button class="button primary" type="submit" value="default">Procesar y guardar</button>
          </div>
        </form>
      </dialog>`;
  }

  function detailDialogMarkup() {
    return `
      <dialog class="nuclei-dialog nuclei-detail-dialog" data-nuclei-detail-dialog>
        <div class="nuclei-dialog-card">
          <div class="nuclei-dialog-head">
            <div><span class="eyebrow">Detalle</span><h3 data-detail-title>Núcleo</h3><p data-detail-subtitle></p></div>
            <button class="icon-button" type="button" data-close-detail aria-label="Cerrar">×</button>
          </div>
          <div data-detail-body></div>
          <div class="nuclei-dialog-actions">
            <button class="button secondary" type="button" data-close-detail>Cerrar</button>
            <button class="button primary" type="button" data-detail-update>Actualizar Núcleo</button>
          </div>
        </div>
      </dialog>`;
  }

  function bindDelegatedEvents(tab) {
    if (tab.dataset.nucleiMatrixBound === '1') return;
    tab.dataset.nucleiMatrixBound = '1';
    tab.addEventListener('click', handleClick);
    tab.addEventListener('input', handleInput);
    tab.addEventListener('submit', handleSubmit);
  }

  function handleClick(event) {
    const tab = event.currentTarget;
    const filter = event.target.closest('[data-nuclei-filter]');
    if (filter) {
      filterMode = filter.dataset.nucleiFilter || 'all';
      tab.querySelectorAll('[data-nuclei-filter]').forEach(button => button.classList.toggle('active', button === filter));
      applyFilters(tab);
      return;
    }

    const cell = event.target.closest('[data-nuclei-cell]');
    if (cell) {
      const career = cell.dataset.career || '';
      const nucleus = Number(cell.dataset.nucleus || 0);
      const group = lastGroups.find(item => normalize(item.career) === normalize(career));
      const slot = group?.nuclei?.[nucleus];
      if (slot?.students?.length) openDetail(tab, group, slot);
      else openLoad(tab, career, nucleus);
      return;
    }

    const close = event.target.closest('[data-close-detail]');
    if (close) {
      tab.querySelector('[data-nuclei-detail-dialog]')?.close();
      return;
    }

    const update = event.target.closest('[data-detail-update]');
    if (update) {
      const dialog = tab.querySelector('[data-nuclei-detail-dialog]');
      const career = dialog?.dataset.career || '';
      const nucleus = Number(dialog?.dataset.nucleus || 0);
      dialog?.close();
      openLoad(tab, career, nucleus);
    }
  }

  function handleInput(event) {
    if (!event.target.matches('[data-nuclei-search]')) return;
    searchText = event.target.value;
    applyFilters(event.currentTarget);
  }

  async function handleSubmit(event) {
    const form = event.target.closest('[data-nuclei-load-form]');
    if (!form) return;
    event.preventDefault();
    const reportId = Number(state.activeReport?.id || 0);
    if (!reportId || !loadTarget) return;

    const text = String(form.elements.text?.value || '').trim();
    if (!text) {
      form.elements.text?.focus();
      return;
    }

    const submit = form.querySelector('button[type="submit"]');
    const resultBox = form.querySelector('[data-load-result]');
    const original = submit?.textContent || 'Procesar y guardar';
    if (submit) {
      submit.disabled = true;
      submit.textContent = 'Procesando...';
    }
    if (resultBox) resultBox.innerHTML = '';

    try {
      const result = await api(`/api/reports/${reportId}/nuclei/import-text-v2`, {
        method: 'POST',
        body: JSON.stringify({ text, nucleus_number: loadTarget.nucleus, target_career: loadTarget.career }),
      });
      const s = result.summary || {};
      if (resultBox) resultBox.innerHTML = resultMarkup(result);
      toast(`Núcleo ${loadTarget.nucleus} guardado: ${Number(s.matched || 0)} de ${Number(s.detected || 0)} estudiantes conciliados.`, Number(s.review || 0) > 0);
      await renderNucleiModule();
      const refreshedDialog = document.querySelector('#tab-nuclei [data-nuclei-load-dialog]');
      refreshedDialog?.close();
      loadTarget = null;
    } catch (error) {
      if (resultBox) resultBox.innerHTML = `<div class="nuclei-load-error">${esc(error.message)}</div>`;
    } finally {
      if (submit && document.contains(submit)) {
        submit.disabled = false;
        submit.textContent = original;
      }
    }
  }

  function resultMarkup(result) {
    const s = result?.summary || {};
    const unmatched = Array.isArray(result?.unmatched) ? result.unmatched : [];
    return `<div class="nuclei-load-result ${Number(s.review || 0) ? 'warn' : 'ok'}">
      <strong>${Number(s.review || 0) ? 'Guardado con casos por revisar' : 'Guardado correctamente'}</strong>
      <span>${Number(s.matched || 0)}/${Number(s.detected || 0)} estudiantes conciliados · ${Number(s.approved || 0)} aprobados · ${Number(s.failed || 0)} reprobados</span>
      ${unmatched.length ? `<details><summary>${unmatched.length} caso${unmatched.length === 1 ? '' : 's'} por revisar</summary>${unmatched.map(item => `<p>${esc(item.name || item.email || 'Sin identificar')} · ${esc(item.grade ?? '—')}</p>`).join('')}</details>` : ''}
    </div>`;
  }

  function openLoad(tab, career, nucleus) {
    loadTarget = { career, nucleus };
    const dialog = tab.querySelector('[data-nuclei-load-dialog]');
    const form = dialog?.querySelector('[data-nuclei-load-form]');
    if (!dialog || !form) return;
    form.reset();
    form.querySelector('[data-load-title]').textContent = `Núcleo ${nucleus}`;
    form.querySelector('[data-load-subtitle]').textContent = career;
    form.querySelector('[data-load-result]').innerHTML = '';
    dialog.showModal();
    window.setTimeout(() => form.elements.text?.focus(), 80);
  }

  function openDetail(tab, group, slot) {
    const dialog = tab.querySelector('[data-nuclei-detail-dialog]');
    if (!dialog) return;
    dialog.dataset.career = group.career;
    dialog.dataset.nucleus = String(slot.number);
    dialog.querySelector('[data-detail-title]').textContent = `${group.career} · Núcleo ${slot.number}`;
    dialog.querySelector('[data-detail-subtitle]').textContent = `${slot.students.length} estudiantes · promedio ${fmt(slot.average)}`;
    dialog.querySelector('[data-detail-body]').innerHTML = detailMarkup(slot);
    dialog.showModal();
  }

  function detailMarkup(slot) {
    const counts = slot.counts;
    const reviewStudents = slot.students.filter(isReviewStudent);
    return `
      <div class="nuclei-detail-summary">
        <span><strong>${slot.students.length}</strong> estudiantes</span>
        <span><strong>${fmt(slot.average)}</strong> promedio</span>
        <span><strong>${counts.approved}</strong> aprobados</span>
        <span><strong>${counts.failed}</strong> reprobados</span>
      </div>
      ${slot.reviewCount ? `<div class="nuclei-review-banner"><strong>${slot.reviewCount} por revisar</strong><span>${slot.conflictCount ? `${slot.conflictCount} duplicado${slot.conflictCount === 1 ? '' : 's'} con información diferente. ` : ''}${reviewStudents.length ? `${reviewStudents.length} estudiante${reviewStudents.length === 1 ? '' : 's'} sin conciliación completa.` : ''}</span></div>` : ''}
      <div class="student-table-wrap nuclei-detail-table-wrap">
        <table class="student-table compact-table"><thead><tr><th>Cédula</th><th>Estudiante</th><th>Nota</th><th>Estado</th></tr></thead><tbody>
          ${slot.students.map(student => `<tr class="${isReviewStudent(student) ? 'needs-review' : ''}"><td>${esc(student.identification || student.cedula || '—')}</td><td>${esc(student.full_name || student.nombre || '—')}</td><td><strong>${fmt(numericGrade(student))}</strong></td><td>${esc(student.final_status || student.estado || 'No evaluado')}</td></tr>`).join('')}
        </tbody></table>
      </div>`;
  }

  function applyFilters(tab) {
    const query = normalize(tab.querySelector('[data-nuclei-search]')?.value || searchText);
    tab.querySelectorAll('[data-nuclei-row]').forEach(row => {
      const matchesSearch = !query || String(row.dataset.search || '').includes(query) || normalize(row.dataset.career).includes(query);
      const loaded = Number(row.dataset.loaded || 0);
      const review = Number(row.dataset.review || 0);
      const matchesMode = filterMode === 'pending' ? loaded < 4 : filterMode === 'review' ? review > 0 : true;
      row.hidden = !(matchesSearch && matchesMode);
    });
  }

  const style = document.createElement('style');
  style.textContent = `
    [data-nuclei-final-box], [data-nuclei-paste-box], .excel-nuclei-upload { display:none !important; }
    .nuclei-matrix-shell { display:grid; gap:16px; }
    .nuclei-matrix-heading { display:flex; justify-content:space-between; gap:18px; align-items:flex-end; }
    .nuclei-matrix-heading h2 { margin:0; font-size:22px; color:#173b57; }
    .nuclei-matrix-heading p { margin:4px 0 0; color:#64748b; font-size:12px; }
    .nuclei-legend { display:flex; gap:14px; flex-wrap:wrap; color:#64748b; font-size:11px; }
    .nuclei-legend span { display:flex; align-items:center; gap:6px; }
    .nuclei-legend .dot { width:8px; height:8px; border-radius:50%; display:inline-block; background:#cbd5e1; }
    .nuclei-legend .dot.ok { background:#22c55e; } .nuclei-legend .dot.warn { background:#f59e0b; }
    .nuclei-kpis { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); border:1px solid #e2e8f0; border-radius:14px; background:#fff; overflow:hidden; }
    .nuclei-kpi { padding:14px 16px; display:grid; gap:2px; border-right:1px solid #edf2f7; }
    .nuclei-kpi:last-child { border-right:0; } .nuclei-kpi strong { font-size:20px; color:#173b57; } .nuclei-kpi span { font-size:11px; color:#64748b; }
    .nuclei-kpi.attention strong { color:#b45309; }
    .nuclei-toolbar { display:flex; justify-content:space-between; align-items:end; gap:14px; }
    .nuclei-search { display:grid; gap:5px; width:min(430px,100%); color:#64748b; font-size:11px; font-weight:700; }
    .nuclei-search input { min-height:40px; border-radius:10px; }
    .nuclei-filter-tabs { display:inline-flex; gap:4px; padding:4px; background:#f1f5f9; border-radius:10px; }
    .nuclei-filter-button { border:0; background:transparent; padding:7px 11px; border-radius:8px; color:#64748b; cursor:pointer; font-weight:700; font-size:11px; }
    .nuclei-filter-button.active { background:#fff; color:#173b57; box-shadow:0 1px 3px rgba(15,23,42,.08); }
    .nuclei-matrix-wrap { overflow:auto; border:1px solid #e2e8f0; border-radius:14px; background:#fff; }
    .nuclei-matrix-table { width:100%; min-width:850px; border-collapse:collapse; table-layout:fixed; }
    .nuclei-matrix-table th, .nuclei-matrix-table td { border-bottom:1px solid #edf2f7; padding:10px 12px; text-align:center; }
    .nuclei-matrix-table thead th { position:sticky; top:0; z-index:2; background:#f8fafc; color:#64748b; font-size:11px; text-transform:uppercase; letter-spacing:.04em; }
    .nuclei-matrix-table thead th:first-child { text-align:left; width:37%; }
    .nuclei-matrix-table tbody th { text-align:left; font-weight:400; background:#fff; }
    .nuclei-matrix-table tbody th strong { display:block; color:#173b57; font-size:12px; }
    .nuclei-matrix-table tbody th span { display:block; margin-top:3px; color:#94a3b8; font-size:10px; }
    .nuclei-matrix-table tbody tr:last-child th, .nuclei-matrix-table tbody tr:last-child td { border-bottom:0; }
    .nuclei-matrix-table tr[hidden] { display:none; }
    .nuclei-cell { width:100%; min-height:48px; border:1px solid transparent; border-radius:10px; display:flex; align-items:center; justify-content:center; gap:7px; cursor:pointer; font:inherit; font-weight:800; transition:.15s ease; }
    .nuclei-cell:hover { transform:translateY(-1px); }
    .nuclei-cell.loaded { background:#f0fdf4; border-color:#bbf7d0; color:#166534; }
    .nuclei-cell.review { background:#fffbeb; border-color:#fde68a; color:#92400e; }
    .nuclei-cell.pending { background:#f8fafc; border-color:#e2e8f0; color:#64748b; }
    .nuclei-cell-icon { width:22px; height:22px; border-radius:50%; display:grid; place-items:center; background:rgba(255,255,255,.75); font-size:12px; }
    .nuclei-cell-label { font-size:11px; }
    .nuclei-dialog { width:min(760px,calc(100vw - 32px)); max-height:88vh; padding:0; border:0; border-radius:16px; box-shadow:0 24px 70px rgba(15,23,42,.22); }
    .nuclei-dialog::backdrop { background:rgba(15,23,42,.38); backdrop-filter:blur(2px); }
    .nuclei-dialog-card { padding:20px; display:grid; gap:16px; margin:0; }
    .nuclei-dialog-head { display:flex; justify-content:space-between; gap:16px; align-items:flex-start; }
    .nuclei-dialog-head h3 { margin:3px 0 2px; color:#173b57; font-size:19px; }
    .nuclei-dialog-head p { margin:0; color:#64748b; font-size:12px; }
    .nuclei-paste-field { display:grid; gap:7px; color:#334155; font-size:12px; font-weight:700; }
    .nuclei-paste-field textarea { width:100%; min-height:220px; resize:vertical; border-radius:11px; font-family:inherit; }
    .nuclei-dialog-help { margin:-6px 0 0; color:#64748b; font-size:11px; }
    .nuclei-dialog-actions { display:flex; justify-content:flex-end; gap:8px; }
    .nuclei-load-result, .nuclei-load-error, .nuclei-review-banner { padding:11px 12px; border-radius:10px; display:grid; gap:3px; font-size:11px; }
    .nuclei-load-result.ok { background:#f0fdf4; border:1px solid #bbf7d0; color:#166534; }
    .nuclei-load-result.warn, .nuclei-review-banner { background:#fffbeb; border:1px solid #fde68a; color:#92400e; }
    .nuclei-load-error { background:#fef2f2; border:1px solid #fecaca; color:#991b1b; }
    .nuclei-load-result details { margin-top:5px; }
    .nuclei-load-result p { margin:4px 0 0; }
    .nuclei-detail-summary { display:grid; grid-template-columns:repeat(4,1fr); border:1px solid #e2e8f0; border-radius:11px; overflow:hidden; }
    .nuclei-detail-summary span { padding:10px; display:grid; gap:2px; border-right:1px solid #edf2f7; color:#64748b; font-size:10px; }
    .nuclei-detail-summary span:last-child { border-right:0; } .nuclei-detail-summary strong { color:#173b57; font-size:15px; }
    .nuclei-detail-table-wrap { max-height:430px; overflow:auto; }
    .nuclei-detail-table-wrap tr.needs-review { background:#fffbeb; }
    @media (max-width:760px) {
      .nuclei-matrix-heading, .nuclei-toolbar { align-items:stretch; flex-direction:column; }
      .nuclei-kpis { grid-template-columns:repeat(2,1fr); }
      .nuclei-kpi:nth-child(2) { border-right:0; } .nuclei-kpi:nth-child(-n+2) { border-bottom:1px solid #edf2f7; }
      .nuclei-filter-tabs { width:100%; } .nuclei-filter-button { flex:1; }
      .nuclei-detail-summary { grid-template-columns:repeat(2,1fr); }
    }
  `;
  document.head.appendChild(style);
})();