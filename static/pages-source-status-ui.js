(() => {
  'use strict';

  if (!/(^|\.)github\.io$/i.test(window.location.hostname)) return;
  if (!window.InformtitPagesStability) return;

  const cache = new Map();
  const TTL = 20000;
  const clean = value => String(value ?? '').replace(/\u00a0/g, ' ').trim().replace(/\s+/g, ' ');

  function activeReport() { return window.state?.activeReport || null; }
  function reportKey(report) { return `${Number(report?.id || 0)}:${clean(report?.periodoId || report?.firebase_period_id || report?.period_id)}`; }

  function ensureBanner() {
    const tabs = document.getElementById('report-tabs');
    if (!tabs) return null;
    let banner = document.getElementById('institutional-source-status');
    if (!banner) {
      banner = document.createElement('div');
      banner.id = 'institutional-source-status';
      banner.className = 'institutional-source-status';
      tabs.insertAdjacentElement('beforebegin', banner);
    }
    return banner;
  }

  function render(health) {
    const banner = ensureBanner();
    if (!banner) return;
    const errors = Array.isArray(health?.errors) ? health.errors : [];
    if (!errors.length) {
      banner.hidden = true;
      banner.className = 'institutional-source-status';
      banner.innerHTML = '';
      return;
    }
    banner.hidden = false;
    banner.className = 'institutional-source-status is-error';
    banner.innerHTML = `<strong>Error de fuente</strong><span>${errors.map(item => `${clean(item.source)}: ${clean(item.error)}`).join(' · ')}</span><button type="button" class="button secondary small" id="retry-source-health">Reintentar</button>`;
    banner.querySelector('#retry-source-health')?.addEventListener('click', () => void checkSources(true));
  }

  async function checkSources(force = false) {
    const report = activeReport();
    const banner = ensureBanner();
    if (!banner) return;
    if (!report?.id) { banner.hidden = true; return; }
    const key = reportKey(report);
    const cached = cache.get(key);
    if (!force && cached && Date.now() - cached.at < TTL) { render(cached.health); return; }
    banner.hidden = false;
    banner.className = 'institutional-source-status is-checking';
    banner.innerHTML = '<strong>Fuentes institucionales</strong><span>Verificando…</span>';
    try {
      const health = await window.InformtitPagesStability.sourceHealth(report);
      cache.set(key, { at: Date.now(), health });
      if (activeReport()?.id !== report.id) return;
      render(health);
    } catch (error) {
      render({ errors: [{ source: 'Google Sheets', error: clean(error?.message || error) }] });
    }
  }

  function injectStyles() {
    if (document.getElementById('institutional-source-status-style')) return;
    const style = document.createElement('style');
    style.id = 'institutional-source-status-style';
    style.textContent = `
      .institutional-source-status{display:flex;align-items:center;gap:8px;margin:0 0 8px;padding:8px 10px;border:1px solid #dfe5eb;border-radius:9px;background:#fff;font-size:11px}.institutional-source-status strong{font-size:11px}.institutional-source-status span{flex:1;color:#65758a}.institutional-source-status.is-checking{background:#f8fafc}.institutional-source-status.is-error{background:#fff1f1;border-color:#e0a5a5;color:#8f2d2d}.institutional-source-status.is-error span{color:#8f2d2d}@media(max-width:620px){.institutional-source-status{align-items:flex-start;flex-wrap:wrap}.institutional-source-status span{flex-basis:100%}}
    `;
    document.head.appendChild(style);
  }

  injectStyles();
  document.addEventListener('informtit:period-changed', () => setTimeout(() => void checkSources(true), 150));
  document.addEventListener('click', event => {
    if (event.target.closest?.('#refresh-btn')) setTimeout(() => void checkSources(true), 250);
    if (event.target.closest?.('[data-svd-open-report],[data-tab]')) setTimeout(() => void checkSources(false), 250);
  });
  document.addEventListener('DOMContentLoaded', () => setTimeout(() => void checkSources(false), 450), { once: true });
  setTimeout(() => void checkSources(false), 700);
})();