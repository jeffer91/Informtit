// Estado documental y validacion visible sin observadores globales.
(function () {
  'use strict';

  let lastImportPreview = null;

  function setTextIfChanged(node, text) {
    if (node && node.textContent !== text) node.textContent = text;
  }

  function setHtmlIfChanged(node, html) {
    if (node && node.innerHTML !== html) node.innerHTML = html;
  }

  function isUnifiedPeriod() {
    const project = state?.activeReport?.project_summary;
    return !!project && String(project.report_type || '').toLowerCase() !== 'pvc';
  }

  // Conserva la previsualizacion para periodos heredados. En los periodos
  // unificados robust-import-ui.js es la unica capa que pinta la importacion.
  if (typeof api === 'function' && !window.__informtitValidationApiWrapped) {
    const previousApi = api;
    api = async function (path, options = {}) {
      const result = await previousApi(path, options);
      if (path === '/api/imports/preview' && result?.preview) {
        lastImportPreview = result.preview;
        queueMicrotask(updateImportDialogText);
      }
      return result;
    };
    window.__informtitValidationApiWrapped = true;
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
      banner.firstElementChild?.appendChild(badge);
    }
    return badge;
  }

  function paintAuditBadge(badge, audit) {
    if (!badge) return;
    badge.textContent = audit.state || 'BORRADOR';
    if (audit.state === 'APTO PARA EMITIR') {
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
    if (!reportId || typeof api !== 'function') return;
    try {
      const data = await api(`/api/reports/${reportId}/audit`);
      if (Number(state?.activeReport?.id || 0) !== reportId) return;
      const audit = data.audit || {};
      setTextIfChanged(
        document.getElementById('report-name'),
        audit.document_title || state.activeReport.name || 'Informe de Titulacion'
      );
      paintAuditBadge(ensureAuditBadge(), audit);
    } catch (error) {
      const badge = ensureAuditBadge();
      if (badge) {
        badge.textContent = 'VALIDACION PENDIENTE';
        badge.style.background = '#eef2f5';
        badge.style.color = '#526779';
        badge.title = error?.message || 'No se pudo consultar la auditoria.';
      }
    }
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

  function updateLegacyPreview() {
    if (isUnifiedPeriod() || !lastImportPreview) return;
    if (document.getElementById('active-import-confirm-step')?.hidden) return;

    const metrics = document.getElementById('active-import-metrics');
    if (metrics) {
      const presencialCareers = lastImportPreview.careers?.presencial || [];
      const onlineCareers = lastImportPreview.careers?.en_linea || [];
      setHtmlIfChanged(metrics, [
        metricCard('Registros del archivo', lastImportPreview.total),
        metricCard('Presencial', lastImportPreview.presencial),
        metricCard('Online', lastImportPreview.en_linea),
        metricCard('Carreras detectadas', presencialCareers.length + onlineCareers.length),
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

  function updateImportDialogText() {
    const importDialog = document.getElementById('active-report-import-dialog');
    if (!importDialog) return;

    setTextIfChanged(importDialog.querySelector('.dialog-head h2'), 'Cargar base de requisitos');

    // robust-import-ui.js es la fuente unica de texto para periodos normales.
    if (isUnifiedPeriod()) return;

    setTextIfChanged(
      importDialog.querySelector('.dialog-head p'),
      'Importe la base de Requisitos y revise la clasificacion antes de guardar.'
    );

    const warning = importDialog.querySelector('.replace-warning');
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
    updateLegacyPreview();
  }

  function installDialogObserver() {
    const importDialog = document.getElementById('active-report-import-dialog');
    if (!importDialog || importDialog.dataset.validationObserved === '1') return;
    importDialog.dataset.validationObserved = '1';
    const observer = new MutationObserver(updateImportDialogText);
    observer.observe(importDialog, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['hidden', 'disabled'],
    });
    updateImportDialogText();
  }

  // El dialogo ya es creado por forms-hotfix.js. Este listener solo cubre el
  // caso de una reconstruccion futura sin vigilar document.body permanentemente.
  document.addEventListener('click', event => {
    if (!event.target?.closest?.('#report-import-roster, #roster-upload-btn, #roster-empty-upload')) return;
    queueMicrotask(installDialogObserver);
  }, true);

  if (typeof renderReport === 'function') {
    const previousRenderReport = renderReport;
    renderReport = function () {
      previousRenderReport();
      installDialogObserver();
      void refreshAuditState();
    };
  }

  installDialogObserver();
  void refreshAuditState();
})();
