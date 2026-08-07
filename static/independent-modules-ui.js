(() => {
  let scanQueued = false;
  let scanning = false;

  function setText(node, value) {
    if (node && node.textContent !== value) node.textContent = value;
  }

  function cleanRoster() {
    const tab = document.querySelector('#tab-roster');
    if (!tab) return;

    setText(tab.querySelector('.roster-head h2'), 'Requisitos');
    setText(
      tab.querySelector('.roster-head p'),
      'Módulo independiente. La información cargada aquí no modifica Núcleos, Examen Complexivo ni Trabajo de Titulación.',
    );

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
      if (!button) return;
      setText(
        button,
        button.id === 'report-import-roster' ? 'Subir requisitos .xls' : 'Cargar requisitos .xls',
      );
    });
  }

  function cleanImportWarning() {
    const warning = document.querySelector('#active-report-import-dialog .replace-warning');
    if (!warning) return;
    setText(
      warning.querySelector('strong'),
      'La importación reemplazará únicamente los datos del módulo Requisitos.',
    );
    setText(
      warning.querySelector('span'),
      'Núcleos, Examen Complexivo y Trabajo de Titulación no se modificarán.',
    );
  }

  function clarifyDashboardCounts() {
    document.querySelectorAll('#dashboard-metrics .metric').forEach(metric => {
      const label = metric.querySelector('span');
      if (!label) return;
      if (label.textContent.trim() === 'Carreras') setText(label, 'Carreras en Complexivo');
      if (label.textContent.trim() === 'Estudiantes procesados') setText(label, 'Registros en Complexivo');
    });

    document.querySelectorAll('#reports-grid .report-card .card-meta').forEach(meta => {
      const spans = [...meta.querySelectorAll('span')];
      if (spans[0] && !spans[0].textContent.includes('Complexivo')) {
        setText(spans[0], `${spans[0].textContent} en Complexivo`);
      }
      if (spans[1] && !spans[1].textContent.includes('Complexivo')) {
        setText(spans[1], `${spans[1].textContent.replace(' estudiantes', ' registros')} en Complexivo`);
      }
    });
  }

  function removeCrossModulePanels() {
    document
      .querySelectorAll('[data-eligibility-panel], [data-complexive-eligibility-warning]')
      .forEach(node => node.remove());
  }

  function scan() {
    if (scanning) return;
    scanning = true;
    try {
      cleanRoster();
      cleanImportWarning();
      clarifyDashboardCounts();
      removeCrossModulePanels();
    } finally {
      scanning = false;
    }
  }

  function scheduleScan() {
    if (scanQueued) return;
    scanQueued = true;
    requestAnimationFrame(() => {
      scanQueued = false;
      scan();
    });
  }

  const style = document.createElement('style');
  style.textContent = `
    #tab-roster .roster-metrics { grid-template-columns: repeat(4, minmax(150px, 1fr)); }
  `;
  document.head.appendChild(style);

  new MutationObserver(records => {
    if (records.some(record => record.addedNodes.length || record.removedNodes.length)) {
      scheduleScan();
    }
  }).observe(document.body, { childList: true, subtree: true });

  document.addEventListener('click', event => {
    if (event.target.closest('[data-tab="roster"], #report-import-roster, #roster-upload-btn, #roster-empty-upload, [data-view="dashboard"]')) {
      scheduleScan();
    }
  });

  scheduleScan();
})();
