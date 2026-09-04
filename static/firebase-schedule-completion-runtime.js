(() => {
  'use strict';

  if (!/(^|\.)github\.io$/i.test(window.location.hostname)) return;

  const previousFetch = window.fetch.bind(window);
  const REPORTS_KEY = 'informtit.githubPages.reports.v1';
  const COMPLETE_STATUS = 'Cumplido';
  const COMPLETE_PERCENTAGE = 100;

  const KNOWN_THESIS = Object.freeze({
    '2025-10__2026-03': [
      ['Fase 1: Inicio y planificación', 'Inducción', '16/12/2025', '16/12/2025'],
      ['Fase 1: Inicio y planificación', 'Clase Redacción eficiente de tesis', '28/01/2026', '28/01/2026'],
      ['Fase 1: Inicio y planificación', 'Elaboración de propuesta de temas', '01/02/2026', '01/02/2026'],
      ['Fase 1: Inicio y planificación', 'Aprobación del tema', '02/02/2026', '04/02/2026'],
      ['Fase 1: Inicio y planificación', 'Elaboración del plan de titulación', '08/02/2026', '08/02/2026'],
      ['Fase 1: Inicio y planificación', 'Aprobación del plan', '09/02/2026', '11/02/2026'],
      ['Fase 2: Desarrollo y tutorías', 'Desarrollo del trabajo (redacción)', '11/02/2026', '28/02/2026'],
      ['Fase 2: Desarrollo y tutorías', 'Borrador 1', '01/03/2026', '01/03/2026'],
      ['Fase 2: Desarrollo y tutorías', 'Revisión del borrador 1 con el estudiante', '02/03/2026', '05/03/2026'],
      ['Fase 2: Desarrollo y tutorías', 'Borrador 2', '08/03/2026', '08/03/2026'],
      ['Fase 2: Desarrollo y tutorías', 'Revisión del borrador 2 con el estudiante', '09/03/2026', '13/03/2026'],
      ['Fase 2: Desarrollo y tutorías', 'Ajustes finales del trabajo', '14/03/2026', '19/03/2026'],
      ['Fase 2: Desarrollo y tutorías', 'Entrega de trabajo de titulación', '22/03/2026', '22/03/2026'],
      ['Fase 2: Desarrollo y tutorías', 'Aprobación del tutor e informe antiplagio', '23/03/2026', '25/03/2026'],
      ['Fase 2: Desarrollo y tutorías', 'Fin de clases', '27/03/2026', '27/03/2026'],
      ['Fase 3: Defensa final', 'Preparación de defensa', '25/03/2026', '08/04/2026'],
      ['Fase 3: Defensa final', 'Defensa de tesis', '14/04/2026', '15/04/2026'],
      ['Fase 3: Defensa final', 'Tutoría extra de supletorio', '14/04/2026', '15/04/2026'],
      ['Fase 3: Defensa final', 'Supletorio defensa', '16/04/2026', '18/04/2026'],
      ['Fase 3: Defensa final', 'Cierre del proceso', '20/04/2026', '20/04/2026'],
    ],
  });

  function clean(value) {
    return String(value ?? '').replace(/\u00a0/g, ' ').trim().replace(/\s+/g, ' ');
  }

  function fold(value) {
    return clean(value)
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .toUpperCase();
  }

  function pathOf(input) {
    try {
      const raw = typeof input === 'string' ? input : input?.url;
      return new URL(raw, window.location.href).pathname;
    } catch (_) {
      return '';
    }
  }

  function methodOf(input, init) {
    return String(init?.method || input?.method || 'GET').toUpperCase();
  }

  async function bodyOf(input, init) {
    if (init?.body !== undefined && init?.body !== null) {
      if (typeof init.body === 'string') {
        try { return JSON.parse(init.body); } catch (_) { return {}; }
      }
    }
    if (input instanceof Request) {
      try { return await input.clone().json(); } catch (_) {}
    }
    return {};
  }

  function jsonResponse(payload, status = 200) {
    return Promise.resolve(new Response(JSON.stringify(payload), {
      status,
      headers: { 'Content-Type': 'application/json; charset=utf-8' },
    }));
  }

  function canonicalPeriodId(value) {
    const text = clean(value);
    const direct = /^(\d{4})-(\d{2})__(\d{4})-(\d{2})$/.exec(text);
    if (direct) return text;
    const months = {
      ENERO: 1, FEBRERO: 2, MARZO: 3, ABRIL: 4, MAYO: 5, JUNIO: 6,
      JULIO: 7, AGOSTO: 8, SEPTIEMBRE: 9, SETIEMBRE: 9, OCTUBRE: 10,
      NOVIEMBRE: 11, DICIEMBRE: 12,
    };
    const normalized = fold(text).replace(/[–—]/g, '-');
    const names = Object.keys(months).sort((a, b) => b.length - a.length).join('|');
    const match = new RegExp(`\\b(${names})\\b\\s+(\\d{4}).*?\\b(${names})\\b\\s+(\\d{4})`).exec(normalized);
    if (!match) return '';
    return `${match[2]}-${String(months[match[1]]).padStart(2, '0')}__${match[4]}-${String(months[match[3]]).padStart(2, '0')}`;
  }

  function reportById(reportId) {
    try {
      const reports = JSON.parse(window.localStorage.getItem(REPORTS_KEY) || '[]');
      if (!Array.isArray(reports)) return null;
      return reports.find(item => Number(item.id) === Number(reportId)
        || (item.legacy_report_ids || []).some(id => Number(id) === Number(reportId))) || null;
    } catch (_) {
      return null;
    }
  }

  function periodIdForReport(report) {
    return canonicalPeriodId(report?.firebase_period_id) || canonicalPeriodId(report?.period);
  }

  function normalizeDate(value) {
    const text = clean(value);
    let match = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(text);
    if (match) {
      const day = Number(match[1]);
      const month = Number(match[2]);
      const year = Number(match[3]);
      const date = new Date(Date.UTC(year, month - 1, day));
      if (date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day) {
        return `${String(day).padStart(2, '0')}/${String(month).padStart(2, '0')}/${year}`;
      }
    }
    match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(text);
    if (match) return normalizeDate(`${match[3]}/${match[2]}/${match[1]}`);
    return text;
  }

  function autoCompleteEntry(item, type, index) {
    const endDate = normalizeDate(item?.end_date || item?.start_date || '');
    return {
      ...item,
      phase: type === 'thesis' ? clean(item?.phase) : '',
      activity: clean(item?.activity),
      start_date: normalizeDate(item?.start_date || ''),
      end_date: endDate,
      executed_date: endDate,
      execution_status: COMPLETE_STATUS,
      compliance_percentage: COMPLETE_PERCENTAGE,
      evidence: clean(item?.evidence),
      observation: clean(item?.observation),
      sort_order: index + 1,
    };
  }

  function normalizeEntries(entries, type) {
    if (!Array.isArray(entries)) return [];
    return entries
      .map((item, index) => autoCompleteEntry(item, type, index))
      .filter(item => item.activity && item.start_date && item.end_date);
  }

  function knownThesisEntries(periodId) {
    return (KNOWN_THESIS[periodId] || []).map(([phase, activity, start_date, end_date], index) => (
      autoCompleteEntry({ phase, activity, start_date, end_date }, 'thesis', index)
    ));
  }

  function stripMarkdown(value) {
    return clean(value)
      .replace(/^#{1,6}\s*/, '')
      .replace(/^>\s*/, '')
      .replace(/\*\*/g, '')
      .replace(/__/g, '')
      .replace(/`/g, '')
      .trim();
  }

  function phaseFromLine(rawLine) {
    const candidate = stripMarkdown(rawLine)
      .replace(/^\|+|\|+$/g, '')
      .replace(/\|/g, ' ')
      .trim();
    if (!/^Fase\s+\d+\s*(?::|-|–|—)?\s*/i.test(candidate)) return '';
    return candidate.replace(/\s+/g, ' ').trim();
  }

  function activityFromLine(line, firstDate) {
    const beforeDate = line.slice(0, line.indexOf(firstDate));
    return stripMarkdown(beforeDate)
      .replace(/^\|+|\|+$/g, '')
      .replace(/\|/g, ' ')
      .replace(/^(Actividad(?:Fecha\s*inicio)?(?:Fecha\s*fin)?|Cronograma\s+\d+\s*:?)\s*/i, '')
      .replace(/[;,-]+$/g, '')
      .replace(/\s+/g, ' ')
      .trim();
  }

  function parseScheduleText(text, type) {
    const entries = [];
    let currentPhase = '';
    const dateRegex = /(?:\d{2}\/\d{2}\/\d{4}|\d{4}-\d{2}-\d{2})/g;

    String(text || '').split(/\r?\n/).forEach(rawLine => {
      const raw = String(rawLine || '').trim();
      if (!raw) return;

      if (type === 'thesis') {
        const phase = phaseFromLine(raw);
        if (phase && !(raw.match(dateRegex) || []).length) {
          currentPhase = phase;
          return;
        }
      }

      const line = raw.replace(/^\|+|\|+$/g, '').trim();
      if (!line || /^[-:|\s]+$/.test(line)) return;
      const dates = line.match(dateRegex) || [];
      if (!dates.length) return;

      const activity = activityFromLine(line, dates[0]);
      if (!activity || /fecha\s*(inicio|fin)/i.test(activity)) return;
      const startDate = normalizeDate(dates[0]);
      const endDate = normalizeDate(dates[1] || dates[0]);
      entries.push(autoCompleteEntry({
        phase: type === 'thesis' ? currentPhase : '',
        activity,
        start_date: startDate,
        end_date: endDate,
      }, type, entries.length));
    });

    if (!entries.length) {
      throw new Error('No se detectaron actividades con fechas válidas. Puede pegar tablas Markdown con Actividad, Fecha inicio y Fecha fin.');
    }
    return entries;
  }

  async function readTextPayload(payload) {
    if (clean(payload?.text)) return String(payload.text);
    const dataUrl = clean(payload?.data_url);
    if (!dataUrl || !dataUrl.includes(',')) return '';
    const encoded = dataUrl.split(',', 2)[1] || '';
    try {
      const binary = atob(encoded);
      const bytes = Uint8Array.from(binary, char => char.charCodeAt(0));
      return new TextDecoder('utf-8').decode(bytes);
    } catch (_) {
      throw new Error('No se pudo leer el archivo del cronograma. Si es un .xls antiguo, pegue la tabla directamente.');
    }
  }

  function requestWithJson(input, init, body) {
    const headers = new Headers(init?.headers || (input instanceof Request ? input.headers : undefined));
    headers.set('Content-Type', 'application/json');
    return previousFetch(input, {
      ...(init || {}),
      method: methodOf(input, init),
      headers,
      body: JSON.stringify(body),
    });
  }

  function schedulesChanged(original, normalized) {
    return JSON.stringify(original || []) !== JSON.stringify(normalized || []);
  }

  function migrateScheduleInBackground(reportId, type, entries) {
    if (!entries.length) return;
    queueMicrotask(() => {
      previousFetch(`/api/reports/${reportId}/schedules/${type}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ entries }),
      }).catch(() => null);
    });
  }

  window.fetch = async function scheduleAutoCompletionFetch(input, init) {
    const path = pathOf(input);
    const method = methodOf(input, init);

    let match = path.match(/^\/api\/reports\/(\d+)\/schedules\/(complexive|thesis)\/parse$/);
    if (match && method === 'POST') {
      try {
        const payload = await bodyOf(input, init);
        const text = await readTextPayload(payload);
        const entries = parseScheduleText(text, match[2]);
        return jsonResponse({
          ok: true,
          entries,
          auto_execution: true,
          execution_status: COMPLETE_STATUS,
          compliance_percentage: COMPLETE_PERCENTAGE,
        });
      } catch (error) {
        return jsonResponse({ ok: false, error: clean(error?.message) || 'No se pudo interpretar el cronograma.' }, 400);
      }
    }

    match = path.match(/^\/api\/reports\/(\d+)\/schedules\/(complexive|thesis)$/);
    if (match && method === 'PUT') {
      const payload = await bodyOf(input, init);
      const entries = normalizeEntries(payload.entries, match[2]);
      return requestWithJson(input, init, { ...payload, entries });
    }

    match = path.match(/^\/api\/reports\/(\d+)\/schedules\/thesis\/reset$/);
    if (match && method === 'POST') {
      const reportId = Number(match[1]);
      const periodId = periodIdForReport(reportById(reportId));
      const known = knownThesisEntries(periodId);
      if (known.length) {
        return previousFetch(`/api/reports/${reportId}/schedules/thesis`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ entries: known }),
        });
      }
    }

    match = path.match(/^\/api\/reports\/(\d+)\/schedules$/);
    if (match && method === 'GET') {
      const reportId = Number(match[1]);
      const response = await previousFetch(input, init);
      if (!response.ok) return response;
      let payload;
      try { payload = await response.clone().json(); } catch (_) { return response; }
      const originalComplexive = payload?.schedules?.complexive || [];
      const originalThesis = payload?.schedules?.thesis || [];
      const normalizedComplexive = normalizeEntries(originalComplexive, 'complexive');
      let normalizedThesis = normalizeEntries(originalThesis, 'thesis');

      const periodId = periodIdForReport(reportById(reportId));
      if (!normalizedThesis.length && KNOWN_THESIS[periodId]) {
        normalizedThesis = knownThesisEntries(periodId);
      }

      payload.schedules = {
        ...(payload.schedules || {}),
        complexive: normalizedComplexive,
        thesis: normalizedThesis,
      };
      payload.schedule_meta = {
        ...(payload.schedule_meta || {}),
        automatic_execution: true,
        execution_status: COMPLETE_STATUS,
        compliance_percentage: COMPLETE_PERCENTAGE,
        thesis_phases_understood: true,
      };

      if (schedulesChanged(originalComplexive, normalizedComplexive)) {
        migrateScheduleInBackground(reportId, 'complexive', normalizedComplexive);
      }
      if (normalizedThesis.length && schedulesChanged(originalThesis, normalizedThesis)) {
        migrateScheduleInBackground(reportId, 'thesis', normalizedThesis);
      }
      return jsonResponse(payload, response.status);
    }

    const response = await previousFetch(input, init);

    match = path.match(/^\/api\/reports\/(\d+)\/schedules\/complexive\/reset$/);
    if (match && method === 'POST' && response.ok) {
      const reportId = Number(match[1]);
      queueMicrotask(async () => {
        try {
          const loaded = await previousFetch(`/api/reports/${reportId}/schedules`, { cache: 'no-store' });
          if (!loaded.ok) return;
          const payload = await loaded.json();
          const entries = normalizeEntries(payload?.schedules?.complexive || [], 'complexive');
          migrateScheduleInBackground(reportId, 'complexive', entries);
        } catch (_) {}
      });
    }

    return response;
  };

  window.informtitScheduleCompletion = Object.freeze({
    status: COMPLETE_STATUS,
    percentage: COMPLETE_PERCENTAGE,
    parseScheduleText,
    knownThesisPeriodIds: Object.keys(KNOWN_THESIS),
  });
})();
