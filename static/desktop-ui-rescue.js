// Guardia final de escritorio: mantiene el tablero y los controles principales
// operativos aunque una extensión de interfaz falle durante el arranque.
(function () {
  'use strict';

  if (window.__informtitDesktopUiRescueInstalled) return;
  window.__informtitDesktopUiRescueInstalled = true;

  const CORE_VIEWS = new Set(['dashboard', 'report', 'ai']);
  const q = (selector, root = document) => root.querySelector(selector);
  const qa = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[char]));

  function statusNode() {
    let node = q('#desktop-ui-rescue-status');
    if (node) return node;
    node = document.createElement('div');
    node.id = 'desktop-ui-rescue-status';
    node.hidden = true;
    node.style.cssText = 'margin:0 0 14px;padding:10px 12px;border-radius:10px;font-size:13px;line-height:1.4;border:1px solid #c7e5d2;background:#edf8f1;color:#245f43';
    q('#view-dashboard')?.prepend(node);
    return node;
  }

  function showStatus(message, error = false) {
    const node = statusNode();
    if (node) {
      node.hidden = false;
      node.textContent = message;
      node.style.background = error ? '#fff0ee' : '#edf8f1';
      node.style.color = error ? '#91382f' : '#245f43';
      node.style.borderColor = error ? '#efc7c1' : '#c7e5d2';
    }
    if (error && typeof toast === 'function') {
      try { toast(message, true); } catch (_error) { /* diagnóstico visual secundario */ }
    }
  }

  function clearStatus() {
    const node = q('#desktop-ui-rescue-status');
    if (node) node.hidden = true;
  }

  async function json(path, options = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 12000);
    try {
      const response = await fetch(path, {
        cache: 'no-store',
        headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
        ...options,
        signal: controller.signal,
      });
      const type = response.headers.get('content-type') || '';
      const data = type.includes('application/json') ? await response.json() : null;
      if (!response.ok || data?.ok === false) {
        throw new Error(data?.error || `HTTP ${response.status}`);
      }
      return data;
    } finally {
      clearTimeout(timer);
    }
  }

  function showViewFallback(name) {
    qa('.view').forEach((view) => view.classList.remove('active'));
    q(`#view-${name}`)?.classList.add('active');
    qa('.nav-item[data-view]').forEach((item) => item.classList.toggle('active', item.dataset.view === name));
  }

  function renderFallback(reports) {
    const list = Array.isArray(reports) ? reports : [];
    const grid = q('#reports-grid');
    const metrics = q('#dashboard-metrics');
    if (!grid || !metrics) return;

    const careers = list.reduce((sum, item) => sum + Number(item.career_count || 0), 0);
    const students = list.reduce((sum, item) => sum + Number(item.student_count || 0), 0);
    metrics.innerHTML = [
      ['Períodos', list.length],
      ['Carreras', careers],
      ['Estudiantes', students],
      ['Base de datos', 'SQLite'],
    ].map(([label, value]) => `<article class="metric"><span>${esc(label)}</span><strong>${esc(value)}</strong></article>`).join('');

    if (!list.length) {
      grid.innerHTML = '<div class="empty-mini">La base activa no contiene períodos visibles.</div>';
      return;
    }

    grid.className = 'period-card-grid';
    grid.innerHTML = list.map((report) => {
      const unified = report.modality === 'unified' || report.period_project_id;
      const primaryId = Number(report.id || report.presencial_report_id || report.online_report_id || 0);
      const split = unified
        ? `<div class="period-split"><div><span>Presencial</span><strong>${Number(report.presencial_students || 0)} estudiantes</strong></div><div><span>Online</span><strong>${Number(report.online_students || 0)} estudiantes</strong></div></div>`
        : `<div class="period-split single"><div><span>${report.modality === 'en_linea' ? 'Online' : 'Presencial'}</span><strong>${Number(report.student_count || 0)} estudiantes</strong></div></div>`;
      return `<article class="period-card report-card">
        <span class="period-badge badge">${unified ? 'Presencial + Online' : (report.modality === 'en_linea' ? 'Online' : 'Presencial')}</span>
        <h3>${esc(report.name || 'Informe del proceso de titulación')}</h3>
        <p>${esc(report.period || '')}</p>
        <p>${esc(report.code || 'Sin código institucional')}</p>
        ${split}
        <div class="report-card-actions"><button type="button" class="button primary small" data-rescue-open="${primaryId}">Abrir</button></div>
      </article>`;
    }).join('');
  }

  async function loadDashboard() {
    try {
      const data = await json('/api/reports');
      const reports = Array.isArray(data?.reports) ? data.reports : [];
      let normalRendered = false;
      if (typeof loadReports === 'function') {
        try {
          await loadReports();
          normalRendered = !!q('#reports-grid')?.children.length;
        } catch (error) {
          console.error('[Informtit rescue] loadReports:', error);
        }
      }
      if (!normalRendered) renderFallback(reports);
      clearStatus();
      return reports;
    } catch (error) {
      showStatus(`No se pudo cargar la base de informes: ${error?.message || error}`, true);
      console.error('[Informtit rescue] dashboard:', error);
      return [];
    }
  }

  async function openReportSafe(id) {
    if (!id) return false;
    try {
      if (typeof openReport === 'function') {
        await openReport(Number(id));
        return true;
      }
      showStatus('La función para abrir informes no terminó de inicializar. Abra Consola para ver el error de JavaScript.', true);
    } catch (error) {
      showStatus(`No se pudo abrir el informe: ${error?.message || error}`, true);
      console.error('[Informtit rescue] openReport:', error);
    }
    return false;
  }

  async function refreshSafe() {
    const activeId = Number(state?.activeReport?.id || 0);
    showStatus('Actualizando información...');
    await loadDashboard();
    if (activeId) {
      await openReportSafe(activeId);
    }
    clearStatus();
  }

  document.addEventListener('click', (event) => {
    const target = event.target instanceof Element ? event.target : null;
    if (!target) return;

    const newReport = target.closest('#new-report-btn');
    if (newReport) {
      event.preventDefault();
      event.stopPropagation();
      const dialog = q('#report-dialog');
      if (dialog && !dialog.open) dialog.showModal();
      else if (!dialog) showStatus('No se encontró el formulario de Nuevo informe.', true);
      return;
    }

    const refresh = target.closest('#refresh-btn');
    if (refresh) {
      event.preventDefault();
      event.stopPropagation();
      void refreshSafe();
      return;
    }

    const nav = target.closest('.nav-item[data-view]');
    if (nav) {
      const name = nav.dataset.view;
      // Las vistas agregadas por módulos tienen controladores propios. No detener
      // su evento ni pasarlas por showView(), porque el catálogo base no las conoce.
      if (!CORE_VIEWS.has(name)) return;
      event.preventDefault();
      event.stopPropagation();
      try {
        if (typeof showView === 'function') showView(name);
        else showViewFallback(name);
      } catch (error) {
        showViewFallback(name);
        console.error('[Informtit rescue] navigation:', error);
      }
      return;
    }

    const open = target.closest('[data-rescue-open]');
    if (open) {
      event.preventDefault();
      event.stopPropagation();
      void openReportSafe(Number(open.dataset.rescueOpen));
    }
  }, true);

  window.addEventListener('error', (event) => {
    console.error('[Informtit renderer]', event.error || event.message);
  });

  window.addEventListener('unhandledrejection', (event) => {
    console.error('[Informtit renderer promise]', event.reason);
  });

  async function boot() {
    // Fuerza interactividad aunque otra capa haya reemplazado propiedades onclick.
    ['#new-report-btn', '#refresh-btn'].forEach((selector) => {
      const node = q(selector);
      if (node) {
        node.disabled = false;
        node.style.pointerEvents = 'auto';
      }
    });
    await loadDashboard();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => void boot(), { once: true });
  } else {
    void boot();
  }
})();
