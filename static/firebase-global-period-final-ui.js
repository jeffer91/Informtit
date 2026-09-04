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

  function esc(value) {
    if (typeof escapeHtml === 'function') return escapeHtml(value || '');
    return String(value || '').replace(/[&<>"']/g, char => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;',
    }[char]));
  }

  const originalDashboard = renderDashboard;
  renderDashboard = function renderFirebaseGlobalPeriodDashboard() {
    const reports = Array.isArray(state?.reports) ? state.reports : [];
    const hasUnified = reports.some(isUnified);
    if (!hasUnified) {
      originalDashboard();
      return;
    }

    const complexive = reports.reduce((sum, report) => sum + Number(report.complexive_records || 0), 0);
    const careers = reports.reduce((sum, report) => sum + Number(report.career_count || 0), 0);
    const metrics = document.getElementById('dashboard-metrics');
    if (metrics) {
      metrics.innerHTML = [
        ['Períodos', reports.length],
        ['Carreras en Complexivo', careers],
        ['Registros en Complexivo', complexive],
        ['Base de datos', 'Firebase + caché'],
      ].map(([label, value]) => `<article class="metric"><span>${label}</span><strong>${value}</strong></article>`).join('');
    }

    const grid = document.getElementById('reports-grid');
    if (!grid) return;
    grid.className = 'reports-grid';
    if (!reports.length) {
      grid.innerHTML = '<div class="empty-mini">Todavía no existen períodos.</div>';
      return;
    }

    grid.innerHTML = reports.map(report => {
      const pvc = clean(report.report_type).toLowerCase() === 'pvc';
      const unified = isUnified(report);
      const badge = pvc ? 'PVC' : unified ? 'Período global' : (report.modality === 'en_linea' ? 'En línea' : 'Presencial');
      const code = pvc
        ? clean(report.code)
        : clean(report.code_presencial || report.code);
      const onlineCode = unified ? clean(report.code_online) : '';
      return `
        <article class="report-card">
          <span class="badge">${esc(badge)}</span>
          <h3>${esc(report.name || 'Informe del proceso de titulación')}</h3>
          <p>${esc(report.period || '')}</p>
          ${code ? `<p>${esc(code)}</p>` : ''}
          ${onlineCode ? `<p>${esc(onlineCode)}</p>` : ''}
          <div class="card-meta">
            <span>${Number(report.career_count || 0)} carreras globales</span>
            <span>${Number(report.student_count || report.complexive_records || 0)} registros globales</span>
          </div>
          <div class="report-card-actions">
            <button class="button primary small" data-open-report="${Number(report.id)}">Abrir</button>
            <button class="button danger small" data-delete-report="${Number(report.id)}">Eliminar</button>
          </div>
        </article>`;
    }).join('');

    grid.querySelectorAll('[data-open-report]').forEach(button => {
      button.onclick = () => openReport(Number(button.dataset.openReport));
    });
    grid.querySelectorAll('[data-delete-report]').forEach(button => {
      button.onclick = () => deleteReport(Number(button.dataset.deleteReport));
    });
  };

  const originalReport = renderReport;
  renderReport = function renderFirebaseGlobalPeriodReport() {
    originalReport();
    const report = state?.activeReport;
    if (!isUnified(report)) return;
    const modality = document.getElementById('report-modality');
    if (modality) modality.textContent = 'Período académico global';
    const generalForm = document.getElementById('general-form');
    const modalitySelect = generalForm?.elements?.modality;
    const modalityLabel = modalitySelect?.closest('label');
    if (modalityLabel) modalityLabel.style.display = 'none';
  };

  document.addEventListener('informtit:firebase-connected', () => {
    if (Array.isArray(state?.reports)) renderDashboard();
  });

  if (Array.isArray(state?.reports) && state.reports.length) renderDashboard();
})();