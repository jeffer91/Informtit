// Un único proyecto por período con filtros Todos / Presencial / Online.
(function () {
  let currentView = 'todos';
  let overviewCache = null;
  let overviewProjectId = null;

  const css = document.createElement('style');
  css.textContent = `
    .period-card-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(310px,1fr));gap:16px}
    .period-card{border:1px solid #d7e0ea;border-radius:15px;padding:18px;background:#fff}
    .period-card .period-badge{display:inline-flex;padding:5px 9px;border-radius:999px;background:#e8f2fb;color:#17659d;font-size:11px;font-weight:800;margin-bottom:9px}
    .period-card h3{margin:0 0 5px}.period-card p{margin:3px 0;color:#61758b}
    .period-split{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:14px 0}
    .period-split.single{grid-template-columns:1fr}
    .period-split>div{background:#f5f8fb;border-radius:10px;padding:10px}.period-split span{display:block;font-size:11px;color:#667b90}.period-split strong{font-size:16px}
    .period-alert{margin:10px 0;padding:9px 11px;border-radius:9px;background:#fff0ee;color:#963b31;font-size:12px;font-weight:650}
    .period-filter{display:flex;gap:7px;flex-wrap:wrap;margin-bottom:9px}
    .period-filter .button.active{background:#fff;color:#185f96;box-shadow:inset 0 0 0 2px rgba(255,255,255,.7)}
    .period-pdf-actions{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
    .period-pdf-actions [aria-disabled="true"]{opacity:.45;pointer-events:none}
    .period-audit-strip{display:grid;grid-template-columns:repeat(2,minmax(190px,1fr));gap:8px;margin:12px 0}
    .period-audit-card{border:1px solid #d9e2eb;border-radius:10px;padding:9px 11px;background:#fff}
    .period-audit-card span{display:block;font-size:11px;color:#63778c}.period-audit-card strong{font-size:13px}
    .period-audit-card.error{background:#fff1ef;border-color:#f1c7c1}.period-audit-card.warning{background:#fff8e8;border-color:#ecdcae}.period-audit-card.ok{background:#edf8f1;border-color:#c7e5d2}
    #period-project-alerts{margin:10px 0}.period-project-alert-item{padding:8px 10px;margin:5px 0;border-left:3px solid #d69228;background:#fff8e7;border-radius:7px;font-size:12px;color:#684e20}
    #period-all-view{margin-top:14px}.period-overview-grid{display:grid;grid-template-columns:repeat(2,minmax(250px,1fr));gap:14px;margin-bottom:14px}
    .period-overview-card{border:1px solid #d8e1ea;border-radius:12px;padding:14px;background:#fff}.period-overview-card h3{margin:0 0 8px}.period-overview-card p{margin:5px 0;color:#62778b}
    .period-overview-table{width:100%;border-collapse:collapse}.period-overview-table th,.period-overview-table td{border-bottom:1px solid #e2e8ee;padding:9px;text-align:left}.period-overview-table th{font-size:12px;color:#597087;background:#f4f7fa}.period-overview-table td:not(:first-child),.period-overview-table th:not(:first-child){text-align:center}
    .period-shared-note{padding:10px 12px;border-radius:9px;background:#eef5fb;color:#2b5f83;margin-top:12px}
    .unified-general-note{padding:12px;border-radius:10px;background:#eef5fb;color:#315f80;grid-column:1/-1}
    #report-workspace[data-unified-normal="1"] #report-audit-state-badge{display:none!important}
    @media(max-width:800px){.period-split,.period-overview-grid,.period-audit-strip{grid-template-columns:1fr}}
  `;
  document.head.appendChild(css);

  function projectSummary() {
    return state?.activeReport?.project_summary || null;
  }

  function isPvcProject(project) {
    return String(project?.report_type || '').toLowerCase() === 'pvc';
  }

  function auditClass(stateValue) {
    if (stateValue === 'APTO PARA EMITIR') return 'ok';
    if (stateValue === 'BORRADOR') return 'warning';
    return 'error';
  }

  async function getOverview(force = false) {
    const project = projectSummary();
    if (!project?.period_project_id || isPvcProject(project)) return null;
    if (!force && overviewCache && overviewProjectId === Number(project.period_project_id)) return overviewCache;
    const data = await api(`/api/period-projects/${project.period_project_id}/overview`);
    overviewCache = data;
    overviewProjectId = Number(project.period_project_id);
    return data;
  }

  function renderUnifiedDashboard() {
    const reports = Array.isArray(state.reports) ? state.reports : [];
    const complexive = reports.reduce((sum, report) => sum + Number(report.complexive_records || 0), 0);
    const careers = reports.reduce((sum, report) => sum + Number(report.career_count || 0), 0);
    $('#dashboard-metrics').innerHTML = [
      ['Períodos', reports.length],
      ['Carreras en Complexivo', careers],
      ['Registros en Complexivo', complexive],
      ['Base de datos', 'Firebase + local'],
    ].map(([label, value]) => `<article class="metric"><span>${label}</span><strong>${value}</strong></article>`).join('');

    const grid = $('#reports-grid');
    if (!reports.length) {
      grid.innerHTML = '<div class="empty-mini">Todavía no existen períodos. Cree el primero para comenzar.</div>';
      return;
    }
    grid.className = 'period-card-grid';
    grid.innerHTML = reports.map(report => {
      const pvc = String(report.report_type || '').toLowerCase() === 'pvc';
      const split = pvc
        ? `<div class="period-split single"><div><span>Programa</span><strong>${Number(report.presencial_students || 0)} estudiantes</strong><span>${Number(report.presencial_complexive || 0)} registros en Complexivo</span></div></div>`
        : `<div class="period-split">
            <div><span>Presencial</span><strong>${Number(report.presencial_students || 0)} estudiantes</strong><span>${Number(report.presencial_complexive || 0)} registros en Complexivo</span></div>
            <div><span>Online</span><strong>${Number(report.online_students || 0)} estudiantes</strong><span>${Number(report.online_complexive || 0)} registros en Complexivo</span></div>
          </div>`;
      return `
        <article class="period-card">
          <span class="period-badge">${pvc ? 'PVC' : 'Presencial + Online'}</span>
          <h3>${escapeHtml(report.name || 'Informe del proceso de titulación')}</h3>
          <p>${escapeHtml(report.period || '')}</p>
          <p>${escapeHtml(report.code || 'Sin código institucional')}</p>
          ${split}
          ${!pvc && report.population_error ? `<div class="period-alert">${escapeHtml((report.alerts || [])[0] || 'Revise la población por modalidad.')}</div>` : ''}
          <div class="report-card-actions">
            <button class="button primary small" data-open-period="${report.id}">Abrir</button>
            <button class="button danger small" data-delete-period="${report.id}">Eliminar</button>
          </div>
        </article>`;
    }).join('');

    $$('[data-open-period]', grid).forEach(button => {
      button.onclick = async () => {
        currentView = 'todos';
        overviewCache = null;
        await openReport(Number(button.dataset.openPeriod));
      };
    });
    $$('[data-delete-period]', grid).forEach(button => {
      button.onclick = () => deleteReport(Number(button.dataset.deletePeriod));
    });
  }

  function normalizeGeneralForm() {
    const project = projectSummary();
    if (!project || isPvcProject(project)) return;
    const select = document.querySelector('#general-form select[name="modality"]');
    const label = select?.closest('label');
    if (label) {
      const note = document.createElement('div');
      note.className = 'unified-general-note';
      note.innerHTML = '<strong>Modalidades del período:</strong> Presencial + Online. La modalidad ya no se configura como un informe separado.';
      label.replaceWith(note);
    }
  }

  function cleanupUnifiedProjectUiForPvc() {
    document.getElementById('period-project-controls')?.remove();
    document.getElementById('period-project-alerts')?.remove();
    document.getElementById('period-pdf-actions')?.remove();
    const allView = document.getElementById('period-all-view');
    if (allView) allView.style.display = 'none';
    const tabs = $('#report-tabs');
    if (tabs) tabs.style.display = '';
    $$('.tab-content').forEach(node => { node.style.display = ''; });
    const oldPdf = $('#export-pdf');
    if (oldPdf) oldPdf.style.display = '';
    const workspace = $('#report-workspace');
    if (workspace) delete workspace.dataset.unifiedNormal;
    $('#report-modality').textContent = 'PVC';
  }

  function ensureProjectUi() {
    const report = state?.activeReport;
    const project = projectSummary();
    if (!report || !project) return;

    if (isPvcProject(project)) {
      cleanupUnifiedProjectUiForPvc();
      return;
    }

    const workspace = $('#report-workspace');
    if (workspace) workspace.dataset.unifiedNormal = '1';
    document.getElementById('modality-report-switcher')?.remove();
    document.getElementById('period-project-controls')?.remove();
    document.getElementById('period-project-alerts')?.remove();

    $('#report-modality').textContent = 'Período académico · Presencial + Online';
    $('#report-name').textContent = project.name || report.name;
    $('#report-period').textContent = project.period || report.period;

    const bannerInfo = document.querySelector('.report-banner > div:first-child');
    const controls = document.createElement('div');
    controls.id = 'period-project-controls';
    controls.innerHTML = `
      <div class="period-filter">
        <button type="button" class="button small ${currentView === 'todos' ? 'active' : ''}" data-period-view="todos">Todos</button>
        <button type="button" class="button small ${currentView === 'presencial' ? 'active' : ''}" data-period-view="presencial">Presencial</button>
        <button type="button" class="button small ${currentView === 'en_linea' ? 'active' : ''}" data-period-view="en_linea">Online</button>
      </div>`;
    bannerInfo?.insertBefore(controls, bannerInfo.firstChild);

    const actions = document.querySelector('.report-actions');
    const oldPdf = $('#export-pdf');
    if (oldPdf) oldPdf.style.display = 'none';
    let pdfActions = document.getElementById('period-pdf-actions');
    if (!pdfActions) {
      pdfActions = document.createElement('div');
      pdfActions.id = 'period-pdf-actions';
      pdfActions.className = 'period-pdf-actions';
      actions?.appendChild(pdfActions);
    }
    const presencialDisabled = !project.presencial_report_id || Number(project.presencial_students || 0) === 0;
    const onlineDisabled = !project.online_report_id || Number(project.online_students || 0) === 0;
    pdfActions.innerHTML = `
      <button type="button" class="button secondary" data-pdf-report-id="${Number(project.presencial_report_id || 0)}" data-pdf-label="Presencial" ${presencialDisabled ? 'disabled aria-disabled="true"' : ''}>PDF Presencial</button>
      <button type="button" class="button secondary" data-pdf-report-id="${Number(project.online_report_id || 0)}" data-pdf-label="Online" ${onlineDisabled ? 'disabled aria-disabled="true"' : ''}>PDF Online</button>`;

    const alerts = document.createElement('div');
    alerts.id = 'period-project-alerts';
    document.querySelector('.report-banner')?.insertAdjacentElement('afterend', alerts);

    $$('[data-period-view]', controls).forEach(button => {
      button.onclick = async () => {
        const target = button.dataset.periodView;
        if (target === 'todos') {
          currentView = 'todos';
          applyView();
          await renderOverview();
          return;
        }
        const targetId = target === 'presencial' ? project.presencial_report_id : project.online_report_id;
        if (!targetId) {
          toast(`No existe el dataset ${target === 'presencial' ? 'Presencial' : 'Online'} del período.`, true);
          return;
        }
        currentView = target;
        await openReport(Number(targetId));
      };
    });

    normalizeGeneralForm();
  }

  function ensureAllView() {
    let view = document.getElementById('period-all-view');
    if (!view) {
      view = document.createElement('div');
      view.id = 'period-all-view';
      const tabs = $('#report-tabs');
      tabs?.insertAdjacentElement('afterend', view);
    }
    return view;
  }

  function applyView() {
    const project = projectSummary();
    if (!project || isPvcProject(project)) return;
    const allView = ensureAllView();
    const tabs = $('#report-tabs');
    const contents = $$('.tab-content');
    if (currentView === 'todos') {
      if (tabs) tabs.style.display = 'none';
      contents.forEach(node => { node.style.display = 'none'; });
      allView.style.display = '';
    } else {
      if (tabs) tabs.style.display = '';
      contents.forEach(node => { node.style.display = ''; });
      allView.style.display = 'none';
    }
    const controls = document.getElementById('period-project-controls');
    if (controls) {
      $$('[data-period-view]', controls).forEach(button => button.classList.toggle('active', button.dataset.periodView === currentView));
    }
  }

  function auditCard(label, audit) {
    if (!audit) return `<article class="period-audit-card error"><span>${label}</span><strong>NO DISPONIBLE</strong></article>`;
    return `<article class="period-audit-card ${auditClass(audit.state)}"><span>${label}</span><strong>${escapeHtml(audit.state || 'BORRADOR')}</strong></article>`;
  }

  function renderAlerts(data) {
    const box = document.getElementById('period-project-alerts');
    if (!box || !data) return;
    const alerts = Array.isArray(data.alerts) ? data.alerts : [];
    box.innerHTML = `
      <div class="period-audit-strip">
        ${auditCard('Presencial', data.audits?.presencial)}
        ${auditCard('Online', data.audits?.en_linea)}
      </div>
      ${alerts.length ? alerts.slice(0, 8).map(item => `<div class="period-project-alert-item">${escapeHtml(item)}</div>`).join('') : ''}`;
  }

  function enforceProjectTitle() {
    const project = projectSummary();
    const node = $('#report-name');
    if (!project || isPvcProject(project) || !node) return;
    const expected = project.name || state.activeReport?.name || 'Informe del proceso de titulación';
    if (node.textContent !== expected) node.textContent = expected;
  }

  async function renderOverview() {
    const project = projectSummary();
    if (!project || isPvcProject(project)) return;
    const view = ensureAllView();
    if (currentView !== 'todos') return;
    view.innerHTML = '<div class="panel"><div class="loading-state">Consolidando Presencial y Online...</div></div>';
    try {
      const data = await getOverview(true);
      if (!data || currentView !== 'todos') return;
      renderAlerts(data);
      enforceProjectTitle();
      const p = data.audits?.presencial?.metrics || {};
      const o = data.audits?.en_linea?.metrics || {};
      view.innerHTML = `
        <div class="panel">
          <div class="panel-head"><div><h2>Vista general del período</h2><p>La información se conserva en un único proyecto y se analiza por modalidad.</p></div></div>
          <div class="period-overview-grid">
            <article class="period-overview-card"><h3>Presencial</h3><p><strong>${Number(p.requirements?.registered || 0)}</strong> estudiantes en Requisitos</p><p>Estado: <strong>${escapeHtml(data.audits?.presencial?.state || 'No disponible')}</strong></p></article>
            <article class="period-overview-card"><h3>Online</h3><p><strong>${Number(o.requirements?.registered || 0)}</strong> estudiantes en Requisitos</p><p>Estado: <strong>${escapeHtml(data.audits?.en_linea?.state || 'No disponible')}</strong></p></article>
          </div>
          <table class="period-overview-table">
            <thead><tr><th>Módulo</th><th>Presencial</th><th>Online</th><th>Total del período</th></tr></thead>
            <tbody>${(data.modules || []).map(row => `<tr><td>${escapeHtml(row.module)}</td><td>${Number(row.presencial || 0)}</td><td>${Number(row.online || 0)}</td><td><strong>${Number(row.total || 0)}</strong></td></tr>`).join('')}</tbody>
          </table>
          <div class="period-shared-note"><strong>Cronograma compartido:</strong> ${Number(data.shared_schedule || 0)} actividades únicas para todo el período.</div>
        </div>`;
    } catch (error) {
      view.innerHTML = `<div class="panel"><div class="empty-mini">${escapeHtml(error.message || 'No se pudo cargar la vista general.')}</div></div>`;
    }
  }

  async function refreshProjectStatus() {
    const project = projectSummary();
    if (!project || isPvcProject(project)) return;
    try {
      const data = await getOverview(true);
      renderAlerts(data);
      enforceProjectTitle();
    } catch (error) {
      const box = document.getElementById('period-project-alerts');
      if (box) box.innerHTML = `<div class="period-project-alert-item">${escapeHtml(error.message)}</div>`;
    }
  }

  document.addEventListener('informtit:students-domain-changed', () => {
    void refreshProjectStatus();
  });

  const previousRenderDashboard = renderDashboard;
  renderDashboard = function () {
    if (Array.isArray(state?.reports) && state.reports.every(item => item.period_project_id || item.modality === 'unified')) {
      renderUnifiedDashboard();
      return;
    }
    previousRenderDashboard();
  };

  const previousRenderReport = renderReport;
  renderReport = function () {
    previousRenderReport();
    const project = projectSummary();
    if (!project) return;
    if (isPvcProject(project)) {
      cleanupUnifiedProjectUiForPvc();
      return;
    }
    if (currentView === 'presencial' && state.activeReport.modality !== 'presencial') currentView = 'todos';
    if (currentView === 'en_linea' && state.activeReport.modality !== 'en_linea') currentView = 'todos';
    ensureProjectUi();
    applyView();
    if (currentView === 'todos') void renderOverview();
    else void refreshProjectStatus();
    queueMicrotask(() => {
      normalizeGeneralForm();
      enforceProjectTitle();
    });
  };

  const titleNode = $('#report-name');
  if (titleNode) {
    new MutationObserver(() => enforceProjectTitle()).observe(titleNode, {childList: true, characterData: true, subtree: true});
  }

  // Si ya se cargó el tablero antes de este script, lo vuelve a dibujar.
  if (Array.isArray(state?.reports) && state.reports.length) renderDashboard();
})();
