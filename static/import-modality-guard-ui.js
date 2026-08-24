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

  function setText(node, value) {
    if (node && node.textContent !== value) node.textContent = value;
  }

  function setHtml(node, value) {
    if (node && node.innerHTML !== value) node.innerHTML = value;
  }

  function setStyle(node, property, value) {
    if (node && node.style[property] !== value) node.style[property] = value;
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
      if (button.disabled !== invalid) button.disabled = invalid;
      setText(
        button,
        invalid ? 'Corrija la clasificación antes de importar' : 'Importar Presencial + Online'
      );
    }

    if (note) {
      if (invalid) {
        const missing = [
          presencial <= 0 ? 'Presencial' : '',
          online <= 0 ? 'Online' : '',
        ].filter(Boolean).join(' y ');
        setHtml(
          note,
          `<strong>Error de clasificación:</strong> la fuente presenta 0 registros ${missing}. Informtit no permitirá guardar la importación hasta que ambas modalidades sean reconocidas.`
        );
        setStyle(note, 'background', '#fff0ee');
        setStyle(note, 'color', '#91382f');
      } else {
        setHtml(
          note,
          `<strong>Clasificación verificada:</strong> ${presencial} estudiantes Presencial + ${online} estudiantes Online = ${presencial + online} registros que se guardarán en el mismo período.`
        );
        setStyle(note, 'background', '#edf8f1');
        setStyle(note, 'color', '#245f43');
      }
    }
  }

  let queued = false;
  function scheduleRefresh() {
    if (queued) return;
    queued = true;
    queueMicrotask(() => {
      queued = false;
      refresh();
    });
  }

  const observer = new MutationObserver(scheduleRefresh);
  observer.observe(document.body, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ['hidden', 'disabled'],
  });

  document.addEventListener('change', event => {
    if (event.target?.id === 'active-roster-file') scheduleRefresh();
  });

  refresh();
})();
