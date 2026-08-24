// Validación visible de la población Presencial + Online antes de confirmar Requisitos.
(function () {
  'use strict';

  function metricValue(label) {
    const cards = [...document.querySelectorAll('#active-import-metrics .metric')];
    const card = cards.find(item => item.querySelector('span')?.textContent.trim() === label);
    const raw = card?.querySelector('strong')?.textContent || '';
    const value = Number(String(raw).replace(/[^0-9.-]/g, ''));
    return Number.isFinite(value) ? value : null;
  }

  function refresh() {
    const dialog = document.getElementById('active-report-import-dialog');
    const confirmStep = document.getElementById('active-import-confirm-step');
    if (!dialog || !confirmStep || confirmStep.hidden) return;

    const presencial = metricValue('Presencial');
    const online = metricValue('Online');
    if (presencial === null || online === null) return;

    const button = document.getElementById('commit-active-roster');
    const note = document.getElementById('active-modality-note');
    const invalid = presencial <= 0 || online <= 0;

    if (button) {
      button.disabled = invalid;
      button.textContent = invalid
        ? 'Corrija la clasificación antes de importar'
        : 'Importar Presencial + Online';
    }

    if (note) {
      if (invalid) {
        const missing = [
          presencial <= 0 ? 'Presencial' : '',
          online <= 0 ? 'Online' : '',
        ].filter(Boolean).join(' y ');
        note.innerHTML = `<strong>Error de clasificación:</strong> la fuente presenta 0 registros ${missing}. Informtit no permitirá guardar la importación hasta que ambas modalidades sean reconocidas.`;
        note.style.background = '#fff0ee';
        note.style.color = '#91382f';
      } else {
        note.innerHTML = `<strong>Clasificación verificada:</strong> ${presencial} estudiantes Presencial + ${online} estudiantes Online = ${presencial + online} registros que se guardarán en el mismo período.`;
        note.style.background = '#edf8f1';
        note.style.color = '#245f43';
      }
    }
  }

  const observer = new MutationObserver(() => queueMicrotask(refresh));
  observer.observe(document.body, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ['hidden', 'disabled'],
  });

  document.addEventListener('change', event => {
    if (event.target?.id === 'active-roster-file') queueMicrotask(refresh);
  });

  refresh();
})();
