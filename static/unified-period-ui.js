(() => {
  'use strict';

  if (!/(^|\.)github\.io$/i.test(window.location.hostname)) return;
  if (typeof renderDashboard !== 'function' || typeof renderReport !== 'function') return;

  function clean(value) {
    return String(value ?? '').trim();
  }

  function isUnified(report) {
    return Boolean(report)
      && clean(report.report_type).toLowerCase() !== 'pvc'
      && (clean(report.modality) === 'unified' || Boolean(report.unified_period));
  }

  const previousDashboard = renderDashboard;
  renderDashboard = function renderUnifiedDashboard() {
    previousDashboard();
    (state.reports || []).forEach(report => {
      if (!isUnified(report)) return;
      const open = document.querySelector(`[data-open-report="${report.id}"]`);
      const card = open?.closest('.report-card');
      if (!card) return;
      const badge = card.querySelector('.badge');
      if (badge) badge.textContent = 'Período unificado';
      const meta = card.querySelector('.card-meta');
      if (meta) {
        const careers = Number(report.career_count || 0);
        const students = Number(report.student_count || 0);
        meta.innerHTML = `<span>${careers} carreras globales</span><span>${students} registros globales</span>`;
      }
    });
  };

  const previousReport = renderReport;
  renderReport = function renderUnifiedReport() {
    previousReport();
    const report = state.activeReport;
    if (!isUnified(report)) return;

    const badge = document.getElementById('report-modality');
    if (badge) badge.textContent = 'Período académico unificado';

    const general = document.getElementById('general-form');
    if (general) {
      const modality = general.elements?.modality;
      const label = modality?.closest('label');
      if (label) label.hidden = true;
    }
  };

  const previousSetType = typeof setReportDialogType === 'function' ? setReportDialogType : null;
  if (previousSetType) {
    setReportDialogType = function setUnifiedDialogType(type = 'normal') {
      previousSetType(type);
      const normalized = type === 'pvc' ? 'pvc' : 'normal';
      const note = document.getElementById('report-output-note');
      const help = document.getElementById('report-type-help');
      if (normalized === 'normal') {
        if (note) note.textContent = '1 período global → PDF Presencial + PDF Online';
        if (help) help.textContent = 'Se crea un solo informe del período. Informtit clasifica los datos y separa Presencial/Online al generar los PDFs.';
      }
    };
  }

  const style = document.createElement('style');
  style.textContent = `
    .report-card .badge { white-space: nowrap; }
  `;
  document.head.appendChild(style);
})();