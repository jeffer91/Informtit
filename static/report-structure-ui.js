(() => {
  function escapeLocal(value = '') {
    return typeof escapeHtml === 'function'
      ? escapeHtml(String(value))
      : String(value).replace(/[&<>"']/g, character => ({
          '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;',
        })[character]);
  }

  function normalizeStatus(value = '') {
    return String(value).trim().toUpperCase();
  }

  function enhanceGeneralForm() {
    const form = document.querySelector('#general-form');
    if (!form || form.querySelector('[name="cutoff_date"]')) return;
    const grid = form.querySelector('.form-grid');
    if (!grid) return;
    const label = document.createElement('label');
    label.innerHTML = `Fecha de corte de la información
      <input type="date" name="cutoff_date" value="${escapeLocal(state.activeReport?.cutoff_date || '')}">
      <small class="field-help">Se usa en la introducción. Si queda vacía, la fecha no se menciona.</small>`;
    const elaboration = grid.querySelector('[name="elaboration_date"]')?.closest('label');
    if (elaboration) elaboration.insertAdjacentElement('afterend', label);
    else grid.appendChild(label);
  }

  const requirements = [
    ['academic_status', 'Académico'],
    ['documentation_status', 'Documentación'],
    ['english_status', 'Inglés'],
    ['financial_status', 'Financiero'],
    ['data_update_status', 'Actualización de datos'],
    ['graduate_followup_status', 'Seguimiento a graduados'],
    ['practices_linkage_status', 'Prácticas'],
    ['linkage_status', 'Vinculación'],
  ];

  function classifyStudent(student, active) {
    const values = active.map(([key]) => normalizeStatus(student[key]));
    if (values.some(value => value === 'NO CUMPLE')) return 'pending';
    if (values.some(value => !value)) return 'incomplete';
    return values.every(value => value === 'CUMPLE') ? 'complete' : 'incomplete';
  }

  async function enhanceRosterAnalysis() {
    const tab = document.querySelector('#tab-roster');
    const reportId = Number(state.activeReport?.id || 0);
    if (!tab || !reportId) return;

    if (Number(tab.dataset.requirementReportId || 0) !== reportId) {
      tab.querySelectorAll('[data-requirement-analysis]').forEach(node => node.remove());
      tab.dataset.requirementReportId = String(reportId);
      tab.dataset.requirementLoading = '0';
    }
    if (tab.querySelector('[data-requirement-analysis]') || tab.dataset.requirementLoading === '1') return;
    tab.dataset.requirementLoading = '1';

    try {
      const data = await api(`/api/reports/${reportId}/roster`);
      if (Number(state.activeReport?.id || 0) !== reportId) return;
      const students = data.students || [];
      if (!students.length) return;
      const active = requirements.filter(([key]) => students.some(student => String(student[key] || '').trim()));
      if (!active.length) return;

      const total = students.length;
      const states = students.map(student => classifyStudent(student, active));
      const complete = states.filter(value => value === 'complete').length;
      const pending = states.filter(value => value === 'pending').length;
      const incomplete = states.filter(value => value === 'incomplete').length;
      const rows = active.map(([key, label]) => {
        const values = students.map(student => normalizeStatus(student[key]));
        const complies = values.filter(value => value === 'CUMPLE').length;
        const doesNot = values.filter(value => value === 'NO CUMPLE').length;
        const blank = values.filter(value => !value).length;
        return { label, complies, doesNot, blank, percentage: total ? complies / total * 100 : 0 };
      });
      const lowest = [...rows].sort((a, b) => a.percentage - b.percentage)[0];

      const section = document.createElement('section');
      section.className = 'panel requirement-analysis-panel';
      section.dataset.requirementAnalysis = '1';
      section.innerHTML = `
        <div class="panel-head">
          <div>
            <h2>Análisis del cumplimiento de requisitos</h2>
            <p>Módulo independiente. Este análisis no habilita ni excluye registros de Núcleos, Examen Complexivo o Trabajo de Titulación.</p>
          </div>
        </div>
        <div class="summary-grid">
          <div class="summary-item"><span>Registrados</span><strong>${total}</strong></div>
          <div class="summary-item"><span>Cumplimiento integral</span><strong>${complete}</strong></div>
          <div class="summary-item"><span>Con pendientes</span><strong>${pending}</strong></div>
          <div class="summary-item"><span>Información incompleta</span><strong>${incomplete}</strong></div>
          <div class="summary-item"><span>Porcentaje integral</span><strong>${(complete / total * 100).toFixed(2).replace('.', ',')} %</strong></div>
        </div>
        <p class="requirement-analysis-text">El requisito con menor cumplimiento es <strong>${escapeLocal(lowest.label)}</strong>, con ${lowest.complies} de ${total} estudiantes (${lowest.percentage.toFixed(2).replace('.', ',')} %).</p>
        <div class="student-table-wrap">
          <table class="student-table compact-table">
            <thead><tr><th>Requisito</th><th>Cumple</th><th>No cumple</th><th>Sin información</th><th>Cumplimiento</th></tr></thead>
            <tbody>${rows.map(row => `<tr><td>${escapeLocal(row.label)}</td><td>${row.complies}</td><td>${row.doesNot}</td><td>${row.blank}</td><td>${row.percentage.toFixed(2).replace('.', ',')} %</td></tr>`).join('')}</tbody>
          </table>
        </div>`;
      tab.prepend(section);
    } catch (_error) {
      // La pestaña principal conserva su funcionamiento aunque falle esta vista auxiliar.
    } finally {
      if (Number(tab.dataset.requirementReportId || 0) === reportId) {
        tab.dataset.requirementLoading = '0';
      }
    }
  }

  const style = document.createElement('style');
  style.textContent = `
    .field-help { display: block; margin-top: 5px; color: #64748b; font-size: 12px; font-weight: 400; }
    .requirement-analysis-panel { margin-bottom: 18px; }
    .requirement-analysis-text { margin: 14px 0; color: #334155; }
  `;
  document.head.appendChild(style);

  let scanQueued = false;
  function scan() {
    enhanceGeneralForm();
    enhanceRosterAnalysis();
  }

  function scheduleScan() {
    if (scanQueued) return;
    scanQueued = true;
    requestAnimationFrame(() => {
      scanQueued = false;
      scan();
    });
  }

  // Este complemento solo trabaja dentro del contenido principal. Observar
  // document.body hacía que cualquier cambio de diálogos, overlays o progreso
  // de PDF activara análisis innecesarios del módulo Requisitos.
  const mainRoot = document.querySelector('.main');
  if (mainRoot) {
    new MutationObserver(records => {
      if (records.some(record => record.addedNodes.length || record.removedNodes.length)) {
        scheduleScan();
      }
    }).observe(mainRoot, { childList: true, subtree: true });
  }

  document.addEventListener('click', event => {
    if (event.target.closest('[data-tab="general"], [data-tab="roster"]')) scheduleScan();
  });
  scheduleScan();
})();
