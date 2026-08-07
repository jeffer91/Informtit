(() => {
  function cleanRoster() {
    const tab = document.querySelector('#tab-roster');
    if (!tab) return;

    const heading = tab.querySelector('.roster-head h2');
    const description = tab.querySelector('.roster-head p');
    if (heading) heading.textContent = 'Requisitos';
    if (description) description.innerHTML = 'Módulo independiente. La información cargada aquí no modifica Núcleos, Examen Complexivo ni Trabajo de Titulación.';

    tab.querySelectorAll('.roster-metric').forEach(metric => {
      const label = metric.querySelector('span')?.textContent?.trim() || '';
      if (label === 'Notas cargadas') metric.remove();
    });

    const filter = tab.querySelector('#roster-requirement-filter');
    filter?.querySelector('option[value="notes_pending"]')?.remove();

    const table = tab.querySelector('.roster-table');
    if (table) {
      table.querySelectorAll('tr').forEach(row => {
        const cells = [...row.children];
        const last = cells[cells.length - 1];
        if (last && (last.textContent.trim() === 'Notas' || cells.length >= 22)) last.remove();
      });
    }

    ['#roster-upload-btn', '#roster-empty-upload', '#report-import-roster'].forEach(selector => {
      const button = document.querySelector(selector);
      if (button) button.textContent = button.id === 'report-import-roster' ? 'Subir requisitos .xls' : 'Cargar requisitos .xls';
    });
  }

  function cleanImportWarning() {
    const warning = document.querySelector('#active-report-import-dialog .replace-warning');
    if (!warning) return;
    const strong = warning.querySelector('strong');
    const span = warning.querySelector('span');
    if (strong) strong.textContent = 'La importación reemplazará únicamente los datos del módulo Requisitos.';
    if (span) span.textContent = 'Núcleos, Examen Complexivo y Trabajo de Titulación no se modificarán.';
  }

  function clarifyDashboardCounts() {
    document.querySelectorAll('#dashboard-metrics .metric').forEach(metric => {
      const label = metric.querySelector('span');
      if (!label) return;
      if (label.textContent.trim() === 'Carreras') label.textContent = 'Carreras en Complexivo';
      if (label.textContent.trim() === 'Estudiantes procesados') label.textContent = 'Registros en Complexivo';
    });
    document.querySelectorAll('#reports-grid .report-card .card-meta').forEach(meta => {
      const spans = [...meta.querySelectorAll('span')];
      if (spans[0] && !spans[0].textContent.includes('Complexivo')) spans[0].textContent = `${spans[0].textContent} en Complexivo`;
      if (spans[1] && !spans[1].textContent.includes('Complexivo')) spans[1].textContent = `${spans[1].textContent.replace(' estudiantes', ' registros')} en Complexivo`;
    });
  }

  function removeCrossModulePanels() {
    document.querySelectorAll('[data-eligibility-panel], [data-complexive-eligibility-warning]').forEach(node => node.remove());
  }

  function scan() {
    cleanRoster();
    cleanImportWarning();
    clarifyDashboardCounts();
    removeCrossModulePanels();
  }

  const style = document.createElement('style');
  style.textContent = `
    #tab-roster .roster-metrics { grid-template-columns: repeat(4, minmax(150px, 1fr)); }
  `;
  document.head.appendChild(style);

  new MutationObserver(records => {
    if (records.some(record => record.addedNodes.length)) scan();
  }).observe(document.body, { childList: true, subtree: true });

  document.addEventListener('click', event => {
    if (event.target.closest('[data-tab="roster"], #report-import-roster, #roster-upload-btn, #roster-empty-upload, [data-view="dashboard"]')) {
      setTimeout(scan, 0);
    }
  });

  scan();
})();
