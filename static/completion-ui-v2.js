(() => {
  const previousRenderReport = renderReport;
  let enhancementGeneration = 0;

  function esc(value = '') {
    return typeof escapeHtml === 'function'
      ? escapeHtml(String(value))
      : String(value).replace(/[&<>"']/g, character => ({
          '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;',
        })[character]);
  }

  function scheduleEnhancements() {
    const generation = ++enhancementGeneration;
    [80, 220, 500, 900].forEach(delay => {
      setTimeout(() => {
        if (generation !== enhancementGeneration || !state.activeReport?.id) return;
        enhanceSchedules();
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
    if (!headerRow) return false;
    if (!headerRow.querySelector('[data-execution-header]')) {
      headerRow.lastElementChild?.insertAdjacentHTML('beforebegin', `
        <th data-execution-header>Fecha ejecutada</th>
        <th data-execution-header>Estado</th>
        <th data-execution-header>% cumplimiento</th>
        <th data-execution-header>Evidencia</th>
        <th data-execution-header>Observación</th>`);
    }
    [...table.querySelectorAll('tbody tr')].forEach((row, index) => {
      if (!row.querySelector('[name="executed_date"]')) {
        row.lastElementChild?.insertAdjacentHTML('beforebegin', executionCells(items[index] || {}));
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
      // Los cronogramas permanecen disponibles aunque falle la ampliación de ejecución.
    }
  }

  function incidentRow(item = {}) {
    return `<tr><td><input class="table-input" name="category" value="${esc(item.category || '')}" placeholder="Categoría"></td><td><textarea class="table-input" name="description" rows="2" placeholder="Descripción de la novedad">${esc(item.description || '')}</textarea></td><td><input class="table-input" name="responsible" value="${esc(item.responsible || '')}" placeholder="Unidad responsable"></td><td><textarea class="table-input" name="treatment" rows="2" placeholder="Tratamiento aplicado">${esc(item.treatment || '')}</textarea></td><td><select class="table-input" name="status">${['Abierto', 'En seguimiento', 'Resuelto'].map(status => `<option ${status === (item.status || 'Abierto') ? 'selected' : ''}>${status}</option>`).join('')}</select></td><td><input class="table-input" name="evidence" value="${esc(item.evidence || '')}" placeholder="Evidencia"></td><td><button type="button" class="button danger small" data-remove-completion-row>Eliminar</button></td></tr>`;
  }

  function actionRow(item = {}) {
    return `<tr><td><textarea class="table-input" name="finding" rows="2" placeholder="Hallazgo">${esc(item.finding || '')}</textarea></td><td><textarea class="table-input" name="action" rows="2" placeholder="Acción de mejora">${esc(item.action || '')}</textarea></td><td><input class="table-input" name="responsible" value="${esc(item.responsible || '')}" placeholder="Responsable"></td><td><input class="table-input date-input" name="due_date" value="${esc(item.due_date || '')}" placeholder="dd/mm/aaaa"></td><td><input class="table-input" name="indicator" value="${esc(item.indicator || '')}" placeholder="Indicador"></td><td><input class="table-input" name="evidence" value="${esc(item.evidence || '')}" placeholder="Evidencia"></td><td><select class="table-input" name="status">${['Pendiente', 'En ejecución', 'Cumplida'].map(status => `<option ${status === (item.status || 'Pendiente') ? 'selected' : ''}>${status}</option>`).join('')}</select></td><td><button type="button" class="button danger small" data-remove-completion-row>Eliminar</button></td></tr>`;
  }

  function completionMarkup(data, reportId) {
    return `<section class="panel completion-panel" data-completion-panel="${reportId}"><div class="panel-head"><div><h2>Novedades, incidencias y plan de mejora</h2><p>Registre situaciones verificadas del informe. Este bloque no vincula las poblaciones de los cuatro módulos.</p></div><button class="button primary small" data-save-completion>Guardar seguimiento</button></div><h3>Novedades e incidencias</h3><div class="student-table-wrap"><table class="student-table completion-table" data-incident-table><thead><tr><th>Categoría</th><th>Descripción</th><th>Responsable</th><th>Tratamiento</th><th>Estado</th><th>Evidencia</th><th></th></tr></thead><tbody>${data.incidents.map(incidentRow).join('')}</tbody></table></div><button type="button" class="button secondary small" data-add-incident>Agregar incidencia</button><h3>Plan de mejora</h3><div class="student-table-wrap"><table class="student-table completion-table" data-action-table><thead><tr><th>Hallazgo</th><th>Acción</th><th>Responsable</th><th>Fecha límite</th><th>Indicador</th><th>Evidencia</th><th>Estado</th><th></th></tr></thead><tbody>${data.actions.map(actionRow).join('')}</tbody></table></div><button type="button" class="button secondary small" data-add-action>Agregar acción</button></section>`;
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
      panel?.addEventListener('click', async event => {
        if (event.target.closest('[data-remove-completion-row]')) return event.target.closest('tr')?.remove();
        if (event.target.closest('[data-add-incident]')) return panel.querySelector('[data-incident-table] tbody')?.insertAdjacentHTML('beforeend', incidentRow());
        if (event.target.closest('[data-add-action]')) return panel.querySelector('[data-action-table] tbody')?.insertAdjacentHTML('beforeend', actionRow());
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
    .completion-panel { margin-top: 18px; }
    .completion-table { min-width: 1450px; }
    .completion-table textarea { min-width: 240px; resize: vertical; }
  `;
  document.head.appendChild(style);

  document.addEventListener('click', event => {
    if (event.target.closest('[data-tab="schedules"], [data-save-schedule]')) scheduleEnhancements();
  });
  scheduleEnhancements();
})();
