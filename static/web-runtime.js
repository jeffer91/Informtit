(() => {
  'use strict';

  const isGitHubPages = /(^|\.)github\.io$/i.test(window.location.hostname);
  const storageKey = 'informtit.apiBase';
  const params = new URLSearchParams(window.location.search);
  const queryApi = String(params.get('api') || '').trim();

  function normalizeBase(value) {
    return String(value || '').trim().replace(/\/+$/, '');
  }

  if (queryApi) {
    try { window.localStorage.setItem(storageKey, normalizeBase(queryApi)); } catch (_) {}
  }

  let stored = '';
  try { stored = window.localStorage.getItem(storageKey) || ''; } catch (_) {}
  const apiBase = normalizeBase(window.INFORMTIT_API_BASE || stored);
  window.INFORMTIT_API_BASE = apiBase;

  if (queryApi) {
    params.delete('api');
    const cleaned = `${window.location.pathname}${params.toString() ? `?${params}` : ''}${window.location.hash}`;
    window.history.replaceState(null, '', cleaned);
  }

  const backendPath = /^\/(api|uploads|exports)\//i;

  function translateUrl(value) {
    if (!apiBase || typeof value !== 'string' || !backendPath.test(value)) return value;
    return `${apiBase}${value}`;
  }

  const nativeFetch = window.fetch.bind(window);
  window.fetch = function informtitFetch(input, init) {
    if (typeof input === 'string') {
      if (isGitHubPages && !apiBase && backendPath.test(input)) {
        return Promise.reject(new TypeError('Informtit web necesita conectar el backend antes de usar esta función.'));
      }
      return nativeFetch(translateUrl(input), init);
    }
    if (input instanceof Request) {
      const url = new URL(input.url, window.location.href);
      if (backendPath.test(url.pathname)) {
        if (isGitHubPages && !apiBase) {
          return Promise.reject(new TypeError('Informtit web necesita conectar el backend antes de usar esta función.'));
        }
        const translated = `${apiBase}${url.pathname}${url.search}`;
        return nativeFetch(new Request(translated, input), init);
      }
    }
    return nativeFetch(input, init);
  };

  const nativeOpen = window.open.bind(window);
  window.open = function informtitOpen(url, ...args) {
    return nativeOpen(translateUrl(url), ...args);
  };

  function rewriteElement(node) {
    if (!(node instanceof Element) || !apiBase) return;
    const candidates = [node, ...node.querySelectorAll('[href],[src]')];
    candidates.forEach((element) => {
      if (element.hasAttribute('href')) {
        const value = element.getAttribute('href');
        if (value && backendPath.test(value)) element.setAttribute('href', translateUrl(value));
      }
      if (element.hasAttribute('src')) {
        const value = element.getAttribute('src');
        if (value && backendPath.test(value)) element.setAttribute('src', translateUrl(value));
      }
    });
  }

  document.addEventListener('click', (event) => {
    const anchor = event.target.closest?.('a[href]');
    if (!anchor) return;
    const href = anchor.getAttribute('href') || '';
    if (!backendPath.test(href)) return;
    if (!apiBase) {
      event.preventDefault();
      showConnectionPanel(true);
      return;
    }
    anchor.setAttribute('href', translateUrl(href));
  }, true);

  const observer = new MutationObserver((mutations) => {
    if (!apiBase) return;
    mutations.forEach((mutation) => mutation.addedNodes.forEach((node) => rewriteElement(node)));
  });

  function showConnectionPanel(force = false) {
    if (!isGitHubPages || (apiBase && !force) || document.getElementById('informtit-web-bridge')) return;

    const panel = document.createElement('div');
    panel.id = 'informtit-web-bridge';
    panel.style.cssText = [
      'position:fixed', 'left:16px', 'right:16px', 'bottom:16px', 'z-index:99999',
      'background:#0f172a', 'color:#fff', 'border:1px solid #334155', 'border-radius:14px',
      'padding:14px 16px', 'box-shadow:0 12px 38px rgba(0,0,0,.35)',
      'font:14px/1.35 system-ui,-apple-system,Segoe UI,sans-serif'
    ].join(';');
    panel.innerHTML = `
      <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap">
        <div style="flex:1;min-width:260px">
          <strong style="display:block;margin-bottom:3px">Informtit web</strong>
          <span>Conecte la API de Informtit para habilitar todas las funciones del sistema.</span>
        </div>
        <input id="informtit-api-input" type="url" placeholder="https://su-backend-informtit.example.com"
          style="flex:2;min-width:280px;padding:9px 11px;border:1px solid #475569;border-radius:9px;background:#fff;color:#111827">
        <button id="informtit-api-save" type="button"
          style="padding:9px 14px;border:0;border-radius:9px;background:#fff;color:#0f172a;font-weight:700;cursor:pointer">Conectar</button>
      </div>`;
    document.body.appendChild(panel);

    const input = panel.querySelector('#informtit-api-input');
    const button = panel.querySelector('#informtit-api-save');
    if (apiBase) input.value = apiBase;
    button.addEventListener('click', () => {
      const value = normalizeBase(input.value);
      if (!/^https?:\/\//i.test(value)) {
        input.setCustomValidity('Ingrese una URL http o https válida.');
        input.reportValidity();
        return;
      }
      try { window.localStorage.setItem(storageKey, value); } catch (_) {}
      window.location.reload();
    });
  }

  window.informtitSetApiBase = (value) => {
    const normalized = normalizeBase(value);
    try { window.localStorage.setItem(storageKey, normalized); } catch (_) {}
    window.location.reload();
  };

  window.addEventListener('DOMContentLoaded', () => {
    observer.observe(document.documentElement, { childList: true, subtree: true });
    rewriteElement(document.documentElement);

    const footer = document.querySelector('.sidebar-footer span:last-child');
    if (footer && isGitHubPages) footer.textContent = apiBase ? 'Informtit web conectado' : 'Informtit web';

    if (isGitHubPages && !apiBase) showConnectionPanel();
  });
})();
