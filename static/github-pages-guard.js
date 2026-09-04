(() => {
  'use strict';

  if (!/(^|\.)github\.io$/i.test(window.location.hostname)) return;

  const storageKey = 'informtit.apiBase';
  let stored = '';
  try { stored = window.localStorage.getItem(storageKey) || ''; } catch (_) {}
  const apiBase = String(window.INFORMTIT_API_BASE || stored || '').trim().replace(/\/+$/, '');
  const backendConnected = Boolean(apiBase);
  const directFirebase = Boolean(window.INFORMTIT_FIREBASE_DIRECT);
  const oldFetch = window.fetch.bind(window);
  const safeStartup = new Map([
    ['/api/health', {
      ok: true,
      mode: directFirebase ? 'github-pages-firebase' : 'github-pages',
      backend_connected: backendConnected,
      firebase_direct: directFirebase,
    }],
    ['/api/runtime-info', {
      ok: true,
      build: directFirebase ? 'GitHub Pages + Firebase' : 'GitHub Pages',
      reports: 0,
      database: directFirebase ? 'Firebase UTET + local web' : (backendConnected ? 'Servidor web' : 'Servidor pendiente'),
      backend_connected: backendConnected,
      firebase_direct: directFirebase,
    }],
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
      || /backend.*no respondio correctamente/i.test(message)
      || /servicio local de Informtit/i.test(message);
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

  function showBackendOnlyNote() {
    if (backendConnected) return;
    let note = document.getElementById('pages-backend-only-note');
    if (!note) {
      note = document.createElement('div');
      note.id = 'pages-backend-only-note';
      note.style.cssText = [
        'margin:0 0 14px', 'padding:10px 12px', 'border-radius:10px',
        'background:#fff7ed', 'border:1px solid #fed7aa', 'color:#7c2d12',
        'font:12.5px/1.4 system-ui,-apple-system,Segoe UI,sans-serif'
      ].join(';');
      const dashboard = document.getElementById('view-dashboard');
      const firebaseCard = document.getElementById('firebase-pages-status');
      if (dashboard && firebaseCard?.parentElement === dashboard) firebaseCard.insertAdjacentElement('afterend', note);
      else dashboard?.insertBefore(note, dashboard.firstChild);
    }
    note.textContent = directFirebase
      ? 'Firebase UTET está conectado. Esta función todavía necesita el motor de informes/PDF del servidor.'
      : 'Esta acción necesita conectar el servidor web de Informtit.';
    window.setTimeout(() => { if (note) note.remove(); }, 6000);
  }

  function blockBackendActions(event) {
    if (backendConnected) return;
    const target = event.target.closest?.('button, a');
    if (!target) return;
    if (target.classList.contains('nav-item')) return;

    const id = String(target.id || '').toLowerCase();
    const text = String(target.textContent || '').trim().toLowerCase();

    if (id === 'refresh-btn' || id === 'firebase-sync-btn') return;
    if (target.closest('#firebase-sync-dialog')) return;

    // En GitHub Pages + Firebase, crear y abrir informes ya funciona con
    // almacenamiento local del navegador. No se debe bloquear el formulario.
    if (directFirebase && (id === 'new-report-btn' || id === 'new-pvc-report-btn')) return;

    const operational = id === 'new-report-btn'
      || id === 'new-pvc-report-btn'
      || id === 'firebase-publish-btn'
      || target.closest('.report-actions')
      || /(publicar notas|generar informes|pdfs generados)/i.test(text);
    if (!operational) return;

    event.preventDefault();
    event.stopImmediatePropagation();
    showBackendOnlyNote();
  }

  window.addEventListener('unhandledrejection', (event) => {
    if (!backendConnected && isBackendMessage(event.reason)) {
      event.preventDefault();
      hideFalseBackendErrors();
    }
  }, true);

  window.addEventListener('error', (event) => {
    if (!backendConnected && isBackendMessage(event.error || event.message)) {
      event.preventDefault();
      hideFalseBackendErrors();
    }
  }, true);

  document.addEventListener('click', blockBackendActions, true);

  const observer = new MutationObserver(() => {
    removeConsoleButtons();
    if (!backendConnected) hideFalseBackendErrors();
    if (directFirebase) document.getElementById('informtit-web-bridge')?.remove();
  });

  function install() {
    removeConsoleButtons();
    hideFalseBackendErrors();
    if (directFirebase) document.getElementById('informtit-web-bridge')?.remove();
    observer.observe(document.documentElement, { childList: true, subtree: true });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install, { once: true });
  else install();
})();
