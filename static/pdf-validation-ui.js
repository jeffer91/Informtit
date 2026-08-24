// Selector de modalidad, estado documental y ajustes visibles de importación.
(function () {
  const normalize = value => String(value || '').trim().toLocaleLowerCase('es');
  let lastImportPreview = null;

  function setTextIfChanged(node, text) {
    if (node && node.textContent !== text) node.textContent = text;
  }

  function setHtmlIfChanged(node, html) {
    if (node && node.innerHTML !== html) node.innerHTML = html;
  }

  // Conserva la previsualización completa para que el diálogo muestre las dos
  // modalidades y no solamente la del informe que estaba abierto al cargar.
  if (typeof api === 'function' && !window.__informtitDualImportApiWrapped) {
    const previousApi = api;
    api = async function (path, options = {}) {
      const result = await previousApi(path, options);
      if (path === '/api/imports/preview' && result?.preview) {
        lastImportPreview = result.preview;
        queueMicrotask(() => updateImportDialogText());
      }
      return result;
    };
    window.__informtitDualImportApiWrapped = true;
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
      queueMicrotask(() => updateRosterText());
    };
  }

  function metricCard(label, value) {
    return `<article class="metric roster-metric"><span>${escapeHtml(label)}</span><strong>${Number(value || 0)}</strong></article>`;
  }

  function careerGroup(title, careers) {
    const rows = Array.isArray(careers) ? careers : [];
    if (!rows.length) {
      return `<section><strong>${title}</strong><div class="empty-mini">Sin carreras detectadas.</div></section>`;
    }
    return `<section><strong>${title}</strong>${rows.map(item => `<div><span>${escapeHtml(item.name || '')}</span><strong>${Number(item.students || 0)}</strong></div>`).join('')}</section>`;
  }

  function updateImportPreview() {
    if (!lastImportPreview || document.getElementById('active-import-confirm-step')?.hidden) return;
    const metrics = document.getElementById('active-import-metrics');
    if (metrics) {
      const presencialCareers = lastImportPreview.careers?.presencial || [];
      const onlineCareers = lastImportPreview.careers?.en_linea || [];
      setHtmlIfChanged(metrics, [
        metricCard('Registros del archivo', lastImportPreview.total),
        metricCard('Presencial', lastImportPreview.presencial),
        metricCard('Online', lastImportPreview.en_linea),
        metricCard('Carreras detectadas', presencialCareers.length + onlineCareers.length),
        metricCard('Sedes detectadas', Object.keys(lastImportPreview.campuses || {}).length),
      ].join(''));
    }

    const careers = document.getElementById('active-career-preview');
    if (careers) {
      setHtmlIfChanged(
        careers,
        careerGroup('Presencial', lastImportPreview.careers?.presencial)
        + careerGroup('Online', lastImportPreview.careers?.en_linea)
      );
    }
  }

  function updateRosterText() {
    const modality = state?.activeReport?.modality === 'en_linea' ? 'Online' : 'Presencial';
    const head = document.querySelector('#tab-roster .roster-head p');
    setHtmlIfChanged(
      head,
      `La carga fuente se procesa para <strong>Presencial y Online</strong>. Esta vista muestra únicamente los registros <strong>${modality}</strong> del informe activo.`
    );
    const empty = document.querySelector('#tab-roster .roster-empty-state p');
    setTextIfChanged(
      empty,
      `Informtit separará automáticamente Presencial y Online. Esta vista mostrará después únicamente la población ${modality} del informe activo.`
    );
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
        '<strong>Informtit actualizará ambos informes.</strong> Si una modalidad tiene 0 registros, quedará registrada como población 0 y se limpiará su base de Requisitos anterior.'
      );
    }

    const warning = dialog.querySelector('.replace-warning');
    if (warning) {
      setTextIfChanged(
        warning.querySelector('strong'),
        'La importación reemplazará únicamente la base de Requisitos de Presencial y Online.'
      );
      setTextIfChanged(
        warning.querySelector('span'),
        'Núcleos, Examen Complexivo y Trabajo de Titulación se conservan de forma independiente y se validan por modalidad.'
      );
    }

    const commit = document.getElementById('commit-active-roster');
    if (commit && !commit.disabled) {
      setTextIfChanged(commit, 'Importar Presencial y Online');
    }
    updateImportPreview();
    updateRosterText();
  }

  function installDialogObserver() {
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
  }

  const bodyObserver = new MutationObserver(() => {
    installDialogObserver();
    updateRosterText();
  });
  bodyObserver.observe(document.body, { childList: true, subtree: true });

  installDialogObserver();
  updateImportDialogText();
  updateRosterText();
  renderModalitySwitcher();
  void refreshAuditState();
})();