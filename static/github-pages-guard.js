(() => {
  'use strict';

  if (!/(^|\.)github\.io$/i.test(window.location.hostname)) return;

  const storageKey = 'informtit.apiBase';
  let stored = '';
  try { stored = window.localStorage.getItem(storageKey) || ''; } catch (_) {}
  const apiBase = String(window.INFORMTIT_API_BASE || stored || '').trim().replace(/\/+$/, '');
  const backendConnected = Boolean(apiBase);
  const oldFetch = window.fetch.bind(window);
  const safeStartup = new Map([
    ['/api/health', { ok: true, mode: 'github-pages', backend_connected: backendConnected }],
    ['/api/runtime-info', {
      ok: true,
      build: 'GitHub Pages',
      reports: 0,
      database: backendConnected ? 'Servidor web' : 'Servidor pendiente',
      backend_connected: backendConnected,
    }],
    ['/api/reports', { ok: true, reports: [] }],
  ]);

  function pathOf(input) {
    try {
      const raw = typeof input === 'string' ? input : input?.url;
      return new URL(raw, window.location.href).pathname;
    } catch (_) {
      return '';
    }
  }

  function jsonResponse(payload) {
    return Promise.resolve(new Response(JSON.stringify(payload), {
      status: 200,
      headers: { 'Content-Type': 'application/json; charset=utf-8' },
    }));
  }

  if (!backendConnected) {
    window.fetch = function pagesSafeFetch(input, init) {
      const method = String(init?.method || input?.method || 'GET').toUpperCase();
      const path = pathOf(input);
      if (method === 'GET' && safeStartup.has(path)) return jsonResponse(safeStartup.get(path));
      return oldFetch(input, init);
    };
  }

  function isBackendMessage(value) {
    const message = String(value?.message || value || '');
    return /necesita conectar el backend/i.test(message)
      || /servidor web de Informtit.*no est[aá] conectado/i.test(message)
      || /backend.*no respondio correctamente/i.test(message);
  }

  function removeConsoleButtons() {
    document.querySelectorAll('.top-actions button').forEach((button) => {
      if (String(button.textContent || '').trim().toLowerCase() === 'consola') button.remove();
    });
  }

  function hideFalseBackendErrors() {
    document.querySelectorAll('#startup-status, .startup-status').forEach((node) => {
      if (isBackendMessage(node.textContent)) node.hidden = true;
    });
    document.querySelectorAll('.toast, [role="alert"], .alert, .error-message').forEach((node) => {
      if (isBackendMessage(node.textContent)) node.hidden = true;
    });
  }

  function showConnectionPanel() {
    if (backendConnected) return;
    document.getElementById('informtit-web-bridge')?.remove();

    const panel = document.createElement('div');
    panel.id = 'informtit-web-bridge';
    panel.style.cssText = [
      'margin:0 0 16px',
      'padding:13px 15px',
      'border-radius:12px',
      'background:#eef6ff',
      'border:1px solid #bfdbfe',
      'color:#1e3a5f',
      'font:13px/1.45 system-ui,-apple-system,Segoe UI,sans-serif'
    ].join(';');
    panel.innerHTML = `
      <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap">
        <div style="flex:1;min-width:300px">
          <strong style="display:block;margin-bottom:3px">Informtit web está publicado</strong>
          <span>La interfaz funciona en GitHub Pages. Para cargar o guardar informes, sincronizar Firebase y generar PDF, falta conectar el servidor de Informtit.</span>
        </div>
        <input id="informtit-pages-api" type="url" placeholder="https://informtit-api.example.com"
          aria-label="URL del servidor de Informtit"
          style="flex:1.1;min-width:260px;padding:9px 11px;border:1px solid #93c5fd;border-radius:9px;background:#fff;color:#111827">
        <button id="informtit-pages-connect" type="button" class="button primary" style="white-space:nowrap">Conectar servidor</button>
      </div>`;

    const dashboard = document.getElementById('view-dashboard');
    if (dashboard) dashboard.insertBefore(panel, dashboard.firstChild);
    else document.body.appendChild(panel);

    const input = panel.querySelector('#informtit-pages-api');
    const button = panel.querySelector('#informtit-pages-connect');
    button.addEventListener('click', () => {
      const value = String(input.value || '').trim().replace(/\/+$/, '');
      if (!/^https?:\/\//i.test(value)) {
        input.setCustomValidity('Ingrese una URL http o https válida.');
        input.reportValidity();
        return;
      }
      input.setCustomValidity('');
      try { window.localStorage.setItem(storageKey, value); } catch (_) {}
      window.location.reload();
    });
  }

  function blockBackendActions(event) {
    if (backendConnected) return;
    const target = event.target.closest?.('button, a');
    if (!target || target.closest('#informtit-web-bridge')) return;
    if (target.classList.contains('nav-item')) return;

    const id = String(target.id || '').toLowerCase();
    const text = String(target.textContent || '').trim().toLowerCase();
    const operational = target.closest('.top-actions')
      || target.closest('.report-actions')
      || /(firebase|publicar|sincronizar|generar|nuevo informe|nuevo pvc|actualizar)/i.test(`${id} ${text}`);
    if (!operational) return;

    event.preventDefault();
    event.stopImmediatePropagation();
    showConnectionPanel();
    document.getElementById('informtit-web-bridge')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  window.addEventListener('unhandledrejection', (event) => {
    if (!backendConnected && isBackendMessage(event.reason)) {
      event.preventDefault();
      hideFalseBackendErrors();
      showConnectionPanel();
    }
  }, true);

  window.addEventListener('error', (event) => {
    if (!backendConnected && isBackendMessage(event.error || event.message)) {
      event.preventDefault();
      hideFalseBackendErrors();
      showConnectionPanel();
    }
  }, true);

  document.addEventListener('click', blockBackendActions, true);

  const observer = new MutationObserver(() => {
    removeConsoleButtons();
    if (!backendConnected) hideFalseBackendErrors();
  });

  function install() {
    removeConsoleButtons();
    hideFalseBackendErrors();
    if (!backendConnected) showConnectionPanel();
    observer.observe(document.documentElement, { childList: true, subtree: true });

    const footer = document.querySelector('.sidebar-footer span:last-child');
    if (footer) footer.textContent = backendConnected ? 'Informtit web conectado' : 'Informtit web';
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install, { once: true });
  else install();
})();
