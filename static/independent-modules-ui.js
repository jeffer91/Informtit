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

  function removeCrossModulePanels() {
    document.querySelectorAll('[data-eligibility-panel], [data-complexive-eligibility-warning]').forEach(node => node.remove());
  }

  function scan() {
    cleanRoster();
    cleanImportWarning();
    removeCrossModulePanels();
  }

  const style = document.createElement('style');
  style.textContent = `
    #tab-roster .roster-metrics { grid-template-columns: repeat(4, minmax(150px, 1fr)); }
    #tab-roster .roster-table th:last-child,
    #tab-roster .roster-table td:last-child { }
  `;
  document.head.appendChild(style);

  new MutationObserver(records => {
    if (records.some(record => record.addedNodes.length)) scan();
  }).observe(document.body, { childList: true, subtree: true });

  document.addEventListener('click', event => {
    if (event.target.closest('[data-tab="roster"], #report-import-roster, #roster-upload-btn, #roster-empty-upload')) {
      setTimeout(scan, 0);
    }
  });

  scan();
})();
