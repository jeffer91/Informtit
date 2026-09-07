(() => {
  'use strict';

  if (window.__informtitGitPagesParityInstalled) return;
  window.__informtitGitPagesParityInstalled = true;

  const currentScript = document.currentScript;
  const assetBase = currentScript?.src
    ? new URL('.', currentScript.src)
    : new URL('./', window.location.href);

  let scheduledFrame = 0;

  function clean(value) {
    return String(value ?? '').trim().replace(/\s+/g, ' ');
  }

  function fold(value) {
    return clean(value)
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .toUpperCase();
  }

  function activeReport() {
    try {
      return typeof state !== 'undefined' ? state.activeReport : null;
    } catch (_) {
      return null;
    }
  }

  function isPvc(report) {
    return clean(report?.report_type).toLowerCase() === 'pvc';
  }

  function isGlobalPeriod(report) {
    if (!report || isPvc(report)) return false;
    const project = report.project_summary || {};
    return clean(report.modality) === 'unified'
      || Boolean(report.unified_period)
      || Boolean(report.period_project_id)
      || Boolean(project.period_project_id);
  }

  function periodLabel(report) {
    return clean(report?.project_summary?.period || report?.period);
  }

  function reportTitle(report) {
    const period = periodLabel(report);
    const projectName = clean(report?.project_summary?.name);
    const reportName = clean(report?.name);
    let name = projectName || reportName || 'Informe Final del Proceso de Titulación';
    if (period && !fold(name).includes(fold(period))) {
      name = `${name.replace(/\s*[-–—]\s*$/, '')} - ${period}`;
    }
    return name;
  }

  function validationLabel(report) {
    const raw = fold(
      report?.validation_status
      || report?.audit_state
      || report?.project_summary?.state
      || report?.status
      || ''
    );
    if (/APTO PARA EMITIR|VALIDADO|VALIDADA|APROBADO|APROBADA/.test(raw)) {
      return 'VALIDADO';
    }
    return 'VALIDACION PENDIENTE';
  }

  function removeConsoleButtons() {
    document.querySelectorAll('.top-actions button').forEach(button => {
      if (clean(button.textContent).toLowerCase() === 'consola') button.remove();
    });
  }

  function showSharedTabs() {
    const tabs = document.getElementById('report-tabs');
    if (tabs && tabs.style.display) tabs.style.removeProperty('display');

    document.querySelectorAll('#report-workspace .tab-content').forEach(content => {
      if (content.style.display) content.style.removeProperty('display');
    });
  }

  function ensureValidationBadge(report) {
    const bannerInfo = document.querySelector('.report-banner > div:first-child');
    if (!bannerInfo) return;

    let badge = document.getElementById('gitpages-validation-badge');
    if (!badge) {
      badge = document.createElement('span');
      badge.id = 'gitpages-validation-badge';
      badge.className = 'gitpages-validation-badge';
      bannerInfo.appendChild(badge);
    }
    const next = validationLabel(report);
    if (badge.textContent !== next) badge.textContent = next;
  }

  function removeValidationBadge() {
    document.getElementById('gitpages-validation-badge')?.remove();
  }

  function normalizeGlobalReport() {
    removeConsoleButtons();

    const report = activeReport();
    if (!isGlobalPeriod(report)) {
      removeValidationBadge();
      return;
    }

    document.getElementById('period-project-controls')?.remove();
    document.getElementById('period-project-alerts')?.remove();
    document.getElementById('period-all-view')?.remove();

    const workspace = document.getElementById('report-workspace');
    if (workspace?.dataset?.unifiedNormal) delete workspace.dataset.unifiedNormal;

    showSharedTabs();

    const modality = document.getElementById('report-modality');
    if (modality && modality.textContent !== 'Período académico global') {
      modality.textContent = 'Período académico global';
    }

    const period = periodLabel(report);
    const periodNode = document.getElementById('report-period');
    if (periodNode && periodNode.textContent !== period) periodNode.textContent = period;

    const title = reportTitle(report);
    const titleNode = document.getElementById('report-name');
    if (titleNode && titleNode.textContent !== title) titleNode.textContent = title;

    const generalForm = document.getElementById('general-form');
    const modalitySelect = generalForm?.elements?.modality;
    const modalityField = modalitySelect?.closest('label');
    if (modalityField && !modalityField.hidden) modalityField.hidden = true;

    ensureValidationBadge(report);
  }

  function scheduleNormalize() {
    if (scheduledFrame) return;
    scheduledFrame = window.requestAnimationFrame(() => {
      scheduledFrame = 0;
      normalizeGlobalReport();
    });
  }

  function scriptAlreadyLoaded(filename) {
    return [...document.scripts].some(script => clean(script.src).includes(filename));
  }

  function loadSharedScript(filename) {
    if (scriptAlreadyLoaded(filename)) return Promise.resolve(false);
    return new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = new URL(filename, assetBase).toString();
      script.async = false;
      script.dataset.informtitParity = '1';
      script.onload = () => resolve(true);
      script.onerror = () => reject(new Error(`No se pudo cargar ${filename}.`));
      document.body.appendChild(script);
    });
  }

  function ensureStyles() {
    if (document.getElementById('gitpages-parity-styles')) return;
    const style = document.createElement('style');
    style.id = 'gitpages-parity-styles';
    style.textContent = `
      .gitpages-validation-badge {
        display:inline-flex;
        align-items:center;
        width:max-content;
        margin-top:8px;
        padding:5px 10px;
        border-radius:999px;
        background:#fff;
        color:#475569;
        box-shadow:0 0 0 1px rgba(255,255,255,.55);
        font-size:11px;
        font-weight:800;
        line-height:1;
      }
      #report-workspace #period-project-controls,
      #report-workspace + #period-project-alerts {
        display:none !important;
      }
    `;
    document.head.appendChild(style);
  }

  async function installHealthDashboard() {
    try {
      const loaded = await loadSharedScript('report-health-ui.js?v=1.0');
      if (loaded) {
        const report = activeReport();
        if (report && typeof renderReport === 'function') {
          renderReport();
        }
      }
    } catch (error) {
      console.warn('[Informtit paridad] No se pudo activar el Resumen compartido.', error);
    } finally {
      scheduleNormalize();
    }
  }

  ensureStyles();
  removeConsoleButtons();
  scheduleNormalize();

  const observer = new MutationObserver(() => scheduleNormalize());
  observer.observe(document.documentElement, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ['style'],
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      scheduleNormalize();
      void installHealthDashboard();
    }, { once: true });
  } else {
    void installHealthDashboard();
  }
})();
