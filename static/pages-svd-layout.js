(() => {
  'use strict';

  if (!/(^|\.)github\.io$/i.test(window.location.hostname)) return;

  const ACTIVE_PERIOD_KEY = 'informtit.activePeriod.v2';
  const clean = value => String(value ?? '').replace(/\u00a0/g, ' ').trim().replace(/\s+/g, ' ');
  const fold = value => clean(value).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toUpperCase();
  const canonicalPeriodId = value => {
    const raw = clean(value);
    const match = /^(\d{4})-(\d{2})_+(\d{4})-(\d{2})$/.exec(raw);
    return match ? `${match[1]}-${match[2]}_${match[3]}-${match[4]}` : raw;
  };

  function activePeriod() {
    if (window.state?.activePeriod) return window.state.activePeriod;
    try { return JSON.parse(localStorage.getItem(ACTIVE_PERIOD_KEY) || 'null'); }
    catch (_) { return null; }
  }

  function periodKey(value) {
    return canonicalPeriodId(value?.id || value?.periodoId || value?.sourceId || value?.firebase_period_id || value?.period_id || '');
  }

  function reportPeriodKey(report) {
    return canonicalPeriodId(report?.periodoId || report?.firebase_period_id || report?.period_id || '');
  }

  function reportType(report) {
    return clean(report?.report_type || report?.tipo || report?.type).toLowerCase() === 'pvc' ? 'pvc' : 'normal';
  }

  function reportsForActivePeriod() {
    const period = activePeriod();
    const key = periodKey(period);
    const label = fold(period?.name || period?.label || '');
    const rows = Array.isArray(window.state?.reports) ? window.state.reports : [];
    if (!period) return [];
    return rows.filter(report => {
      const reportKey = reportPeriodKey(report);
      if (key && reportKey && key === reportKey) return true;
      return label && fold(report?.period || report?.periodo || '') === label;
    });
  }

  function isFinal(report) {
    return ['FINALIZADO', 'COMPLETO', 'LISTO', 'APROBADO', 'CERRADO'].includes(fold(report?.status || report?.estado));
  }

  function ensureSvdChrome() {
    document.querySelector('.sidebar')?.setAttribute('hidden', '');
    document.body.classList.add('svd-layout-active');

    const main = document.querySelector('.main');
    const topbar = document.querySelector('.topbar');
    if (!main || !topbar) return null;

    let strip = document.getElementById('svd-document-strip');
    if (!strip) {
      strip = document.createElement('section');
      strip.id = 'svd-document-strip';
      strip.className = 'svd-document-strip';
      topbar.insertAdjacentElement('afterend', strip);
    }

    const period = document.getElementById('global-period-context');
    if (period && period.parentElement !== topbar) topbar.appendChild(period);

    const refresh = document.getElementById('refresh-btn');
    const actions = document.querySelector('.top-actions');
    if (actions) {
      actions.querySelector('#new-report-btn')?.setAttribute('hidden', '');
      actions.querySelector('#new-pvc-report-btn')?.setAttribute('hidden', '');
      if (refresh) refresh.textContent = 'Actualizar';
    }

    const title = document.getElementById('page-title');
    const subtitle = document.getElementById('page-subtitle');
    if (title) title.textContent = 'INFORMTIT';
    if (subtitle) subtitle.textContent = 'Gestión documental';

    document.getElementById('view-dashboard')?.setAttribute('aria-hidden', 'true');
    return strip;
  }

  function cardMarkup(title, subtitle, report, type) {
    const activeId = Number(window.state?.activeReport?.id || 0);
    const selected = Boolean(report && Number(report.id) === activeId);
    const final = Boolean(report && isFinal(report));
    const stateLabel = selected ? 'Seleccionado' : final ? 'Finalizado' : report ? 'Disponible' : 'Pendiente';
    const classes = ['svd-document-card', selected ? 'is-selected' : '', final ? 'is-final' : '', report ? 'is-available' : 'is-pending'].filter(Boolean).join(' ');
    const action = report
      ? `data-svd-open-report="${Number(report.id)}"`
      : `data-svd-create-report="${type}"`;
    return `<button type="button" class="${classes}" ${action}>
      <span class="svd-document-title">${window.escapeHtml ? window.escapeHtml(title) : title}</span>
      <span class="svd-document-state">${final ? '<i class="svd-complete-dot" aria-hidden="true"></i>' : ''}${stateLabel}</span>
      <small>${window.escapeHtml ? window.escapeHtml(subtitle) : subtitle}</small>
    </button>`;
  }

  function renderDocumentStrip() {
    const strip = ensureSvdChrome();
    if (!strip) return;
    const period = activePeriod();
    if (!period) {
      strip.innerHTML = '<div class="svd-document-empty"><strong>Documentos</strong><span>Seleccione o cree un período para comenzar.</span></div>';
      return;
    }

    const reports = reportsForActivePeriod();
    const regular = reports.find(report => reportType(report) === 'normal');
    const pvc = reports.find(report => reportType(report) === 'pvc');
    strip.innerHTML = `
      <div class="svd-document-strip-head"><span>Documentos</span></div>
      <div class="svd-document-track">
        ${cardMarkup('Informe Final de Titulación', 'Presencial + Online', regular, 'normal')}
        ${cardMarkup('PVC · Artículo Académico', 'Artículo científico', pvc, 'pvc')}
      </div>`;

    strip.querySelectorAll('[data-svd-open-report]').forEach(button => {
      button.addEventListener('click', () => window.openReport?.(Number(button.dataset.svdOpenReport)));
    });
    strip.querySelectorAll('[data-svd-create-report]').forEach(button => {
      button.addEventListener('click', () => window.openReportDialog?.(button.dataset.svdCreateReport));
    });
  }

  function reorderTabs() {
    const tabs = document.getElementById('report-tabs');
    if (!tabs) return;
    const order = ['general', 'cover', 'header', 'roster', 'students', 'schedules', 'nuclei', 'careers', 'projects', 'images', 'sections'];
    const labels = {
      general: 'Información', cover: 'Portada', header: 'Cabecera', roster: 'Requisitos', students: 'Estudiantes',
      schedules: 'Cronogramas', nuclei: 'Núcleos', careers: 'Examen Complexivo', projects: 'Trabajo de Titulación',
      images: 'Recursos', sections: 'Estructura',
    };
    order.forEach(key => {
      const button = tabs.querySelector(`[data-tab="${key}"]`);
      if (!button) return;
      button.textContent = labels[key] || button.textContent;
      tabs.appendChild(button);
    });
    const workspace = document.getElementById('report-workspace');
    if (workspace) {
      order.forEach(key => {
        const content = document.getElementById(`tab-${key}`);
        if (content) workspace.appendChild(content);
      });
    }
  }

  function compactReportHeader() {
    const banner = document.querySelector('.report-banner');
    if (!banner) return;
    const modality = document.getElementById('report-modality');
    if (modality) modality.textContent = clean(modality.textContent).replace(/Informe\s+/i, '');
  }

  async function openFirstDocumentIfNeeded() {
    ensureSvdChrome();
    renderDocumentStrip();
    reorderTabs();
    compactReportHeader();

    const reports = reportsForActivePeriod();
    const current = window.state?.activeReport;
    const currentStillValid = current && reports.some(report => Number(report.id) === Number(current.id));
    if (currentStillValid) {
      window.showView?.('report');
      return;
    }

    const first = reports.find(report => reportType(report) === 'normal') || reports[0];
    if (first && typeof window.openReport === 'function') {
      await window.openReport(Number(first.id));
      renderDocumentStrip();
      reorderTabs();
      compactReportHeader();
      return;
    }

    window.state && (window.state.activeReport = null);
    document.getElementById('report-workspace')?.setAttribute('hidden', '');
    const empty = document.getElementById('empty-report');
    if (empty) {
      empty.hidden = false;
      const h2 = empty.querySelector('h2');
      const p = empty.querySelector('p');
      if (h2) h2.textContent = 'Cree el primer documento del período';
      if (p) p.textContent = 'Seleccione uno de los documentos de la franja superior.';
    }
    window.showView?.('report');
  }

  function installWrappers() {
    if (window.__informtitSvdWrapped) return;
    window.__informtitSvdWrapped = true;

    const baseShowView = window.showView;
    if (typeof baseShowView === 'function') {
      window.showView = function svdShowView(name, ...args) {
        const target = name === 'dashboard' ? 'report' : name;
        const result = baseShowView.call(this, target, ...args);
        ensureSvdChrome();
        renderDocumentStrip();
        reorderTabs();
        compactReportHeader();
        return result;
      };
    }

    const baseLoadReports = window.loadReports;
    if (typeof baseLoadReports === 'function') {
      window.loadReports = async function svdLoadReports(...args) {
        const result = await baseLoadReports.apply(this, args);
        await openFirstDocumentIfNeeded();
        return result;
      };
    }

    const baseOpenReport = window.openReport;
    if (typeof baseOpenReport === 'function') {
      window.openReport = async function svdOpenReport(...args) {
        const result = await baseOpenReport.apply(this, args);
        window.showView?.('report');
        renderDocumentStrip();
        reorderTabs();
        compactReportHeader();
        return result;
      };
    }

    const baseRenderReport = window.renderReport;
    if (typeof baseRenderReport === 'function') {
      window.renderReport = function svdRenderReport(...args) {
        const result = baseRenderReport.apply(this, args);
        renderDocumentStrip();
        reorderTabs();
        compactReportHeader();
        return result;
      };
    }
  }

  function injectStyles() {
    if (document.getElementById('svd-layout-style')) return;
    const style = document.createElement('style');
    style.id = 'svd-layout-style';
    style.textContent = `
      body.svd-layout-active{background:#f6f7f9;color:#1c2b3a}
      body.svd-layout-active .sidebar{display:none!important}
      body.svd-layout-active .main{margin-left:0!important;max-width:1240px;margin-right:auto;margin-left:auto!important;padding:18px 24px 42px}
      body.svd-layout-active .topbar{display:grid;grid-template-columns:minmax(180px,1fr) auto auto;gap:14px;align-items:center;margin:0 0 12px;padding:13px 16px;border:1px solid #dfe5eb;border-radius:12px;background:#fff}
      body.svd-layout-active .topbar>div:first-child{min-width:0}
      body.svd-layout-active .topbar h1{font-size:13px;line-height:1.1;letter-spacing:.04em;margin:0 0 2px;color:#31465a}
      body.svd-layout-active .topbar p{font-size:15px;font-weight:750;color:#173b5c;margin:0}
      body.svd-layout-active .top-actions{margin:0;gap:6px}
      body.svd-layout-active .top-actions #new-report-btn,body.svd-layout-active .top-actions #new-pvc-report-btn{display:none!important}
      body.svd-layout-active .top-actions #refresh-btn{padding:7px 10px;font-size:12px;background:#fff}
      body.svd-layout-active .global-period-context{order:2;margin:0!important;padding:0!important;border:0!important;background:transparent!important;display:flex;align-items:end;gap:6px;flex-wrap:nowrap}
      body.svd-layout-active .global-period-context label{min-width:255px!important;gap:3px!important}
      body.svd-layout-active .global-period-context label span{font-size:9px!important;color:#687789!important}
      body.svd-layout-active .global-period-context select{height:34px!important;border-radius:8px!important;padding:6px 9px!important;font-size:12px!important}
      body.svd-layout-active .global-period-context .button{height:34px;padding:6px 9px;font-size:11px;white-space:nowrap}
      .svd-document-strip{margin:0 0 10px;padding:10px 12px;border:1px solid #dfe5eb;border-radius:12px;background:#fff}
      .svd-document-strip-head{margin-bottom:7px}.svd-document-strip-head span{font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:.04em;color:#647386}
      .svd-document-track{display:flex;gap:8px;overflow-x:auto;padding-bottom:2px;scrollbar-width:thin}
      .svd-document-card{position:relative;flex:0 0 230px;display:grid;grid-template-columns:1fr auto;gap:2px 8px;text-align:left;border:1px solid #dfe5eb;border-radius:9px;background:#fff;padding:10px 11px;color:#203246;cursor:pointer;box-shadow:none}
      .svd-document-card:hover{border-color:#b8c8d8;background:#fbfcfd}.svd-document-card.is-selected{background:#fafbfd;border-color:#c9d4df}.svd-document-card.is-selected:after{content:'';position:absolute;left:10px;right:10px;bottom:-1px;height:3px;border-radius:3px 3px 0 0;background:#d5ad2f}
      .svd-document-title{font-size:12px;font-weight:780;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.svd-document-state{font-size:10px;color:#69788a;display:inline-flex;align-items:center;gap:5px}.svd-document-card small{grid-column:1/-1;font-size:10px;color:#7b8795}.svd-complete-dot{width:7px;height:7px;border-radius:50%;background:#27835a;display:inline-block}
      .svd-document-empty{display:flex;align-items:center;gap:8px;font-size:12px}.svd-document-empty span{color:#69788a}
      body.svd-layout-active #view-dashboard{display:none!important}
      body.svd-layout-active .report-banner{background:#fff!important;color:#203246!important;border:1px solid #dfe5eb!important;border-radius:10px!important;padding:10px 12px!important;margin-bottom:8px!important;box-shadow:none!important}
      body.svd-layout-active .report-banner h2{font-size:17px!important;margin:3px 0 1px!important;line-height:1.2}.report-banner p{font-size:11px!important;color:#718093!important}.report-banner .eyebrow{padding:2px 6px!important;background:#edf3f7!important;color:#436078!important;font-size:9px!important}
      body.svd-layout-active .report-actions{gap:6px}.report-actions .button{padding:7px 10px;font-size:11px}
      body.svd-layout-active .tabs{margin:0 0 10px!important;padding:0 3px!important;gap:4px!important;background:#f0f2f5!important;border-radius:0!important;border-bottom:1px solid #dfe5eb!important;overflow-x:auto}
      body.svd-layout-active .tab{position:relative;padding:9px 10px!important;border-radius:0!important;font-size:11px!important;font-weight:700!important;color:#687789!important;background:transparent!important;box-shadow:none!important}
      body.svd-layout-active .tab.active{color:#173b5c!important;background:transparent!important}.tab.active:after{content:'';position:absolute;left:7px;right:7px;bottom:0;height:2px;background:#1f5f95;border-radius:2px}
      body.svd-layout-active .panel,body.svd-layout-active .form-panel{box-shadow:none!important;border-color:#dfe5eb!important;border-radius:10px!important;padding:14px!important}
      body.svd-layout-active .panel-head{margin-bottom:10px!important}.panel-head h2{font-size:15px!important;margin:0 0 2px!important}.panel-head p{font-size:11px!important;line-height:1.35!important}
      body.svd-layout-active .empty-state{padding:34px 14px!important}.empty-state h2{font-size:16px!important;margin-bottom:5px}.empty-state p{font-size:12px!important}
      body.svd-layout-active .metric{padding:12px!important;box-shadow:none!important}.metric strong{font-size:20px!important}
      @media(max-width:820px){
        body.svd-layout-active .main{padding:12px}
        body.svd-layout-active .topbar{grid-template-columns:1fr auto;align-items:start}
        body.svd-layout-active .global-period-context{grid-column:1/-1;order:3;width:100%;overflow-x:auto;padding-top:6px!important}
        body.svd-layout-active .global-period-context label{min-width:240px!important}
        .svd-document-card{flex-basis:205px}
      }
      @media(max-width:520px){
        body.svd-layout-active .topbar{padding:10px}.svd-document-strip{padding:8px}.svd-document-card{flex-basis:190px}
        body.svd-layout-active .top-actions #refresh-btn{font-size:0;width:34px;height:34px;padding:0}body.svd-layout-active .top-actions #refresh-btn:after{content:'↻';font-size:18px}
      }
    `;
    document.head.appendChild(style);
  }

  injectStyles();
  ensureSvdChrome();
  installWrappers();
  renderDocumentStrip();
  reorderTabs();
  compactReportHeader();

  document.addEventListener('informtit:period-changed', () => setTimeout(() => void openFirstDocumentIfNeeded(), 0));
  document.addEventListener('DOMContentLoaded', () => setTimeout(() => void openFirstDocumentIfNeeded(), 0), { once: true });
  setTimeout(() => void openFirstDocumentIfNeeded(), 60);
})();
