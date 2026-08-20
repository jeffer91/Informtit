// La validación previa del PDF se gestiona en pdf-progress.js.
// Este archivo añade el selector de modalidad y ajusta el flujo visible de
// importación para reflejar que una sola base genera Presencial y Online.
(function () {
  const normalize = value => String(value || '').trim().toLocaleLowerCase('es');

  function setTextIfChanged(node, text) {
    if (node && node.textContent !== text) node.textContent = text;
  }

  function setHtmlIfChanged(node, html) {
    if (node && node.innerHTML !== html) node.innerHTML = html;
  }

  function relatedReports(report) {
    if (!report) return [];
    const reports = Array.isArray(state?.reports) ? state.reports : [];
    let related = [];

    if (report.source_import_id) {
      related = reports.filter(item =>
        item.source_import_id && Number(item.source_import_id) === Number(report.source_import_id)
      );
    }

    if (related.length < 2) {
      related = reports.filter(item =>
        normalize(item.period) === normalize(report.period)
        && normalize(item.name) === normalize(report.name)
      );
    }

    const byModality = new Map();
    related.forEach(item => {
      if (item.modality === 'presencial' || item.modality === 'en_linea') {
        if (!byModality.has(item.modality) || Number(item.id) === Number(report.id)) {
          byModality.set(item.modality, item);
        }
      }
    });
    return ['presencial', 'en_linea'].map(key => byModality.get(key)).filter(Boolean);
  }

  function renderModalitySwitcher() {
    const report = state?.activeReport;
    const banner = document.querySelector('.report-banner');
    if (!banner || !report) return;

    document.getElementById('modality-report-switcher')?.remove();
    const related = relatedReports(report);
    if (related.length < 2) return;

    const switcher = document.createElement('div');
    switcher.id = 'modality-report-switcher';
    switcher.style.display = 'flex';
    switcher.style.gap = '8px';
    switcher.style.marginBottom = '10px';
    switcher.style.flexWrap = 'wrap';

    related.forEach(item => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = Number(item.id) === Number(report.id)
        ? 'button secondary small modality-switch-active'
        : 'button small modality-switch';
      button.textContent = item.modality === 'en_linea' ? 'Online' : 'Presencial';
      button.style.fontWeight = Number(item.id) === Number(report.id) ? '700' : '600';
      button.style.opacity = Number(item.id) === Number(report.id) ? '1' : '.86';
      button.onclick = async () => {
        if (Number(item.id) === Number(state.activeReport?.id)) return;
        await openReport(Number(item.id));
      };
      switcher.appendChild(button);
    });

    const info = banner.firstElementChild;
    if (info) info.insertBefore(switcher, info.firstChild);
  }

  if (typeof renderReport === 'function') {
    const previousRenderReport = renderReport;
    renderReport = function () {
      previousRenderReport();
      renderModalitySwitcher();
    };
  }

  function updateImportDialogText() {
    const dialog = document.getElementById('active-report-import-dialog');
    if (!dialog) return;

    const intro = dialog.querySelector('.dialog-head p');
    setTextIfChanged(
      intro,
      'Una sola carga separará automáticamente los registros Presencial y Online.'
    );

    const title = dialog.querySelector('.dialog-head h2');
    setTextIfChanged(title, 'Cargar base de requisitos');

    const note = document.getElementById('active-modality-note');
    if (note && !document.getElementById('active-import-confirm-step')?.hidden) {
      setHtmlIfChanged(
        note,
        '<strong>Informtit actualizará Presencial y Online por separado</strong> cuando ambas modalidades existan en el archivo.'
      );
    }

    const warning = dialog.querySelector('.replace-warning');
    if (warning) {
      setTextIfChanged(
        warning.querySelector('strong'),
        'La importación reemplazará únicamente la base de Requisitos de cada modalidad.'
      );
      setTextIfChanged(
        warning.querySelector('span'),
        'Núcleos, Examen Complexivo y Trabajo de Titulación se conservan de forma independiente.'
      );
    }

    const commit = document.getElementById('commit-active-roster');
    if (commit && !commit.disabled) {
      setTextIfChanged(commit, 'Importar Presencial y Online');
    }
  }

  // El diálogo ya fue creado por forms-hotfix.js. Observar únicamente ese nodo
  // evita procesar cada cambio de toda la aplicación y, sobre todo, evita el
  // bucle de mutaciones que bloqueaba completamente el renderer de Electron.
  const importDialog = document.getElementById('active-report-import-dialog');
  if (importDialog) {
    const observer = new MutationObserver(() => updateImportDialogText());
    observer.observe(importDialog, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['hidden', 'disabled'],
    });
  }

  updateImportDialogText();
  renderModalitySwitcher();
})();