(() => {
  'use strict';

  if (!/(^|\.)github\.io$/i.test(window.location.hostname)) return;

  const AUTO_COLUMNS = [
    'fecha ejecutada',
    'estado',
    '% cumplimiento',
    'cumplimiento',
    'evidencia',
    'observación',
    'observacion',
  ];

  function clean(value) {
    return String(value ?? '').trim().replace(/\s+/g, ' ');
  }

  function fold(value) {
    return clean(value)
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .toLowerCase();
  }

  function isAutomaticColumn(text) {
    const normalized = fold(text);
    return AUTO_COLUMNS.some(label => normalized === fold(label));
  }

  function removeAutomaticColumns(table) {
    const headerCells = [...table.querySelectorAll('thead th')];
    const indexes = headerCells
      .map((cell, index) => ({ index, text: clean(cell.textContent) }))
      .filter(item => isAutomaticColumn(item.text))
      .map(item => item.index)
      .sort((a, b) => b - a);

    if (!indexes.length) return;
    table.querySelectorAll('tr').forEach(row => {
      const cells = [...row.children];
      indexes.forEach(index => cells[index]?.remove());
    });
  }

  function ensureAutoNote(card) {
    if (card.querySelector('.schedule-auto-completion-note')) return;
    const head = card.querySelector('.panel-head');
    if (!head) return;
    const note = document.createElement('div');
    note.className = 'schedule-auto-completion-note';
    note.innerHTML = '<strong>Ejecución automática:</strong> todas las actividades se registran como Cumplidas al 100 %. La fecha ejecutada corresponde automáticamente a la fecha fin.';
    head.insertAdjacentElement('afterend', note);
  }

  function improvePasteHelp(card) {
    const type = card.dataset.scheduleCard;
    const textarea = card.querySelector(`[data-schedule-paste="${type}"]`);
    if (!textarea) return;
    textarea.rows = Math.max(Number(textarea.rows || 0), type === 'thesis' ? 8 : 5);
    textarea.placeholder = type === 'thesis'
      ? 'Pegue el cronograma completo. Puede incluir encabezados como “### Fase 1: Inicio y planificación” y tablas Markdown con Actividad, Fecha inicio y Fecha fin.'
      : 'Pegue la tabla completa con Actividad, Fecha inicio y Fecha fin. Informtit marcará automáticamente cada actividad como Cumplida al 100 %.';
  }

  function simplifyScheduleCard(card) {
    if (!(card instanceof Element)) return;
    ensureAutoNote(card);
    improvePasteHelp(card);
    card.querySelectorAll('table.schedule-table').forEach(removeAutomaticColumns);

    card.querySelectorAll('[name="executed_date"], [name="execution_status"], [name="compliance_percentage"], [name="evidence"], [name="observation"]').forEach(control => {
      const cell = control.closest('td, th, label, .form-field');
      if (cell) cell.remove();
      else control.remove();
    });
  }

  function apply(root = document) {
    root.querySelectorAll?.('[data-schedule-card]').forEach(simplifyScheduleCard);
  }

  const style = document.createElement('style');
  style.textContent = `
    .schedule-auto-completion-note {
      margin: 0 0 14px;
      padding: 10px 12px;
      border-radius: 10px;
      background: #eef7f1;
      color: #285f3e;
      font-size: 12px;
      line-height: 1.45;
    }
    .schedule-auto-completion-note strong { font-weight: 800; }
    [data-schedule-card="thesis"] .phase-input { min-width: 220px; }
  `;
  document.head.appendChild(style);

  const observer = new MutationObserver(mutations => {
    let relevant = false;
    for (const mutation of mutations) {
      if (mutation.type !== 'childList' || !mutation.addedNodes.length) continue;
      relevant = true;
      break;
    }
    if (!relevant) return;
    queueMicrotask(() => apply(document));
  });

  observer.observe(document.body, { childList: true, subtree: true });
  apply(document);
})();
