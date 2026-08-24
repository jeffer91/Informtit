// Selector de modalidad, estado documental y ajustes visibles de importación.
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

  function ensureAuditBadge() {
    const banner = document.querySelector('.report-banner');
    if (!banner) return null;
    let badge = document.getElementById('report-audit-state-badge');
    if (!badge) {
      badge = document.createElement('span');
      badge.id = 'report-audit-state-badge';
      badge.style.display = 'inline-flex';
      badge.style.alignItems = 'center';
      badge.style.width = 'fit-content';
      badge.style.padding = '5px 9px';
      badge.style.marginTop = '7px';
      badge.style.borderRadius = '999px';
      badge.style.fontSize = '11px';
      badge.style.fontWeight = '800';
      badge.style.letterSpacing = '.03em';
      const info = banner.firstElementChild;
      if (info) info.appendChild(badge);
    }
    return badge;
  }

  function paintAuditBadge(badge, audit) {
    if (!badge) return;
    badge.textContent = audit.state || 'BORRADOR';
    if (audit.state === 'APTO PARA EMITIR' || audit.state === 'SIN POBLACIÓN') {
      badge.style.background = '#dff2e7';
      badge.style.color = '#245f43';
    } else if (audit.state === 'ERROR DE CARGA') {
      badge.style.background = '#f7dddd';
      badge.style.color = '#8f3131';
    } else {
      badge.style.background = '#fff0ca';
      badge.style.color = '#745415';
    }
  }

  async function refreshAuditState() {
    const reportId = Number(state?.activeReport?.id || 0);
    if (!reportId) return;
    try {
      const data = await api(`/api/reports/${reportId}/audit`);
      if (Number(state?.activeReport?.id || 0) !== reportId) return;
      const audit = data.audit || {};
      setTextIfChanged(document.getElementById('report-name'), audit.document_title || state.activeReport.name || 'Informe de Titulación');
      paintAuditBadge(ensureAuditBadge(), audit);
    } catch (error) {
      const badge = ensureAuditBadge();
      if (badge) {
        badge.textContent = 'VALIDACIÓN PENDIENTE';
        badge.style.background = '#eef2f5';
        badge.style.color = '#526779';
        badge.title = error.message || 'No se pudo consultar la auditoría.';
      }
    }
  }

  if (typeof renderReport === 'function') {
    const previousRenderReport = renderReport;
    renderReport = function () {
      previousRenderReport();
      renderModalitySwitcher();
      void refreshAuditState();
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

  // El diálogo se crea bajo demanda. Cuando aparezca, se observan solo sus cambios.
  const bodyObserver = new MutationObserver(() => {
    const dialog = document.getElementById('active-report-import-dialog');
    if (!dialog || dialog.dataset.integrityObserved === '1') return;
    dialog.dataset.integrityObserved = '1';
    const observer = new MutationObserver(() => updateImportDialogText());
    observer.observe(dialog, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['hidden', 'disabled'],
    });
    updateImportDialogText();
  });
  bodyObserver.observe(document.body, { childList: true, subtree: true });

  updateImportDialogText();
  renderModalitySwitcher();
  void refreshAuditState();
})();