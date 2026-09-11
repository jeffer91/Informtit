(() => {
  'use strict';

  if (!/(^|\.)github\.io$/i.test(window.location.hostname)) return;
  if (typeof window.renderReport !== 'function') return;

  const previousRenderReport = window.renderReport;

  const esc = value => typeof window.escapeHtml === 'function'
    ? window.escapeHtml(String(value ?? ''))
    : String(value ?? '').replace(/[&<>"']/g, char => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;',
    })[char]);

  const fmt = value => {
    if (value === null || value === undefined || value === '') return '—';
    const number = Number(value);
    return Number.isFinite(number) ? number.toFixed(2).replace('.', ',') : '—';
  };

  const isPvc = () => String(window.state?.activeReport?.report_type || '').toLowerCase() === 'pvc';
  const activeReportId = () => Number(window.state?.activeReport?.id || 0);

  function apiCall(path, options) {
    if (typeof window.api === 'function') return window.api(path, options);
    return window.fetch(path, options).then(async response => {
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.error || `Error ${response.status}`);
      return payload;
    });
  }

  function toastMessage(message, error = false) {
    if (typeof window.toast === 'function') window.toast(message, error);
  }

  function scheduleRow(item = {}, thesis = false) {
    return `<tr>
      ${thesis ? `<td><input class="table-input" name="phase" value="${esc(item.phase || '')}" placeholder="Fase"></td>` : ''}
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
        <div>
          <h2>${esc(title)}</h2>
          <p>Edición manual del cronograma correspondiente al período activo.</p>
        </div>
        <div class="process-actions">
          <button class="button secondary small" type="button" data-add-schedule>Agregar actividad</button>
          <button class="button primary small" type="button" data-save-schedule>Guardar cronograma</button>
        </div>
      </div>
      <div class="student-table-wrap">
        <table class="student-table schedule-table">
          <thead><tr>${thesis ? '<th>Fase</th>' : ''}<th>Actividad</th><th>Fecha inicio</th><th>Fecha fin</th><th></th></tr></thead>
          <tbody>${(rows || []).map(row => scheduleRow(row, thesis)).join('')}</tbody>
        </table>
      </div>
      <p class="field-help">Fuente temporal del cronograma: navegador. No se utilizan las funciones antiguas de importar, restaurar o analizar texto.</p>
    </section>`;
  }

  function collectSchedule(card, type) {
    return [...card.querySelectorAll('tbody tr')]
      .map(row => ({
        phase: type === 'thesis' ? row.querySelector('[name="phase"]')?.value?.trim() || '' : '',
        activity: row.querySelector('[name="activity"]')?.value?.trim() || '',
        start_date: row.querySelector('[name="start_date"]')?.value?.trim() || '',
        end_date: row.querySelector('[name="end_date"]')?.value?.trim() || '',
      }))
      .filter(row => row.activity);
  }

  function bindScheduleCard(card, type, reportId) {
    const thesis = type === 'thesis';
    card.querySelector('[data-add-schedule]')?.addEventListener('click', () => {
      card.querySelector('tbody')?.insertAdjacentHTML('beforeend', scheduleRow({}, thesis));
    });
    card.querySelectorAll('[data-remove-schedule]').forEach(button => {
      button.addEventListener('click', () => button.closest('tr')?.remove());
    });
    card.querySelector('[data-save-schedule]')?.addEventListener('click', async () => {
      try {
        const entries = collectSchedule(card, type);
        const result = await apiCall(`/api/reports/${reportId}/schedules/${type}`, {
          method: 'PUT',
          body: JSON.stringify({ entries }),
        });
        toastMessage(`${Number(result.count || entries.length)} actividades guardadas.`);
        await renderSchedules();
      } catch (error) {
        toastMessage(error.message || 'No se pudo guardar el cronograma.', true);
      }
    });
  }

  async function renderSchedules() {
    if (isPvc()) return;
    const reportId = activeReportId();
    const tab = document.querySelector('#tab-schedules');
    if (!reportId || !tab) return;
    const token = `${reportId}-${Date.now()}`;
    tab.dataset.pagesProcessesToken = token;
    tab.innerHTML = '<div class="panel"><div class="empty-mini">Cargando cronogramas...</div></div>';
    try {
      const data = await apiCall(`/api/reports/${reportId}/schedules`);
      if (activeReportId() !== reportId || tab.dataset.pagesProcessesToken !== token) return;
      const schedules = data.schedules || {};
      tab.innerHTML = `<div class="process-stack pages-process-stack">
        ${scheduleCard('complexive', 'Cronograma de Núcleos y Examen Complexivo', schedules.complexive || [])}
        ${scheduleCard('thesis', 'Cronograma de Trabajo de Titulación', schedules.thesis || [])}
      </div>`;
      tab.querySelectorAll('[data-pages-schedule]').forEach(card => bindScheduleCard(card, card.dataset.pagesSchedule, reportId));
    } catch (error) {
      tab.innerHTML = `<div class="panel"><div class="empty-mini">${esc(error.message || 'No se pudieron cargar los cronogramas.')}</div></div>`;
    }
  }

  function thesisCard(project) {
    const approved = String(project.final_status || '').toUpperCase() === 'APROBADO'
      || (project.final_grade !== null && project.final_grade !== undefined && Number(project.final_grade) >= 7);
    const status = project.final_grade === null || project.final_grade === undefined
      ? (project.final_status || 'Pendiente')
      : approved ? 'Aprobado' : 'Reprobado';
    return `<article class="career-card project-card pages-thesis-card">
      <div class="career-head">
        <div>
          <span class="badge">${esc(status)}</span>
          <h3>${esc(project.full_name || 'Sin nombre')}</h3>
          <p>${esc(project.identification || 'Sin cédula')} · ${esc(project.career_name || 'Sin carrera')}</p>
        </div>
      </div>
      <div class="summary-grid">
        <div class="summary-item"><span>Tutor</span><strong>${fmt(project.tutor_grade)}</strong></div>
        <div class="summary-item"><span>Lector</span><strong>${fmt(project.reader_grade)}</strong></div>
        <div class="summary-item"><span>Trabajo escrito</span><strong>${fmt(project.written_average)}</strong></div>
        <div class="summary-item"><span>Defensa</span><strong>${fmt(project.defense_average)}</strong></div>
        <div class="summary-item"><span>Nota final</span><strong>${fmt(project.final_grade)}</strong></div>
      </div>
      <div class="project-meta"><strong>Título:</strong> ${esc(project.title || '—')}</div>
      <div class="project-meta"><strong>Acta:</strong> ${esc(project.act_number || '—')} · ${esc(project.act_date || '—')}</div>
      <div class="project-meta"><strong>Tribunal:</strong> ${esc(project.vocal_1 || '—')} · ${esc(project.vocal_2 || '—')} · ${esc(project.vocal_3 || '—')}</div>
    </article>`;
  }

  async function renderThesis() {
    if (isPvc()) return;
    const reportId = activeReportId();
    const tab = document.querySelector('#tab-projects');
    if (!reportId || !tab) return;
    const token = `${reportId}-${Date.now()}`;
    tab.dataset.pagesProcessesToken = token;
    tab.innerHTML = '<div class="panel"><div class="empty-mini">Cargando Trabajo de Titulación...</div></div>';
    try {
      const data = await apiCall(`/api/reports/${reportId}/projects`);
      if (activeReportId() !== reportId || tab.dataset.pagesProcessesToken !== token) return;
      const projects = Array.isArray(data.projects) ? data.projects : [];
      const summary = data.summary || {};
      tab.innerHTML = `<div class="process-stack pages-process-stack">
        <section class="panel">
          <div id="pages-projects-readonly-note" class="empty-mini">Trabajo de Titulación se consulta directamente desde Google Sheets. Para cargar o actualizar resultados use la pestaña Importaciones.</div>
          <div class="panel-head"><div><h2>Trabajo de Titulación</h2><p>Vista institucional de solo lectura para el período activo.</p></div></div>
          <div class="summary-grid project-summary">
            <div class="summary-item"><span>Registrados</span><strong>${Number(summary.total || projects.length)}</strong></div>
            <div class="summary-item"><span>Aprobados</span><strong>${Number(summary.approved || 0)}</strong></div>
            <div class="summary-item"><span>Reprobados</span><strong>${Number(summary.failed || 0)}</strong></div>
            <div class="summary-item"><span>Promedio final</span><strong>${fmt(summary.average_final)}</strong></div>
          </div>
        </section>
        <section class="panel">
          <div class="panel-head"><div><h2>Registros</h2><p>Fuente: Google Sheets.</p></div></div>
          <div class="project-list">${projects.length ? projects.map(thesisCard).join('') : '<div class="empty-mini">No existen registros de Trabajo de Titulación para este período.</div>'}</div>
        </section>
      </div>`;
    } catch (error) {
      tab.innerHTML = `<div class="panel"><div class="empty-mini">${esc(error.message || 'No se pudo cargar Trabajo de Titulación.')}</div></div>`;
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
