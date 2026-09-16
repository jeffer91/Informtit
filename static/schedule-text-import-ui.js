((root) => {
  'use strict';

  const VERSION = '1.0.1';
  const MARKER = 'SCHEDULE_TEXT_IMPORT_V1';
  const clean = value => String(value ?? '').replace(/\u00a0/g, ' ').trim().replace(/\s+/g, ' ');
  const fold = value => clean(value).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toUpperCase();
  const esc = value => clean(value).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot',"'":'&#39;'}[char]));

  function normalizeDate(value) {
    const text = clean(value);
    if (!text) return '';
    let year, month, day;
    let match = text.match(/^(\d{4})[-\/.](\d{1,2})[-\/.](\d{1,2})$/);
    if (match) {
      year = Number(match[1]); month = Number(match[2]); day = Number(match[3]);
    } else {
      match = text.match(/^(\d{1,2})[-\/.](\d{1,2})[-\/.](\d{4})$/);
      if (!match) return '';
      day = Number(match[1]); month = Number(match[2]); year = Number(match[3]);
    }
    const date = new Date(Date.UTC(year, month - 1, day));
    if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) return '';
    return `${String(year).padStart(4,'0')}-${String(month).padStart(2,'0')}-${String(day).padStart(2,'0')}`;
  }

  function cellsFromLine(line) {
    const raw = String(line ?? '').trim();
    if (!raw) return [];
    if (raw.includes('|')) return raw.split('|').map(clean).filter(Boolean);
    if (raw.includes('\t')) return raw.split('\t').map(clean).filter(Boolean);
    const dateMatches = [...raw.matchAll(/\b\d{1,4}[\/-]\d{1,2}[\/-]\d{1,4}\b/g)];
    if (dateMatches.length >= 2) {
      const first = dateMatches[0];
      const second = dateMatches[1];
      return [clean(raw.slice(0, first.index)), clean(first[0]), clean(second[0])].filter(Boolean);
    }
    return [clean(raw)];
  }

  function isSeparator(cells) {
    return cells.length && cells.every(cell => /^:?-{2,}:?$/.test(clean(cell)));
  }

  function isHeader(cells) {
    if (!cells.length) return false;
    const text = fold(cells.join(' '));
    return text.includes('ACTIVIDAD') && text.includes('FECHA');
  }

  function phaseFromLine(line) {
    const raw = clean(String(line ?? '').replace(/^#{1,6}\s*/, ''));
    const match = raw.match(/^(FASE\s+\d+\s*:\s*.+)$/i);
    return match ? clean(match[1]) : '';
  }

  function parseScheduleText(text, type = 'complexive') {
    const thesis = type === 'thesis';
    const entries = [];
    const errors = [];
    let phase = '';
    String(text ?? '').split(/\r?\n/).forEach((line, index) => {
      const detectedPhase = thesis ? phaseFromLine(line) : '';
      if (detectedPhase) { phase = detectedPhase; return; }
      const cells = cellsFromLine(line);
      if (cells.length < 3 || isSeparator(cells) || isHeader(cells)) return;
      const activity = clean(cells[0]);
      const startDate = normalizeDate(cells[1]);
      const endDate = normalizeDate(cells[2]);
      if (!activity || /^OCTUBRE\s+\d{4}/i.test(activity)) return;
      if (!startDate || !endDate) {
        errors.push(`Línea ${index + 1}: fecha inválida en «${activity}».`);
        return;
      }
      if (endDate < startDate) {
        errors.push(`Línea ${index + 1}: la fecha fin es anterior a la fecha inicio en «${activity}».`);
        return;
      }
      entries.push({
        phase: thesis ? phase : '',
        activity,
        start_date: startDate,
        end_date: endDate,
        notes: thesis ? phase : '',
      });
    });
    if (!entries.length && !errors.length) errors.push('No se reconocieron actividades con fecha inicio y fecha fin.');
    if (thesis && entries.some(row => !row.phase)) errors.push('Hay actividades de Trabajo de Titulación sin una fase identificada.');
    return { entries, errors, type };
  }

  root.InformtitScheduleTextImport = Object.freeze({ VERSION, MARKER, normalizeDate, parseScheduleText });

  if (typeof document === 'undefined' || typeof location === 'undefined') return;
  if (!/(^|\.)github\.io$/i.test(location.hostname)) return;

  function rowHtml(item, thesis) {
    return `<tr>
      ${thesis ? `<td><input class="table-input" name="phase" value="${esc(item.phase || '')}" placeholder="Fase"></td>` : ''}
      <td><input class="table-input" name="activity" value="${esc(item.activity || '')}" placeholder="Actividad"></td>
      <td><input type="date" class="table-input date-input" name="start_date" value="${esc(item.start_date || '')}"></td>
      <td><input type="date" class="table-input date-input" name="end_date" value="${esc(item.end_date || '')}"></td>
      <td><button class="button danger small" type="button" data-remove-schedule>Eliminar</button></td>
    </tr>`;
  }

  function setMessage(card, message, kind = '') {
    const node = card.querySelector('[data-schedule-text-status]');
    if (!node) return;
    node.textContent = clean(message);
    node.className = `schedule-text-status${kind ? ` is-${kind}` : ''}`;
  }

  function validateCard(card) {
    const problems = [];
    [...card.querySelectorAll('tbody tr')].forEach((row, index) => {
      row.classList.remove('schedule-row-error');
      const activity = clean(row.querySelector('[name="activity"]')?.value);
      const startDate = normalizeDate(row.querySelector('[name="start_date"]')?.value);
      const endDate = normalizeDate(row.querySelector('[name="end_date"]')?.value);
      const thesis = card.dataset.pagesSchedule === 'thesis';
      const phase = thesis ? clean(row.querySelector('[name="phase"]')?.value) : '';
      if (!activity || !startDate || !endDate || (thesis && !phase) || (startDate && endDate && endDate < startDate)) {
        row.classList.add('schedule-row-error');
        problems.push(index + 1);
      }
    });
    return problems;
  }

  function bindRemove(card) {
    card.querySelectorAll('[data-remove-schedule]').forEach(button => {
      if (button.dataset.scheduleTextRemoveBound) return;
      button.dataset.scheduleTextRemoveBound = '1';
      button.addEventListener('click', () => {
        setTimeout(() => setMessage(card, `${card.querySelectorAll('tbody tr').length} actividades en edición.`, 'ready'), 0);
      });
    });
  }

  function enhance(card) {
    if (!card || card.dataset.scheduleTextBound === '1') return;
    card.dataset.scheduleTextBound = '1';
    const type = card.dataset.pagesSchedule === 'thesis' ? 'thesis' : 'complexive';
    const thesis = type === 'thesis';
    const tableWrap = card.querySelector('.student-table-wrap');
    if (!tableWrap) return;
    const importer = document.createElement('details');
    importer.className = 'schedule-text-import';
    importer.innerHTML = `
      <summary>Importar cronograma desde texto</summary>
      <div class="schedule-text-import-body">
        <textarea rows="5" data-schedule-text placeholder="Pegue aquí el cronograma con Actividad | Fecha inicio | Fecha fin${thesis ? ' y encabezados Fase 1, Fase 2…' : ''}."></textarea>
        <div class="schedule-text-actions">
          <button type="button" class="button secondary small" data-parse-schedule-text>Cargar texto en la tabla</button>
          <span class="schedule-text-status" data-schedule-text-status>El texto se valida antes de reemplazar la tabla.</span>
        </div>
      </div>`;
    tableWrap.insertAdjacentElement('beforebegin', importer);

    importer.querySelector('[data-parse-schedule-text]')?.addEventListener('click', () => {
      const source = importer.querySelector('[data-schedule-text]')?.value || '';
      const parsed = parseScheduleText(source, type);
      if (parsed.errors.length) {
        setMessage(card, parsed.errors.slice(0, 3).join(' '), 'error');
        return;
      }
      const tbody = card.querySelector('tbody');
      if (!tbody) return;
      tbody.innerHTML = parsed.entries.map(item => rowHtml(item, thesis)).join('');
      bindRemove(card);
      setMessage(card, `${parsed.entries.length} actividades cargadas y validadas. Revise la tabla y pulse Guardar cronograma.`, 'ready');
    });

    card.querySelector('[data-save-schedule]')?.addEventListener('click', event => {
      const problems = validateCard(card);
      if (!problems.length) {
        setMessage(card, `${card.querySelectorAll('tbody tr').length} actividades listas para guardar.`, 'ready');
        return;
      }
      event.preventDefault();
      event.stopImmediatePropagation();
      setMessage(card, `No se guardó. Revise las filas ${problems.slice(0, 10).join(', ')}${problems.length > 10 ? '…' : ''}.`, 'error');
    }, true);

    bindRemove(card);
  }

  function enhanceAll() {
    document.querySelectorAll('[data-pages-schedule]').forEach(enhance);
  }

  function injectStyles() {
    if (document.getElementById('schedule-text-import-style')) return;
    const style = document.createElement('style');
    style.id = 'schedule-text-import-style';
    style.textContent = `
      .schedule-text-import{margin:10px 0 12px;border:1px solid #dfe7ee;border-radius:10px;background:#f8fafc}.schedule-text-import summary{cursor:pointer;padding:9px 11px;font-size:12px;font-weight:700;color:#284f73}.schedule-text-import-body{display:grid;gap:8px;padding:0 10px 10px}.schedule-text-import textarea{width:100%;min-height:92px;resize:vertical;border:1px solid #cfd9e4;border-radius:8px;padding:9px 10px;font:inherit;background:#fff}.schedule-text-actions{display:flex;align-items:center;gap:10px;flex-wrap:wrap}.schedule-text-status{font-size:11px;color:#64748b}.schedule-text-status.is-ready{color:#24643d}.schedule-text-status.is-error{color:#a33a32}.schedule-row-error{outline:2px solid #e1a19b;outline-offset:-2px;background:#fff5f4}@media(max-width:620px){.schedule-text-actions{align-items:flex-start;flex-direction:column}}
    `;
    document.head.appendChild(style);
  }

  injectStyles();
  enhanceAll();
  if (typeof MutationObserver !== 'undefined' && document.body) {
    new MutationObserver(enhanceAll).observe(document.body, { childList: true, subtree: true });
  }
})(typeof window !== 'undefined' ? window : globalThis);