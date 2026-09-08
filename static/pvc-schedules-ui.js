(() => {
  'use strict';

  if (!/(^|\.)github\.io$/i.test(window.location.hostname)) return;

  const TEMPLATE_PERIOD = 'NOVIEMBRE 2025 MAYO 2026';
  let applying = false;
  let renderToken = 0;

  const DEFAULT_GROUPS = [
    {
      name: 'Superiores',
      items: [
        ['Inducción general al proceso de titulación', '09/04/2026', '09/04/2026'],
        ['Finalización de clases del período académico', '24/04/2026', '24/04/2026'],
        ['Clase de metodología 1', '27/04/2026', '27/04/2026'],
        ['Clase de metodología 2', '28/04/2026', '28/04/2026'],
        ['Clase de metodología 3', '29/04/2026', '29/04/2026'],
        ['Entrega de la pregunta de investigación', '03/05/2026', '03/05/2026'],
        ['Evaluación de la pregunta de investigación', '04/05/2026', '05/05/2026'],
        ['Clase de refuerzo académico por carrera 1', '04/05/2026', '04/05/2026'],
        ['Clase de refuerzo académico por carrera 2', '07/05/2026', '07/05/2026'],
        ['Verificación del cumplimiento de requisitos de titulación', '08/05/2026', '08/05/2026'],
        ['Entrega del artículo académico completo', '10/05/2026', '10/05/2026'],
        ['Evaluación institucional y revisión antiplagio del artículo académico', '11/05/2026', '13/05/2026'],
        ['Defensa oral del artículo académico', '18/05/2026', '20/05/2026'],
        ['Tutoría extraordinaria para supletorio', '18/05/2026', '20/05/2026'],
        ['Entrega del artículo académico supletorio', '24/05/2026', '24/05/2026'],
        ['Evaluación institucional y revisión antiplagio del artículo académico supletorio', '25/05/2026', '27/05/2026'],
        ['Defensa oral supletoria del artículo académico', '29/05/2026', '29/05/2026'],
      ],
    },
    {
      name: 'Universitarias 2',
      items: [
        ['Inducción general al proceso de titulación', '07/05/2026', '07/05/2026'],
        ['Finalización de Clases', '08/05/2026', '08/05/2026'],
        ['Metodología 1', '11/05/2026', '11/05/2026'],
        ['Metodología 2', '12/05/2026', '12/05/2026'],
        ['Metodología 3', '13/05/2026', '13/05/2026'],
        ['Entrega de la Interrogante de Investigación', '17/05/2026', '17/05/2026'],
        ['Evaluación de la Interrogante de Investigación', '18/05/2026', '19/05/2026'],
        ['Clase de refuerzo por carreras 1', '20/05/2026', '20/05/2026'],
        ['Clase de refuerzo por carreras 2', '27/05/2026', '27/05/2026'],
        ['Cumplimiento de requisitos', '28/05/2026', '28/05/2026'],
        ['Entrega del artículo académico completo', '31/05/2026', '31/05/2026'],
        ['Evaluación final institucional con revisión antiplagio', '01/06/2026', '03/06/2026'],
        ['Defensa oral', '08/06/2026', '10/06/2026'],
        ['Tutoría extra supletorio', '08/06/2026', '10/06/2026'],
        ['Entrega del artículo académico supletorio', '21/06/2026', '21/06/2026'],
        ['Rúbrica institucional y plagio supletorio', '22/06/2026', '24/06/2026'],
        ['Defensa oral supletorio', '25/06/2026', '25/06/2026'],
      ],
    },
    {
      name: 'Universitarias 1',
      items: [
        ['Inducción general al proceso de titulación', '20/05/2026', '20/05/2026'],
        ['Finalización de Clases', '22/05/2026', '22/05/2026'],
        ['Metodología 1', '26/05/2026', '26/05/2026'],
        ['Metodología 2', '27/05/2026', '27/05/2026'],
        ['Metodología 3', '28/05/2026', '28/05/2026'],
        ['Entrega de la Interrogante de Investigación', '31/05/2026', '31/05/2026'],
        ['Evaluación de la Interrogante de Investigación', '01/06/2026', '02/06/2026'],
        ['Clase de refuerzo por carreras 1', '03/06/2026', '03/06/2026'],
        ['Clase de refuerzo por carreras 2', '10/06/2026', '10/06/2026'],
        ['Cumplimiento de requisitos', '11/06/2026', '11/06/2026'],
        ['Entrega del artículo académico completo', '14/06/2026', '14/06/2026'],
        ['Evaluación final institucional con revisión antiplagio', '15/06/2026', '17/06/2026'],
        ['Defensa oral', '22/06/2026', '24/06/2026'],
        ['Tutoría extra supletorio', '22/06/2026', '24/06/2026'],
        ['Entrega del artículo académico supletorio', '28/06/2026', '28/06/2026'],
        ['Rúbrica institucional y plagio supletorio', '29/06/2026', '01/07/2026'],
        ['Defensa oral supletorio', '02/07/2026', '02/07/2026'],
      ],
    },
  ];

  function esc(value = '') {
    return String(value).replace(/[&<>"']/g, char => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[char]));
  }

  function clean(value = '') {
    return String(value ?? '').trim().replace(/\s+/g, ' ');
  }

  function fold(value = '') {
    return clean(value)
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .toUpperCase();
  }

  function isPvc() {
    const report = window.state?.activeReport;
    const project = report?.project_summary || {};
    return String(report?.report_type || project?.report_type || '').toLowerCase() === 'pvc';
  }

  function matchesTemplatePeriod() {
    const period = fold(window.state?.activeReport?.period || '');
    return period.includes('NOVIEMBRE 2025') && period.includes('MAYO 2026');
  }

  function emptyGroup(index = 1) {
    return { name: `Cronograma ${index}`, items: [] };
  }

  function templateGroups() {
    return DEFAULT_GROUPS.map(group => ({
      name: group.name,
      items: group.items.map(([activity, start_date, end_date]) => ({ activity, start_date, end_date })),
    }));
  }

  function groupStoredEntries(entries) {
    const groups = new Map();
    (Array.isArray(entries) ? entries : []).forEach(item => {
      const name = clean(item?.phase) || 'Cronograma de Artículo Académico';
      if (!groups.has(name)) groups.set(name, []);
      groups.get(name).push({
        activity: clean(item?.activity),
        start_date: clean(item?.start_date),
        end_date: clean(item?.end_date),
      });
    });
    return [...groups.entries()].map(([name, items]) => ({ name, items }));
  }

  function rowMarkup(item = {}) {
    return `
      <tr>
        <td><input class="pvc-schedule-input" name="activity" value="${esc(item.activity || '')}" placeholder="Actividad"></td>
        <td><input class="pvc-schedule-input date-input" name="start_date" value="${esc(item.start_date || '')}" placeholder="dd/mm/aaaa"></td>
        <td><input class="pvc-schedule-input date-input" name="end_date" value="${esc(item.end_date || '')}" placeholder="dd/mm/aaaa"></td>
        <td><button type="button" class="pvc-icon-danger" data-pvc-remove-row aria-label="Eliminar actividad">×</button></td>
      </tr>`;
  }

  function groupMarkup(group, index) {
    const items = Array.isArray(group.items) ? group.items : [];
    return `
      <section class="pvc-calendar" data-pvc-calendar>
        <div class="pvc-calendar-head">
          <div class="pvc-calendar-title-wrap">
            <span class="pvc-calendar-index">${index + 1}</span>
            <input class="pvc-calendar-title" data-pvc-calendar-title value="${esc(group.name || `Cronograma ${index + 1}`)}" aria-label="Nombre del cronograma">
          </div>
          <div class="pvc-calendar-actions">
            <button type="button" class="button secondary small" data-pvc-add-row>Agregar actividad</button>
            <button type="button" class="button danger small" data-pvc-remove-calendar>Eliminar cronograma</button>
          </div>
        </div>
        <div class="pvc-calendar-import">
          <label class="file-button">Subir este cronograma
            <input type="file" data-pvc-calendar-file accept=".xls,.html,.htm,.csv,.txt">
          </label>
          <textarea data-pvc-calendar-paste rows="3" placeholder="Pegue aquí la tabla con Actividad, Fecha inicio y Fecha fin."></textarea>
          <button type="button" class="button secondary small" data-pvc-parse-calendar>Procesar tabla</button>
        </div>
        <div class="student-table-wrap">
          <table class="student-table pvc-calendar-table">
            <thead><tr><th>Actividad</th><th>Fecha inicio</th><th>Fecha fin</th><th></th></tr></thead>
            <tbody>${items.length ? items.map(rowMarkup).join('') : rowMarkup()}</tbody>
          </table>
        </div>
      </section>`;
  }

  function parseHtmlTable(text) {
    if (!/<table[\s>]/i.test(text)) return [];
    const documentHtml = new DOMParser().parseFromString(text, 'text/html');
    const rows = [...documentHtml.querySelectorAll('table tr')].map(row =>
      [...row.querySelectorAll('th,td')].map(cell => clean(cell.textContent))
    );
    return normalizeTableRows(rows);
  }

  function splitPlainLine(line) {
    const trimmed = line.trim();
    if (!trimmed) return [];
    if (trimmed.includes('|')) {
      return trimmed.replace(/^\|/, '').replace(/\|$/, '').split('|').map(clean);
    }
    if (trimmed.includes('\t')) return trimmed.split('\t').map(clean);
    if (trimmed.includes(';')) return trimmed.split(';').map(clean);
    return [];
  }

  function normalizeTableRows(rows) {
    const result = [];
    for (const cells of rows) {
      if (!Array.isArray(cells) || cells.length < 3) continue;
      const first = fold(cells[0]);
      const second = fold(cells[1]);
      if (!first || /^[-: ]+$/.test(cells.join(''))) continue;
      if (first.includes('ACTIVIDAD') && second.includes('FECHA')) continue;
      if (first.includes('NOVIEMBRE') && second === '') continue;
      const activity = clean(cells[0]);
      const start_date = clean(cells[1]);
      const end_date = clean(cells[2]);
      if (!activity || !start_date || !end_date) continue;
      result.push({ activity, start_date, end_date });
    }
    return result;
  }

  function parseTableText(text) {
    const html = parseHtmlTable(text);
    if (html.length) return html;
    const rows = String(text || '').split(/\r?\n/).map(splitPlainLine).filter(cells => cells.length);
    return normalizeTableRows(rows);
  }

  async function readFileText(file) {
    return await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ''));
      reader.onerror = () => reject(reader.error || new Error('No se pudo leer el archivo.'));
      reader.readAsText(file);
    });
  }

  function collectGroups(root) {
    const names = new Set();
    const groups = [];
    root.querySelectorAll('[data-pvc-calendar]').forEach((calendar, index) => {
      const name = clean(calendar.querySelector('[data-pvc-calendar-title]')?.value) || `Cronograma ${index + 1}`;
      const normalizedName = fold(name);
      if (names.has(normalizedName)) throw new Error(`El nombre “${name}” está repetido.`);
      names.add(normalizedName);
      const items = [...calendar.querySelectorAll('tbody tr')].map(row => ({
        activity: clean(row.querySelector('[name="activity"]')?.value),
        start_date: clean(row.querySelector('[name="start_date"]')?.value),
        end_date: clean(row.querySelector('[name="end_date"]')?.value),
      })).filter(item => item.activity || item.start_date || item.end_date);
      for (const item of items) {
        if (!item.activity || !item.start_date || !item.end_date) {
          throw new Error(`Complete actividad, fecha inicio y fecha fin en “${name}”.`);
        }
      }
      groups.push({ name, items });
    });
    return groups;
  }

  function flattenGroups(groups) {
    return groups.flatMap(group => group.items.map(item => ({
      phase: group.name,
      activity: item.activity,
      start_date: item.start_date,
      end_date: item.end_date,
    })));
  }

  function bindRoot(root, reportId) {
    root.addEventListener('click', async event => {
      const removeRow = event.target.closest('[data-pvc-remove-row]');
      if (removeRow) {
        const tbody = removeRow.closest('tbody');
        removeRow.closest('tr')?.remove();
        if (tbody && !tbody.querySelector('tr')) tbody.insertAdjacentHTML('beforeend', rowMarkup());
        return;
      }

      const addRow = event.target.closest('[data-pvc-add-row]');
      if (addRow) {
        addRow.closest('[data-pvc-calendar]')?.querySelector('tbody')?.insertAdjacentHTML('beforeend', rowMarkup());
        return;
      }

      const removeCalendar = event.target.closest('[data-pvc-remove-calendar]');
      if (removeCalendar) {
        const calendars = root.querySelectorAll('[data-pvc-calendar]');
        if (calendars.length <= 1) return toast('Debe existir al menos un cronograma.', true);
        if (confirm('¿Eliminar este cronograma de Artículo Académico?')) removeCalendar.closest('[data-pvc-calendar]')?.remove();
        return;
      }

      if (event.target.closest('[data-pvc-add-calendar]')) {
        const host = root.querySelector('[data-pvc-calendars]');
        const index = host.querySelectorAll('[data-pvc-calendar]').length;
        host.insertAdjacentHTML('beforeend', groupMarkup(emptyGroup(index + 1), index));
        return;
      }

      if (event.target.closest('[data-pvc-load-defaults]')) {
        if (!confirm('Se reemplazará la vista actual por los cronogramas sugeridos para Noviembre 2025 a Mayo 2026.')) return;
        const host = root.querySelector('[data-pvc-calendars]');
        const groups = templateGroups();
        host.innerHTML = groups.map(groupMarkup).join('');
        toast('Cronogramas sugeridos cargados. Revise y pulse Guardar todos.');
        return;
      }

      const parseButton = event.target.closest('[data-pvc-parse-calendar]');
      if (parseButton) {
        const calendar = parseButton.closest('[data-pvc-calendar]');
        const textarea = calendar.querySelector('[data-pvc-calendar-paste]');
        const items = parseTableText(textarea?.value || '');
        if (!items.length) return toast('No se detectaron filas con Actividad, Fecha inicio y Fecha fin.', true);
        calendar.querySelector('tbody').innerHTML = items.map(rowMarkup).join('');
        toast(`${items.length} actividades detectadas.`);
        return;
      }

      const save = event.target.closest('[data-pvc-save-all]');
      if (save) {
        save.disabled = true;
        try {
          const groups = collectGroups(root);
          const entries = flattenGroups(groups);
          const result = await api(`/api/reports/${reportId}/schedules/thesis`, {
            method: 'PUT',
            body: JSON.stringify({ entries }),
          });
          toast(`${groups.length} cronograma(s) · ${result.count ?? entries.length} actividades guardadas.`);
          await renderPvcSchedules(true);
        } catch (error) {
          toast(error.message || String(error), true);
        } finally {
          save.disabled = false;
        }
      }
    });

    root.querySelectorAll('[data-pvc-calendar-file]').forEach(input => {
      input.addEventListener('change', async () => {
        const file = input.files?.[0];
        if (!file) return;
        const calendar = input.closest('[data-pvc-calendar]');
        try {
          const text = await readFileText(file);
          const items = parseTableText(text);
          if (!items.length) throw new Error('No se detectaron filas válidas en el archivo.');
          calendar.querySelector('tbody').innerHTML = items.map(rowMarkup).join('');
          toast(`${items.length} actividades cargadas desde ${file.name}.`);
        } catch (error) {
          toast(error.message || String(error), true);
        } finally {
          input.value = '';
        }
      });
    });
  }

  function injectStyles() {
    if (document.getElementById('pvc-schedules-style')) return;
    const style = document.createElement('style');
    style.id = 'pvc-schedules-style';
    style.textContent = `
      .pvc-schedules-root{display:grid;gap:14px}.pvc-schedules-hero{padding:16px;border:1px solid #dbe4ec;border-radius:12px;background:#fff}.pvc-schedules-hero h2{margin:0 0 5px}.pvc-schedules-hero p{margin:0;color:#5e7184}.pvc-schedules-note{margin-top:10px;padding:9px 11px;border-radius:9px;background:#eef7f1;color:#285f3e;font-size:12px}.pvc-schedules-toolbar{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}.pvc-calendars{display:grid;gap:12px}.pvc-calendar{border:1px solid #dce5ed;border-radius:12px;background:#fff;overflow:hidden}.pvc-calendar-head{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 14px;border-bottom:1px solid #edf1f5}.pvc-calendar-title-wrap{display:flex;align-items:center;gap:9px;min-width:0;flex:1}.pvc-calendar-index{width:26px;height:26px;border-radius:8px;background:#eef4f8;display:grid;place-items:center;font-weight:800;font-size:12px;color:#305b79}.pvc-calendar-title{font:inherit;font-weight:800;font-size:15px;border:0;background:transparent;min-width:180px;max-width:420px;width:100%;padding:4px 2px;color:#10283f}.pvc-calendar-title:focus{outline:2px solid #c7dcef;border-radius:6px}.pvc-calendar-actions{display:flex;gap:7px;flex-wrap:wrap}.pvc-calendar-import{display:grid;grid-template-columns:auto 1fr auto;gap:8px;align-items:start;padding:11px 14px;background:#f8fafc;border-bottom:1px solid #edf1f5}.pvc-calendar-import textarea{min-height:66px;resize:vertical}.pvc-calendar-table th,.pvc-calendar-table td{vertical-align:middle}.pvc-schedule-input{width:100%;min-width:130px;padding:7px 8px;border:1px solid #d5e0e8;border-radius:7px;background:#fff}.pvc-icon-danger{width:28px;height:28px;border:0;border-radius:7px;background:#fff0f0;color:#b3261e;font-size:18px;cursor:pointer}.pvc-schedules-empty{padding:13px;border:1px dashed #cbd6df;border-radius:10px;color:#63778a;background:#fff}@media(max-width:900px){.pvc-calendar-head,.pvc-calendar-import{grid-template-columns:1fr;display:grid}.pvc-calendar-actions{justify-content:flex-start}}
    `;
    document.head.appendChild(style);
  }

  async function renderPvcSchedules(force = false) {
    if (!isPvc()) return;
    const tab = document.querySelector('#tab-schedules');
    const reportId = Number(window.state?.activeReport?.id || 0);
    if (!tab || !reportId) return;
    if (!force && tab.dataset.pvcSchedulesFor === String(reportId) && tab.querySelector('.pvc-schedules-root')) return;

    const token = ++renderToken;
    tab.dataset.pvcSchedulesFor = String(reportId);
    tab.innerHTML = '<div class="panel"><div class="empty-mini">Cargando cronogramas de Artículo Académico...</div></div>';
    try {
      const data = await api(`/api/reports/${reportId}/schedules`);
      if (token !== renderToken || Number(window.state?.activeReport?.id || 0) !== reportId || !isPvc()) return;
      let groups = groupStoredEntries(data?.schedules?.thesis || []);
      const hasSaved = groups.some(group => group.items.length);
      if (!hasSaved) groups = matchesTemplatePeriod() ? templateGroups() : [emptyGroup(1)];
      const period = clean(window.state?.activeReport?.period || '');
      tab.innerHTML = `
        <div class="pvc-schedules-root" data-pvc-schedules-root>
          <section class="pvc-schedules-hero">
            <h2>Cronogramas de Artículo Académico</h2>
            <p>${esc(period)} · PVC puede manejar varios cronogramas independientes dentro del mismo informe.</p>
            <div class="pvc-schedules-note"><strong>Correcto para PVC:</strong> no utiliza Núcleos ni Examen Complexivo. Todos los cronogramas corresponden al proceso de Artículo Académico.</div>
            <div class="pvc-schedules-toolbar">
              <button type="button" class="button secondary" data-pvc-add-calendar>Agregar cronograma</button>
              ${matchesTemplatePeriod() ? '<button type="button" class="button secondary" data-pvc-load-defaults>Usar cronogramas del período</button>' : ''}
              <button type="button" class="button primary" data-pvc-save-all>Guardar todos</button>
            </div>
          </section>
          ${!hasSaved && matchesTemplatePeriod() ? '<div class="pvc-schedules-empty">Se cargaron como vista previa los tres cronogramas suministrados: Superiores, Universitarias 2 y Universitarias 1. Pulse <strong>Guardar todos</strong> para registrarlos.</div>' : ''}
          <div class="pvc-calendars" data-pvc-calendars>${groups.map(groupMarkup).join('')}</div>
        </div>`;
      bindRoot(tab.querySelector('[data-pvc-schedules-root]'), reportId);
    } catch (error) {
      tab.innerHTML = `<div class="panel"><div class="empty-mini">${esc(error.message || 'No se pudieron cargar los cronogramas PVC.')}</div></div>`;
    }
  }

  function scheduleApply() {
    if (applying || !isPvc()) return;
    const tab = document.querySelector('#tab-schedules');
    if (!tab) return;
    const wrongContent = tab.querySelector('[data-schedule-card="complexive"], [data-schedule-card="thesis"]');
    const missingPvc = !tab.querySelector('.pvc-schedules-root');
    if (!wrongContent && !missingPvc) return;
    applying = true;
    Promise.resolve(renderPvcSchedules(true)).finally(() => { applying = false; });
  }

  injectStyles();

  document.addEventListener('click', event => {
    const tabButton = event.target.closest?.('[data-tab="schedules"]');
    if (tabButton && isPvc()) setTimeout(() => renderPvcSchedules(true), 0);
  }, true);

  const observer = new MutationObserver(() => {
    if (!isPvc()) return;
    queueMicrotask(scheduleApply);
  });
  observer.observe(document.body, { childList: true, subtree: true });

  setTimeout(scheduleApply, 0);
})();
