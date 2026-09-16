(() => {
  'use strict';

  if (typeof window === 'undefined' || !/(^|\.)github\.io$/i.test(window.location.hostname)) return;

  const VERSION = '1.0.0';
  const MARKER = 'PERIOD_STATUS_COLORS_V1';

  function injectStyles() {
    if (document.getElementById('period-status-colors-style')) return;
    const style = document.createElement('style');
    style.id = 'period-status-colors-style';
    style.textContent = `
      .shealth-card.ok{border-color:#a8d9b6!important;background:#eef9f1!important}.shealth-card.ok>div>span{background:#dff2e5;color:#24643d;border-radius:999px;padding:3px 7px}.shealth-card.ok h3{color:#173f28}
      .shealth-card.warn{border-color:#e5c665!important;background:#fff8dc!important}.shealth-card.warn>div>span{background:#ffe7a0;color:#805900;border-radius:999px;padding:3px 7px}.shealth-card.warn h3{color:#5f4800}
      .shealth-card.empty{border-color:#e6a4a4!important;background:#fff1f1!important}.shealth-card.empty>div>span{background:#f7d9d9;color:#9a2f2f;border-radius:999px;padding:3px 7px}.shealth-card.empty h3{color:#6f2424}
      .shealth-card.error{border-color:#d87878!important;background:#fde7e7!important}.shealth-card.error>div>span{background:#efbcbc;color:#842020;border-radius:999px;padding:3px 7px}.shealth-card.error h3{color:#681b1b}
      .shealth-overview.status-all-ok{border-color:#a8d9b6!important;background:#eef9f1!important}.shealth-overview.status-review{border-color:#e5c665!important;background:#fff8dc!important}.shealth-overview.status-error{border-color:#d87878!important;background:#fde7e7!important}
    `;
    document.head.appendChild(style);
  }

  function paintOverview() {
    const overview = document.querySelector('.shealth-overview');
    const cards = [...document.querySelectorAll('.shealth-grid .shealth-card')];
    if (!overview || !cards.length) return;
    overview.classList.remove('status-all-ok','status-review','status-error');
    const hasSourceError = cards.some(card => card.classList.contains('error'));
    const allOk = cards.every(card => card.classList.contains('ok'));
    if (hasSourceError) overview.classList.add('status-error');
    else if (allOk) overview.classList.add('status-all-ok');
    else overview.classList.add('status-review');
  }

  function refresh() {
    injectStyles();
    paintOverview();
  }

  injectStyles();
  refresh();
  const observer = new MutationObserver(refresh);
  observer.observe(document.documentElement, { childList:true, subtree:true });
  document.addEventListener('click', event => {
    if (event.target.closest?.('[data-tab="summary"]')) setTimeout(refresh, 0);
  }, true);

  window.InformtitPeriodStatusColors = Object.freeze({ VERSION, MARKER });
})();