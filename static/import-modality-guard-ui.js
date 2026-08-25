// Guarda ligera para importaciones heredadas. Los periodos unificados son
// gestionados por robust-import-ui.js y no deben tener observadores duplicados.
(function () {
  'use strict';

  function isUnifiedPeriod() {
    const project = state?.activeReport?.project_summary;
    return !!project && String(project.report_type || '').toLowerCase() !== 'pvc';
  }

  function metricValue(label) {
    const cards = [...document.querySelectorAll('#active-import-metrics .metric')];
    const card = cards.find(item => item.querySelector('span')?.textContent.trim() === label);
    const raw = card?.querySelector('strong')?.textContent || '';
    const value = Number(String(raw).replace(/[^0-9.-]/g, ''));
    return Number.isFinite(value) ? value : null;
  }

  function refresh() {
    if (isUnifiedPeriod()) return;
    const importDialog = document.getElementById('active-report-import-dialog');
    const confirmStep = document.getElementById('active-import-confirm-step');
    if (!importDialog || !importDialog.open || !confirmStep || confirmStep.hidden) return;

    const presencial = metricValue('Presencial');
    const online = metricValue('Online');
    if (presencial === null || online === null) return;

    const button = document.getElementById('commit-active-roster');
    if (button) button.disabled = presencial <= 0 || online <= 0;
  }

  function install() {
    const importDialog = document.getElementById('active-report-import-dialog');
    if (!importDialog || importDialog.dataset.modalityGuardObserved === '1') return;
    importDialog.dataset.modalityGuardObserved = '1';
    const observer = new MutationObserver(refresh);
    observer.observe(importDialog, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['hidden', 'disabled', 'open'],
    });
    refresh();
  }

  document.addEventListener('click', event => {
    if (!event.target?.closest?.('#report-import-roster, #roster-upload-btn, #roster-empty-upload')) return;
    queueMicrotask(install);
  }, true);

  document.addEventListener('change', event => {
    if (event.target?.id === 'active-roster-file') queueMicrotask(refresh);
  });

  install();
})();
