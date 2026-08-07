(() => {
  function setImportOpen(tab, open) {
    const panel = tab?.querySelector('[data-nucleus-import-panel]');
    const toggle = tab?.querySelector('[data-toggle-nucleus-import]');
    if (!panel || !toggle) return false;

    panel.hidden = !open;
    if (open) panel.removeAttribute('hidden');
    else panel.setAttribute('hidden', '');

    toggle.textContent = open ? 'Cerrar carga' : '+ Cargar núcleo';
    toggle.setAttribute('aria-expanded', open ? 'true' : 'false');

    if (open) {
      requestAnimationFrame(() => {
        panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
        panel.querySelector('textarea[name="grades_text"]')?.focus({ preventScroll: true });
      });
    }
    return true;
  }

  document.addEventListener('click', event => {
    const toggle = event.target.closest('#tab-nuclei [data-toggle-nucleus-import]');
    if (toggle) {
      const tab = toggle.closest('#tab-nuclei');
      const panel = tab?.querySelector('[data-nucleus-import-panel]');
      if (!panel) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      setImportOpen(tab, panel.hasAttribute('hidden') || panel.hidden);
      return;
    }

    const cancel = event.target.closest('#tab-nuclei [data-cancel-nucleus-import]');
    if (cancel) {
      const tab = cancel.closest('#tab-nuclei');
      event.preventDefault();
      event.stopImmediatePropagation();
      setImportOpen(tab, false);
    }
  }, true);
})();
