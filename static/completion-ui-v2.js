(() => {
  const previousRenderReport = renderReport;
  let enhancementGeneration = 0;
  let eligibilityRequest = 0;

  function esc(value = '') {
    return typeof escapeHtml === 'function'
      ? escapeHtml(String(value))
      : String(value).replace(/[&<>"']/g, character => ({
          '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;',
        })[character]);
  }

  function fmt(value) {
    if (value === null || value === undefined || value === '') return '—';
    return Number(value).toFixed(2).replace('.', ',');
  }

  function summaryItem(label, value) {
    return `<div class="summary-item"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`;
  }

  function scheduleEnhancements() {
    const generation = ++enhancementGeneration;
    [80, 220, 500, 900, 1500].forEach(delay => {
      setTimeout(() => {
        if (generation !== enhancementGeneration || !state.activeReport?.id) return;
        enhanceSchedules();
        renderEligibility();
        renderCompletionPanel();
      }, delay);
    });
  }

  renderReport = function renderReportWithCompletionV2() {
    previousRenderReport();
    scheduleEnhancements();
  };

  const executionStatuses = [
    '',
    'Cumplido',
    'Cumplido con retraso',
    'Cumplido parcialmente',
    'No cumplido',
    'Reprogramado',
  ];

  function executionCells(item = {}) {
    return `
      <td><input class="table-input date-input" name="executed_date" value="${esc(item.executed_date || '')}" placeholder="dd/mm/aaaa"></td>
      <td><select class="table-input" name="execution_status">${executionStatuses.map(status => `<option value="${esc(status)}" ${status === (item.execution_status || '') ? 'selected' : ''}>${esc(status || 'Sin evaluar')}</option>`).join('')}</select></td>
      <td><input class="table-input compact-number" name="compliance_percentage" type="number" min="0" max="100" step="0.01" value="${item.compliance_percentage ?? ''}" placeholder="%"></td>
      <td><input class="table-input" name="evidence" value="${esc(item.evidence || '')}" placeholder="Acta, enlace o archivo"></td>
      <td><input class="table-input" name="observation" value="${esc(item.observation || '')}" placeholder="Novedad o explicación"></td>`;
  }

  function decorateScheduleTable(card, items) {
    const table = card.querySelector('table');
    if (!table) return false;
    const headerRow = table.querySelector('thead tr');
    if (!headerRow.querySelector('[data-execution-header]')) {
      headerRow.lastElementChild.insertAdjacentHTML('beforebegin', `
        <th data-execution-header>Fecha ejecutada</th>
        <th data-execution-header>Estado</th>
        <th data-execution-header>% cumplimiento</th>
        <th data-execution-header>Evidencia</th>
        <th data-execution-header>Observación</th>`);
    }
    [...table.querySelectorAll('tbody tr')].forEach((row, index) => {
      if (!row.querySelector('[name="executed_date"]')) {
        row.lastElementChild.insertAdjacentHTML('beforebegin', executionCells(items[index] || {}));
      }
    });
    return true;
  }

  function collectExtendedSchedule(card, type) {
    return [...card.querySelectorAll('tbody tr')]
      .map(row => ({
        phase: type === 'thesis' ? row.querySelector('[name="phase"]')?.value || '' : '',
        activity: row.querySelector('[name="activity"]')?.value || '',
        start_date: row.querySelector('[name="start_date"]')?.value || '',
        end_date: row.querySelector('[name="end_date"]')?.value || '',
        executed_date: row.querySelector('[name="executed_date"]')?.value || '',
        execution_status: row.querySelector('[name="execution_status"]')?.value || '',
        compliance_percentage: row.querySelector('[name="compliance_percentage"]')?.value || '',
        evidence: row.querySelector('[name="evidence"]')?.value || '',
        observation: row.querySelector('[name="observation"]')?.value || '',
      }))
      .filter(item => item.activity.trim());
  }

  async function enhanceSchedules() {
    const reportId = Number(state.activeReport?.id || 0);
    const tab = document.querySelector('#tab-schedules');
    if (!reportId || !tab?.querySelector('[data-schedule-card]')) return;
    try {
      const data = await api(`/api/reports/${reportId}/schedules`);
      if (Number(state.activeReport?.id || 0) !== reportId) return;
      for (const type of ['complexive', 'thesis']) {
        const card = tab.querySelector(`[data-schedule-card="${type}"]`);
        if (!card || !decorateScheduleTable(card, data.schedules[type] || [])) continue;
        if (card.dataset.extendedSaveBound === '1') continue;
        card.dataset.extendedSaveBound = '1';
        card.addEventListener('click', async event => {
          const saveButton = event.target.closest(`[data-save-schedule="${type}"]`);
          if (!saveButton) return;
          event.preventDefault();
          event.stopImmediatePropagation();
          try {
            const entries = collectExtendedSchedule(card, type);
            const result = await api(`/api/reports/${reportId}/schedules/${type}`, {
              method: 'PUT',
              body: JSON.stringify({ entries }),
            });
            toast(`${result.count} actividades y su ejecución fueron guardadas.`);
            renderReport();
          } catch (error) {
            toast(error.message, true);
          }
        }, true);
      }
    } catch (_error) {
      // La interfaz original permanece disponible.
    }
  }

  function statusClass(status) {
    if (status === 'Habilitado') return 'eligibility-ok';
    if (status === 'No habilitado') return 'eligibility-fail';
    if (status === 'Trabajo de Titulación') return 'eligibility-thesis';
    return 'eligibility-pending';
  }

  function eligibilitySignature(data) {
    return JSON.stringify({
      summary: data.summary,
      careers: data.careers,
      rows: data.rows.map(row => [row.student_id, row.nucleus_1, row.nucleus_2, row.nucleus_3, row.nucleus_4, row.status]),
      unmatched: data.unmatched.map(row => [row.email, row.nucleus_number, row.grade]),
    });
  }

  function eligibilityTable(data) {
    const candidates = data.rows.filter(row => row.option === 'Examen Complexivo');
    return `<details class="eligibility-details" open>
      <summary>Matriz individual de los cuatro núcleos (${candidates.length} estudiantes)</summary>
      <div class="eligibility-filter"><input type="search" data-eligibility-search placeholder="Buscar por cédula, nombre o carrera"></div>
      <div class="student-table-wrap">
        <table class="student-table compact-table eligibility-table">
          <thead><tr><th>Cédula</th><th>Estudiante</th><th>Carrera</th><th>Núcleo 1</th><th>Núcleo 2</th><th>Núcleo 3</th><th>Núcleo 4</th><th>Estado</th></tr></thead>
          <tbody>${candidates.map(row => `<tr data-search-value="${esc(`${row.identification} ${row.full_name} ${row.career_name}`.toLowerCase())}">
            <td>${esc(row.identification || '—')}</td><td>${esc(row.full_name)}</td><td>${esc(row.career_name)}</td>
            <td>${fmt(row.nucleus_1)}</td><td>${fmt(row.nucleus_2)}</td><td>${fmt(row.nucleus_3)}</td><td>${fmt(row.nucleus_4)}</td>
            <td><span class="eligibility-status ${statusClass(row.status)}">${esc(row.status)}</span></td>
          </tr>`).join('')}</tbody>
        </table>
      </div>
    </details>`;
  }

  function eligibilityMarkup(data, reportId, signature) {
    const summary = data.summary;
    return `<section class="panel eligibility-panel" data-eligibility-panel="${reportId}" data-eligibility-signature="${esc(signature)}">
      <div class="panel-head"><div><h2>Habilitación para el Examen Complexivo</h2><p>Cada estudiante debe aprobar los cuatro núcleos con una calificación mínima de 7,00. Los núcleos no se compensan entre sí.</p></div></div>
      <div class="summary-grid">
        ${summaryItem('Candidatos a Complexivo', summary.complexive_candidates)}
        ${summaryItem('Habilitados', summary.habilitated)}
        ${summaryItem('No habilitados', summary.not_habilitated)}
        ${summaryItem('Pendientes', summary.pending)}
        ${summaryItem('Trabajo de Titulación', summary.thesis_students)}
        ${summaryItem('Habilitación', `${fmt(summary.habilitation_percentage)} %`)}
      </div>
      <h3>Resultado por carrera</h3>
      <div class="student-table-wrap"><table class="student-table compact-table"><thead><tr><th>Carrera</th><th>Candidatos</th><th>Habilitados</th><th>No habilitados</th><th>Pendientes</th><th>% habilitación</th></tr></thead><tbody>${data.careers.map(row => `<tr><td>${esc(row.career_name)}</td><td>${row.total}</td><td>${row.habilitated}</td><td>${row.not_habilitated}</td><td>${row.pending}</td><td>${fmt(row.habilitation_percentage)} %</td></tr>`).join('')}</tbody></table></div>
      ${eligibilityTable(data)}
      ${data.unmatched.length ? `<details class="eligibility-details"><summary>${data.unmatched.length} calificación(es) de núcleo sin coincidencia</summary><div class="student-table-wrap"><table class="student-table compact-table"><thead><tr><th>Carrera</th><th>Núcleo</th><th>Nombre</th><th>Correo</th><th>Nota</th></tr></thead><tbody>${data.unmatched.map(row => `<tr><td>${esc(row.career_name)}</td><td>${row.nucleus_number}</td><td>${esc(row.full_name)}</td><td>${esc(row.email)}</td><td>${fmt(row.grade)}</td></tr>`).join('')}</tbody></table></div></details>` : ''}
    </section>`;
  }

  function bindEligibilitySearch(panel) {
    const search = panel?.querySelector('[data-eligibility-search]');
    if (!search || search.dataset.bound === '1') return;
    search.dataset.bound = '1';
    search.addEventListener('input', () => {
      const query = search.value.trim().toLowerCase();
      panel.querySelectorAll('.eligibility-table tbody tr').forEach(row => {
        row.hidden = Boolean(query && !row.dataset.searchValue.includes(query));
      });
    });
  }

  async function renderEligibility() {
    const reportId = Number(state.activeReport?.id || 0);
    const tab = document.querySelector('#tab-nuclei');
    const stack = tab?.querySelector('.process-stack');
    if (!reportId || !stack) return;
    const request = ++eligibilityRequest;
    try {
      const data = await api(`/api/reports/${reportId}/nuclei/eligibility`);
      if (request !== eligibilityRequest || Number(state.activeReport?.id || 0) !== reportId) return;
      const signature = eligibilitySignature(data);
      let panel = tab.querySelector('[data-eligibility-panel]');
      if (panel?.dataset.eligibilitySignature !== signature) {
        panel?.remove();
        stack.insertAdjacentHTML('beforeend', eligibilityMarkup(data, reportId, signature));
        panel = tab.querySelector('[data-eligibility-panel]');
      }
      bindEligibilitySearch(panel);
      renderComplexiveEligibilityWarning(data, reportId, signature);
    } catch (_error) {
      // Se mantiene el módulo de notas aunque no pueda generarse la matriz.
    }
  }

  function normalize(value = '') {
    return String(value).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
  }

  function renderComplexiveEligibilityWarning(data, reportId, eligibilitySignatureValue) {
    const tab = document.querySelector('#tab-careers');
    if (!tab) return;
    const eligibilityByName = new Map(data.rows.map(row => [`${normalize(row.career_name)}|${normalize(row.full_name)}`, row]));
    const conflicts = [];
    for (const career of state.activeReport?.careers || []) {
      for (const student of career.students || []) {
        const hasGrade = ['ordinary_theory', 'ordinary_practical', 'supplementary_theory', 'supplementary_practical'].some(key => student[key] !== null && student[key] !== undefined);
        if (!hasGrade) continue;
        const row = eligibilityByName.get(`${normalize(career.name)}|${normalize(student.full_name)}`);
        if (!row || row.status !== 'Habilitado') conflicts.push({ career: career.name, name: student.full_name, status: row?.status || 'Sin coincidencia' });
      }
    }
    const warningSignature = `${eligibilitySignatureValue}|${JSON.stringify(conflicts)}`;
    const existing = tab.querySelector('[data-complexive-eligibility-warning]');
    if (existing?.dataset.warningSignature === warningSignature) return;
    existing?.remove();
    const panel = document.createElement('section');
    panel.className = `panel complexive-eligibility-warning ${conflicts.length ? 'has-conflicts' : ''}`;
    panel.dataset.complexiveEligibilityWarning = String(reportId);
    panel.dataset.warningSignature = warningSignature;
    panel.innerHTML = conflicts.length
      ? `<div class="panel-head"><div><h2>Validación previa del Examen Complexivo</h2><p>Se encontraron ${conflicts.length} registro(s) con notas de Complexivo sin habilitación confirmada en los cuatro núcleos.</p></div></div><details><summary>Revisar casos</summary><ul>${conflicts.map(item => `<li>${esc(item.name)} · ${esc(item.career)} · ${esc(item.status)}</li>`).join('')}</ul></details>`
      : `<div class="panel-head"><div><h2>Validación previa del Examen Complexivo</h2><p>Los registros evaluados coinciden con estudiantes habilitados por los cuatro núcleos.</p></div></div>`;
    tab.prepend(panel);
  }

  function incidentRow(item = {}) {
    return `<tr><td><input class="table-input" name="category" value="${esc(item.category || '')}" placeholder="Notas, requisitos, plataforma..."></td><td><textarea class="table-input" name="description" rows="2" placeholder="Descripción de la novedad">${esc(item.description || '')}</textarea></td><td><input class="table-input" name="responsible" value="${esc(item.responsible || '')}" placeholder="Unidad responsable"></td><td><textarea class="table-input" name="treatment" rows="2" placeholder="Tratamiento aplicado">${esc(item.treatment || '')}</textarea></td><td><select class="table-input" name="status">${['Abierto', 'En seguimiento', 'Resuelto'].map(status => `<option ${status === (item.status || 'Abierto') ? 'selected' : ''}>${status}</option>`).join('')}</select></td><td><input class="table-input" name="evidence" value="${esc(item.evidence || '')}" placeholder="Evidencia"></td><td><button type="button" class="button danger small" data-remove-completion-row>Eliminar</button></td></tr>`;
  }

  function actionRow(item = {}) {
    return `<tr><td><textarea class="table-input" name="finding" rows="2" placeholder="Hallazgo">${esc(item.finding || '')}</textarea></td><td><textarea class="table-input" name="action" rows="2" placeholder="Acción de mejora">${esc(item.action || '')}</textarea></td><td><input class="table-input" name="responsible" value="${esc(item.responsible || '')}" placeholder="Responsable"></td><td><input class="table-input date-input" name="due_date" value="${esc(item.due_date || '')}" placeholder="dd/mm/aaaa"></td><td><input class="table-input" name="indicator" value="${esc(item.indicator || '')}" placeholder="Indicador"></td><td><input class="table-input" name="evidence" value="${esc(item.evidence || '')}" placeholder="Evidencia"></td><td><select class="table-input" name="status">${['Pendiente', 'En ejecución', 'Cumplida'].map(status => `<option ${status === (item.status || 'Pendiente') ? 'selected' : ''}>${status}</option>`).join('')}</select></td><td><button type="button" class="button danger small" data-remove-completion-row>Eliminar</button></td></tr>`;
  }

  function completionMarkup(data, reportId) {
    return `<section class="panel completion-panel" data-completion-panel="${reportId}"><div class="panel-head"><div><h2>Novedades, incidencias y plan de mejora</h2><p>Registre únicamente situaciones verificadas. Estos datos se incorporarán al informe final.</p></div><button class="button primary small" data-save-completion>Guardar seguimiento</button></div><h3>Novedades e incidencias</h3><div class="student-table-wrap"><table class="student-table completion-table" data-incident-table><thead><tr><th>Categoría</th><th>Descripción</th><th>Responsable</th><th>Tratamiento</th><th>Estado</th><th>Evidencia</th><th></th></tr></thead><tbody>${data.incidents.map(incidentRow).join('')}</tbody></table></div><button type="button" class="button secondary small" data-add-incident>Agregar incidencia</button><h3>Plan de mejora</h3><div class="student-table-wrap"><table class="student-table completion-table" data-action-table><thead><tr><th>Hallazgo</th><th>Acción</th><th>Responsable</th><th>Fecha límite</th><th>Indicador</th><th>Evidencia</th><th>Estado</th><th></th></tr></thead><tbody>${data.actions.map(actionRow).join('')}</tbody></table></div><button type="button" class="button secondary small" data-add-action>Agregar acción</button></section>`;
  }

  function collectRows(table, fields) {
    return [...table.querySelectorAll('tbody tr')].map(row => Object.fromEntries(fields.map(field => [field, row.querySelector(`[name="${field}"]`)?.value || ''])));
  }

  async function renderCompletionPanel() {
    const reportId = Number(state.activeReport?.id || 0);
    const tab = document.querySelector('#tab-schedules');
    const stack = tab?.querySelector('.process-stack');
    if (!reportId || !stack || tab.querySelector(`[data-completion-panel="${reportId}"]`)) return;
    try {
      const data = await api(`/api/reports/${reportId}/completion`);
      if (Number(state.activeReport?.id || 0) !== reportId || tab.querySelector(`[data-completion-panel="${reportId}"]`)) return;
      stack.insertAdjacentHTML('beforeend', completionMarkup(data, reportId));
      const panel = stack.querySelector(`[data-completion-panel="${reportId}"]`);
      panel.addEventListener('click', async event => {
        if (event.target.closest('[data-remove-completion-row]')) return event.target.closest('tr').remove();
        if (event.target.closest('[data-add-incident]')) return panel.querySelector('[data-incident-table] tbody').insertAdjacentHTML('beforeend', incidentRow());
        if (event.target.closest('[data-add-action]')) return panel.querySelector('[data-action-table] tbody').insertAdjacentHTML('beforeend', actionRow());
        if (event.target.closest('[data-save-completion]')) {
          try {
            const incidents = collectRows(panel.querySelector('[data-incident-table]'), ['category', 'description', 'responsible', 'treatment', 'status', 'evidence']);
            const actions = collectRows(panel.querySelector('[data-action-table]'), ['finding', 'action', 'responsible', 'due_date', 'indicator', 'evidence', 'status']);
            const result = await api(`/api/reports/${reportId}/completion`, { method: 'PUT', body: JSON.stringify({ incidents, actions }) });
            toast(`${result.incident_count} incidencias y ${result.action_count} acciones guardadas.`);
          } catch (error) {
            toast(error.message, true);
          }
        }
      });
    } catch (_error) {
      // Los cronogramas permanecen operativos.
    }
  }

  const style = document.createElement('style');
  style.textContent = `
    .schedule-table { min-width: 1650px; }
    .compact-number { min-width: 90px; }
    .eligibility-panel, .completion-panel { margin-top: 18px; }
    .eligibility-details { margin-top: 16px; }
    .eligibility-details summary { cursor: pointer; font-weight: 700; }
    .eligibility-filter { margin: 12px 0; }
    .eligibility-filter input { width: min(520px, 100%); }
    .eligibility-status { display: inline-flex; padding: 4px 8px; border-radius: 999px; font-size: 12px; font-weight: 700; white-space: nowrap; }
    .eligibility-ok { background: #dcfce7; color: #166534; }
    .eligibility-fail { background: #fee2e2; color: #991b1b; }
    .eligibility-pending { background: #fef3c7; color: #92400e; }
    .eligibility-thesis { background: #dbeafe; color: #1e40af; }
    .complexive-eligibility-warning { margin-bottom: 18px; border-left: 4px solid #16a34a; }
    .complexive-eligibility-warning.has-conflicts { border-left-color: #dc2626; }
    .completion-table { min-width: 1450px; }
    .completion-table textarea { min-width: 240px; resize: vertical; }
  `;
  document.head.appendChild(style);

  document.addEventListener('click', event => {
    if (event.target.closest('[data-tab="schedules"], [data-tab="nuclei"], [data-tab="careers"], [data-save-nucleus], [data-save-schedule]')) {
      scheduleEnhancements();
    }
  });
  scheduleEnhancements();
})();
