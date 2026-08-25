// Respaldo de arranque: mantiene controles basicos utilizables y hace visibles
// los errores de inicializacion en lugar de dejar la pantalla aparentemente muerta.
(function () {
  'use strict';

  if (window.__informtitStartupGuardInstalled) return;
  window.__informtitStartupGuardInstalled = true;

  function ensureStatus() {
    let node = document.getElementById('startup-status');
    if (node) return node;
    node = document.createElement('div');
    node.id = 'startup-status';
    node.hidden = true;
    node.style.margin = '0 0 14px';
    node.style.padding = '10px 12px';
    node.style.borderRadius = '10px';
    node.style.fontSize = '13px';
    node.style.lineHeight = '1.4';
    const dashboard = document.getElementById('view-dashboard');
    dashboard?.insertBefore(node, dashboard.firstChild);
    return node;
  }

  function showStatus(message, error = false) {
    const node = ensureStatus();
    if (!node) return;
    node.hidden = false;
    node.textContent = message;
    node.style.background = error ? '#fff0ee' : '#edf8f1';
    node.style.color = error ? '#91382f' : '#245f43';
    node.style.border = error ? '1px solid #efc7c1' : '1px solid #c7e5d2';
  }

  function hideStatus() {
    const node = document.getElementById('startup-status');
    if (node) node.hidden = true;
  }

  function ensureNewReportButton() {
    const button = document.getElementById('new-report-btn');
    const dialog = document.getElementById('report-dialog');
    if (!button || !dialog || button.dataset.startupGuard === '1') return;
    button.dataset.startupGuard = '1';
    button.addEventListener('click', () => {
      if (!dialog.open) dialog.showModal();
    });
  }

  function ensureRefreshButton() {
    const button = document.getElementById('refresh-btn');
    if (!button || button.dataset.startupGuard === '1') return;
    button.dataset.startupGuard = '1';
    button.addEventListener('click', async () => {
      try {
        if (typeof loadReports === 'function') {
          await loadReports();
          hideStatus();
        } else {
          location.reload();
        }
      } catch (error) {
        showStatus(`No se pudo actualizar: ${error?.message || error}`, true);
      }
    });
  }

  function ensureNavigation() {
    document.querySelectorAll('.nav-item[data-view]').forEach(button => {
      if (button.dataset.startupGuard === '1') return;
      button.dataset.startupGuard = '1';
      button.addEventListener('click', () => {
        const name = button.dataset.view;
        if (typeof showView === 'function') {
          showView(name);
          return;
        }
        document.querySelectorAll('.view').forEach(view => view.classList.remove('active'));
        document.getElementById(`view-${name}`)?.classList.add('active');
        document.querySelectorAll('.nav-item').forEach(item => item.classList.toggle('active', item === button));
      });
    });
  }

  function ensureConsoleButton() {
    const actions = document.querySelector('.top-actions');
    if (!actions || document.getElementById('startup-console-btn')) return;
    const button = document.createElement('button');
    button.type = 'button';
    button.id = 'startup-console-btn';
    button.className = 'button secondary';
    button.textContent = 'Consola';
    button.onclick = async () => {
      if (window.informtitDesktop?.openDevTools) await window.informtitDesktop.openDevTools();
    };
    actions.insertBefore(button, actions.firstChild);
  }

  function showRuntimeInfo(info) {
    const footer = document.querySelector('.sidebar-footer');
    if (!footer || !info) return;
    let detail = document.getElementById('runtime-database-info');
    if (!detail) {
      detail = document.createElement('small');
      detail.id = 'runtime-database-info';
      detail.style.display = 'block';
      detail.style.marginTop = '6px';
      detail.style.fontSize = '10px';
      detail.style.lineHeight = '1.35';
      detail.style.opacity = '.78';
      footer.appendChild(detail);
    }
    detail.textContent = `${info.build || 'build'} · ${Number(info.reports || 0)} informes`;
    detail.title = `Base activa: ${info.database || 'desconocida'}`;
  }

  async function runtimeCheck() {
    try {
      const response = await fetch('/api/runtime-info', { cache: 'no-store' });
      if (!response.ok) return null;
      const info = await response.json();
      showRuntimeInfo(info);
      return info;
    } catch (_error) {
      return null;
    }
  }

  async function healthCheck() {
    try {
      const response = await fetch('/api/health', { cache: 'no-store' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      if (!data?.ok) throw new Error(data?.error || 'Respuesta de salud invalida');

      const runtime = await runtimeCheck();

      // Si app.js no alcanzo a llenar el tablero, fuerza un segundo intento.
      if (typeof loadReports === 'function' && !document.getElementById('dashboard-metrics')?.children.length) {
        await loadReports();
      }

      // Si SQLite tiene informes pero la cuadrícula sigue vacía, no ocultar el
      // problema: deja un diagnóstico visible en vez de una pantalla silenciosa.
      if (runtime && Number(runtime.reports || 0) > 0 && !document.getElementById('reports-grid')?.children.length) {
        showStatus(
          `SQLite contiene ${runtime.reports} informe(s), pero la interfaz no pudo mostrarlos. Base activa: ${runtime.database}`,
          true
        );
        return;
      }
      hideStatus();
    } catch (error) {
      showStatus(
        `Informtit inicio la interfaz, pero el backend no respondio correctamente: ${error?.message || error}. Abra Consola para ver el detalle.`,
        true
      );
    }
  }

  window.addEventListener('error', event => {
    showStatus(`Error de interfaz: ${event.message || 'error JavaScript no identificado'}.`, true);
  });

  window.addEventListener('unhandledrejection', event => {
    const reason = event.reason?.message || String(event.reason || 'promesa rechazada');
    showStatus(`Error de operacion: ${reason}.`, true);
  });

  function install() {
    ensureNewReportButton();
    ensureRefreshButton();
    ensureNavigation();
    ensureConsoleButton();
    window.setTimeout(healthCheck, 250);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install, { once: true });
  else install();
})();
