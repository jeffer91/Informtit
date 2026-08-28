(() => {
  if (window.__informtitSmartReconciliationInstalled) return;
  window.__informtitSmartReconciliationInstalled = true;

  const POLL_MS = 500;
  let activeJobId = null;
  let enhancing = false;

  function apiRequest(path, options = {}) {
    if (typeof api === 'function') return api(path, options);
    return fetch(path, {
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
      ...options,
    }).then(async response => {
      const data = await response.json().catch(() => ({}));
      if (!response.ok || data.ok === false) throw new Error(data.error || `Error ${response.status}`);
      return data;
    });
  }

  function projectId() {
    return Number(window.state?.activeReport?.project_summary?.period_project_id || 0);
  }

  function ensureStyles() {
    if (document.getElementById('smart-reconciliation-style')) return;
    const style = document.createElement('style');
    style.id = 'smart-reconciliation-style';
    style.textContent = `
      .smart-reconcile-overlay {
        position: fixed;
        inset: 0;
        z-index: 100001;
        display: grid;
        place-items: center;
        padding: 24px;
        background: rgba(15, 29, 43, .58);
        backdrop-filter: blur(3px);
      }
      .smart-reconcile-overlay[hidden] { display: none !important; }
      .smart-reconcile-card {
        width: min(720px, 94vw);
        border-radius: 18px;
        background: #fff;
        box-shadow: 0 24px 80px rgba(0,0,0,.28);
        padding: 28px;
      }
      .smart-reconcile-kicker {
        margin: 0 0 7px;
        color: #5d7184;
        font-size: 12px;
        font-weight: 800;
        letter-spacing: .08em;
        text-transform: uppercase;
      }
      .smart-reconcile-title { margin: 0; color: #18364f; font-size: 24px; }
      .smart-reconcile-stage { margin: 20px 0 5px; color: #244a73; font-size: 16px; font-weight: 800; }
      .smart-reconcile-detail { min-height: 42px; margin: 0 0 17px; color: #647586; line-height: 1.45; }
      .smart-reconcile-track { height: 16px; overflow: hidden; border-radius: 999px; background: #e7edf2; }
      .smart-reconcile-fill { width: 0; height: 100%; border-radius: inherit; background: linear-gradient(90deg,#244a73,#2f719f); transition: width .35s ease; }
      .smart-reconcile-meta { display: flex; justify-content: space-between; gap: 16px; margin-top: 9px; color: #627486; font-size: 13px; }
      .smart-reconcile-percent { color: #18364f; font-size: 20px; font-weight: 900; }
      .smart-reconcile-stats { display: grid; grid-template-columns: repeat(5,minmax(0,1fr)); gap: 10px; margin-top: 20px; }
      .smart-reconcile-stat { padding: 12px; border: 1px solid #e1e8ee; border-radius: 12px; background: #f8fafc; }
      .smart-reconcile-stat strong { display: block; color: #18364f; font-size: 20px; }
      .smart-reconcile-stat span { display: block; margin-top: 3px; color: #657788; font-size: 11px; line-height: 1.25; }
      .smart-reconcile-actions { display: flex; justify-content: flex-end; margin-top: 20px; }
      .smart-reconcile-card.done .smart-reconcile-fill { background: #2c7b55; }
      .smart-reconcile-card.error .smart-reconcile-fill { background: #b94b4b; }
      .smart-reconciliation-summary { display: grid; grid-template-columns: repeat(7,minmax(0,1fr)); gap: 10px; margin: 14px 0 18px; }
      .smart-summary-chip { border: 1px solid #e1e8ee; border-radius: 12px; padding: 11px 12px; background: #f8fafc; }
      .smart-summary-chip strong { display: block; color: #18364f; font-size: 18px; }
      .smart-summary-chip span { display: block; margin-top: 2px; color: #657788; font-size: 11px; }
      .smart-summary-chip.attention { background: #fff8e8; border-color: #f0d79b; }
      .smart-summary-chip.outside { background: #fff3ec; border-color: #efc8ad; }
      .smart-summary-chip.resolved { background: #eef8f2; border-color: #badbc8; }
      .student-match-card .student-badge[data-smart-status='outside'] { background: #fff0e6; color: #8a4c20; }
      @media (max-width: 760px) {
        .smart-reconcile-stats, .smart-reconciliation-summary { grid-template-columns: repeat(2,minmax(0,1fr)); }
      }
    `;
    document.head.appendChild(style);
  }

  function ensureOverlay() {
    ensureStyles();
    let overlay = document.getElementById('smart-reconcile-overlay');
    if (overlay) return overlay;
    overlay = document.createElement('div');
    overlay.id = 'smart-reconcile-overlay';
    overlay.className = 'smart-reconcile-overlay';
    overlay.hidden = true;
    overlay.innerHTML = `
      <section class="smart-reconcile-card" role="dialog" aria-modal="true" aria-labelledby="smart-reconcile-title">
        <p class="smart-reconcile-kicker">Conciliación inteligente</p>
        <h2 class="smart-reconcile-title" id="smart-reconcile-title">Reconciliando estudiantes</h2>
        <p class="smart-reconcile-stage" id="smart-reconcile-stage">Preparando conciliación</p>
        <p class="smart-reconcile-detail" id="smart-reconcile-detail">Analizando la población oficial y las evidencias académicas.</p>
        <div class="smart-reconcile-track" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="1">
          <div class="smart-reconcile-fill" id="smart-reconcile-fill"></div>
        </div>
        <div class="smart-reconcile-meta">
          <span>El porcentaje avanza cuando termina cada fase real del proceso.</span>
          <strong class="smart-reconcile-percent" id="smart-reconcile-percent">1 %</strong>
        </div>
        <div class="smart-reconcile-stats">
          <div class="smart-reconcile-stat"><strong id="smart-stat-auto">0</strong><span>resueltas automáticamente</span></div>
          <div class="smart-reconcile-stat"><strong id="smart-stat-cases">0</strong><span>casos por revisar</span></div>
          <div class="smart-reconcile-stat"><strong id="smart-stat-outside">0</strong><span>fuera de población</span></div>
          <div class="smart-reconcile-stat"><strong id="smart-stat-route">0</strong><span>conflictos de ruta</span></div>
          <div class="smart-reconcile-stat"><strong id="smart-stat-grade">0</strong><span>conflictos de nota</span></div>
        </div>
        <div class="smart-reconcile-actions">
          <button type="button" class="button secondary" id="smart-reconcile-close" hidden>Cerrar</button>
        </div>
      </section>`;
    document.body.appendChild(overlay);
    document.getElementById('smart-reconcile-close').addEventListener('click', () => {
      if (!activeJobId) overlay.hidden = true;
    });
    return overlay;
  }

  function setJob(job) {
    const overlay = ensureOverlay();
    const card = overlay.querySelector('.smart-reconcile-card');
    const progress = Math.max(0, Math.min(100, Number(job.progress || 0)));
    const stats = job.stats || {};
    overlay.hidden = false;
    card.classList.toggle('done', job.status === 'completed');
    card.classList.toggle('error', job.status === 'error');
    document.getElementById('smart-reconcile-stage').textContent = job.stage || 'Reconciliando estudiantes';
    document.getElementById('smart-reconcile-detail').textContent = job.error || job.detail || 'Procesando información.';
    document.getElementById('smart-reconcile-fill').style.width = `${progress}%`;
    document.getElementById('smart-reconcile-percent').textContent = `${Math.round(progress)} %`;
    overlay.querySelector('.smart-reconcile-track').setAttribute('aria-valuenow', String(Math.round(progress)));
    document.getElementById('smart-stat-auto').textContent = String(stats.auto_resolved || 0);
    document.getElementById('smart-stat-cases').textContent = String(stats.cases || 0);
    document.getElementById('smart-stat-outside').textContent = String(stats.outside_population || 0);
    document.getElementById('smart-stat-route').textContent = String(stats.route_conflicts || 0);
    document.getElementById('smart-stat-grade').textContent = String(stats.grade_conflicts || 0);
    document.getElementById('smart-reconcile-close').hidden = !['completed', 'error'].includes(job.status);
  }

  async function refreshStudentsView() {
    const button = document.querySelector('[data-period-students-view]');
    if (button) button.click();
    await enhanceMatchPanel(true);
  }

  async function pollJob(jobId) {
    try {
      while (activeJobId === jobId) {
        const result = await apiRequest(`/api/reconciliation-jobs/${jobId}`);
        const job = result.job;
        setJob(job);
        if (job.status === 'completed') {
          activeJobId = null;
          if (typeof toast === 'function') toast('Conciliación inteligente completada.');
          await refreshStudentsView();
          return;
        }
        if (job.status === 'error') {
          activeJobId = null;
          if (typeof toast === 'function') toast(job.error || 'No se pudo completar la conciliación.', true);
          return;
        }
        await new Promise(resolve => setTimeout(resolve, POLL_MS));
      }
    } catch (error) {
      activeJobId = null;
      setJob({ status: 'error', progress: 0, stage: 'No se pudo consultar el progreso', error: error.message, stats: {} });
      if (typeof toast === 'function') toast(error.message, true); else alert(error.message);
    }
  }

  async function startReconciliation(pid) {
    if (!pid || activeJobId) return;
    setJob({ status: 'queued', progress: 1, stage: 'Preparando conciliación', detail: 'Iniciando el análisis inteligente de identidad y evidencias académicas.', stats: {} });
    try {
      const result = await apiRequest(`/api/period-projects/${pid}/students-domain/reconcile-jobs`, {
        method: 'POST',
        body: JSON.stringify({}),
      });
      activeJobId = result.job.id;
      setJob(result.job);
      await pollJob(activeJobId);
    } catch (error) {
      activeJobId = null;
      setJob({ status: 'error', progress: 0, stage: 'No se pudo iniciar la conciliación', error: error.message, stats: {} });
      if (typeof toast === 'function') toast(error.message, true); else alert(error.message);
    }
  }

  function relabelStatuses(panel) {
    panel.querySelectorAll('.student-match-card').forEach(card => {
      const badge = card.querySelector('.student-badge');
      if (!badge) return;
      const raw = badge.textContent.trim();
      const labels = {
        OUT_OF_POPULATION: 'FUERA DE POBLACIÓN',
        REVIEW_REQUIRED: 'REVISAR IDENTIDAD',
        AMBIGUOUS: 'IDENTIDAD AMBIGUA',
        IDENTITY_CONFLICT: 'CONFLICTO DE IDENTIDAD',
        ROUTE_CONFLICT: 'CONFLICTO DE RUTA',
        UNMATCHED: 'SIN COINCIDENCIA',
        OFFICIAL_DATA_CONFLICT: 'INCONSISTENCIA EN REQUISITOS',
      };
      if (labels[raw]) badge.textContent = labels[raw];
      if (raw === 'OUT_OF_POPULATION') badge.dataset.smartStatus = 'outside';
    });
  }

  async function enhanceMatchPanel(force = false) {
    if (enhancing) return;
    const panel = document.querySelector('.student-match-panel');
    const pid = projectId();
    if (!panel || !pid) return;
    if (!force && panel.dataset.smartSummary === String(pid)) {
      relabelStatuses(panel);
      return;
    }
    enhancing = true;
    try {
      const result = await apiRequest(`/api/period-projects/${pid}/reconciliation-summary`);
      const summary = result.summary || {};
      const head = panel.querySelector('.panel-head');
      const title = head?.querySelector('h2');
      const intro = head?.querySelector('p');
      const total = head?.querySelector(':scope > strong');
      if (title) title.textContent = 'Casos que requieren atención';
      if (intro) intro.textContent = 'Las evidencias repetidas del mismo estudiante se agrupan en un solo caso. Las coincidencias fuertes se resuelven automáticamente; aquí quedan solo decisiones reales.';
      if (total) total.textContent = String(summary.total_cases || 0);

      panel.querySelector('.smart-reconciliation-summary')?.remove();
      const grid = document.createElement('div');
      grid.className = 'smart-reconciliation-summary';
      grid.innerHTML = `
        <div class="smart-summary-chip attention"><strong>${summary.total_cases || 0}</strong><span>casos reales</span></div>
        <div class="smart-summary-chip outside"><strong>${summary.outside_population || 0}</strong><span>fuera de población confirmado</span></div>
        <div class="smart-summary-chip"><strong>${summary.identity_review || 0}</strong><span>identidades por confirmar</span></div>
        <div class="smart-summary-chip"><strong>${summary.official_review || 0}</strong><span>inconsistencias de Requisitos</span></div>
        <div class="smart-summary-chip"><strong>${summary.route_conflicts || 0}</strong><span>conflictos de ruta</span></div>
        <div class="smart-summary-chip"><strong>${summary.grade_conflicts || 0}</strong><span>conflictos de nota</span></div>
        <div class="smart-summary-chip resolved"><strong>${summary.auto_resolved || 0}</strong><span>evidencias auto-resueltas</span></div>`;
      if (head) head.insertAdjacentElement('afterend', grid);
      panel.dataset.smartSummary = String(pid);
      relabelStatuses(panel);
    } catch (_) {
      relabelStatuses(panel);
    } finally {
      enhancing = false;
    }
  }

  document.addEventListener('click', event => {
    const reconcile = event.target.closest('#period-student-refresh');
    if (!reconcile) return;
    event.preventDefault();
    event.stopImmediatePropagation();

    // Otros componentes antiguos usaban button.click() como una forma de refrescar
    // la vista. Esos clics sintéticos ya no deben disparar una conciliación pesada.
    if (!event.isTrusted) {
      document.querySelector('[data-period-students-view]')?.click();
      return;
    }
    startReconciliation(projectId());
  }, true);

  const observer = new MutationObserver(() => {
    if (document.querySelector('.student-match-panel')) {
      requestAnimationFrame(() => enhanceMatchPanel(false));
    }
  });

  ensureStyles();
  observer.observe(document.documentElement, { subtree: true, childList: true });
  document.addEventListener('DOMContentLoaded', () => enhanceMatchPanel(false));
  setTimeout(() => enhanceMatchPanel(false), 0);
})();
