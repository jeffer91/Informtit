(() => {
  'use strict';

  if (!/(^|\.)github\.io$/i.test(window.location.hostname)) return;

  const previousFetch = window.fetch.bind(window);
  const PROJECT_ID = 'utet-4387a';
  const API_KEY = 'AIzaSyCaHf1C0BB0X_H3BDZ1o-UDAsPmLTjsZLA';
  const FIRESTORE_ROOT = `https://firestore.googleapis.com/v1/projects/${PROJECT_ID}/databases/(default)`;
  const REPORTS_KEY = 'informtit.githubPages.reports.v1';
  const CACHE_PREFIX = 'informtit.schedule.webcache.v2.';
  const FRESH_MS = 5 * 60 * 1000;

  const MONTHS = {
    ENERO: 1, FEBRERO: 2, MARZO: 3, ABRIL: 4, MAYO: 5, JUNIO: 6,
    JULIO: 7, AGOSTO: 8, SEPTIEMBRE: 9, SETIEMBRE: 9, OCTUBRE: 10,
    NOVIEMBRE: 11, DICIEMBRE: 12,
  };

  const KNOWN_COMPLEXIVE = Object.freeze({
    '2025-10__2026-03': [
      ['', 'Núcleo 1', '30/03/2026', '02/04/2026'],
      ['', 'Núcleo 2', '06/04/2026', '09/04/2026'],
      ['', 'Núcleo 3', '10/04/2026', '14/04/2026'],
      ['', 'Núcleo 4', '15/04/2026', '18/04/2026'],
      ['', 'Examen Complexivo', '20/04/2026', '24/04/2026'],
      ['', 'Supletorio', '04/05/2026', '04/05/2026'],
    ],
    '2026-04__2026-09': [
      ['', 'Fin de clases', '25/09/2026', '26/09/2026'],
      ['', 'Semana Requisitos', '28/09/2026', '02/10/2026'],
      ['', 'Núcleo 1', '05/10/2026', '08/10/2026'],
      ['', 'Núcleo 2', '12/10/2026', '15/10/2026'],
      ['', 'Núcleo 3', '16/10/2026', '20/10/2026'],
      ['', 'Núcleo 4', '21/10/2026', '24/10/2026'],
      ['', 'Notas de núcleos', '26/10/2026', '27/10/2026'],
      ['', 'Examen Complexivo', '28/10/2026', '31/10/2026'],
      ['', 'Supletorio', '09/11/2026', '11/11/2026'],
    ],
  });

  function clean(value) {
    return String(value ?? '').trim();
  }

  function fold(value) {
    return clean(value)
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .replace(/\s+/g, ' ')
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
    if (init?.body) {
      try { return JSON.parse(String(init.body)); } catch (_) { return {}; }
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
    const direct = /^(\d{4})-(\d{2})__(\d{4})-(\d{2})$/.exec(clean(value));
    if (direct) return clean(value);

    const normalized = fold(value).replace(/[–—]/g, '-');
    const names = Object.keys(MONTHS).sort((a, b) => b.length - a.length).join('|');
    const match = new RegExp(`\\b(${names})\\b\\s+(\\d{4}).*?\\b(${names})\\b\\s+(\\d{4})`).exec(normalized);
    if (!match) return '';
    return `${match[2]}-${String(MONTHS[match[1]]).padStart(2, '0')}__${match[4]}-${String(MONTHS[match[3]]).padStart(2, '0')}`;
  }

  function loadReports() {
    try {
      const parsed = JSON.parse(window.localStorage.getItem(REPORTS_KEY) || '[]');
      return Array.isArray(parsed) ? parsed : [];
    } catch (_) {
      return [];
    }
  }

  function reportById(reportId) {
    return loadReports().find(item => Number(item.id) === Number(reportId)) || null;
  }

  function periodIdForReport(report) {
    return canonicalPeriodId(report?.firebase_period_id) || canonicalPeriodId(report?.period);
  }

  function cacheKey(periodId) {
    return `${CACHE_PREFIX}${periodId}`;
  }

  function readCache(periodId) {
    try {
      const value = JSON.parse(window.localStorage.getItem(cacheKey(periodId)) || 'null');
      return value && typeof value === 'object' ? value : null;
    } catch (_) {
      return null;
    }
  }

  function writeCache(periodId, data) {
    const record = { savedAt: Date.now(), data };
    try { window.localStorage.setItem(cacheKey(periodId), JSON.stringify(record)); } catch (_) {}
    return record;
  }

  function clearCache(periodId) {
    try { window.localStorage.removeItem(cacheKey(periodId)); } catch (_) {}
  }

  function encodeValue(value) {
    if (value === null || value === undefined) return { nullValue: null };
    if (typeof value === 'boolean') return { booleanValue: value };
    if (Number.isInteger(value)) return { integerValue: String(value) };
    if (typeof value === 'number') return { doubleValue: value };
    if (Array.isArray(value)) return { arrayValue: { values: value.map(encodeValue) } };
    if (typeof value === 'object') {
      return { mapValue: { fields: Object.fromEntries(Object.entries(value).map(([key, item]) => [key, encodeValue(item)])) } };
    }
    return { stringValue: String(value) };
  }

  function decodeValue(value) {
    if (!value || typeof value !== 'object') return value;
    if ('nullValue' in value) return null;
    if ('booleanValue' in value) return Boolean(value.booleanValue);
    if ('integerValue' in value) return Number(value.integerValue || 0);
    if ('doubleValue' in value) return Number(value.doubleValue || 0);
    if ('timestampValue' in value) return value.timestampValue;
    if ('stringValue' in value) return value.stringValue;
    if ('arrayValue' in value) return (value.arrayValue?.values || []).map(decodeValue);
    if ('mapValue' in value) {
      return Object.fromEntries(Object.entries(value.mapValue?.fields || {}).map(([key, item]) => [key, decodeValue(item)]));
    }
    return null;
  }

  function decodeDocument(document) {
    return Object.fromEntries(Object.entries(document?.fields || {}).map(([key, value]) => [key, decodeValue(value)]));
  }

  async function firestoreRequest(path, options = {}) {
    const url = new URL(`${FIRESTORE_ROOT}${path}`);
    url.searchParams.set('key', API_KEY);
    const response = await previousFetch(url.toString(), {
      method: options.method || 'GET',
      headers: {
        Accept: 'application/json',
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      },
      body: options.body ? JSON.stringify(options.body) : undefined,
      cache: 'no-store',
    });
    if (options.allow404 && response.status === 404) return null;
    if (!response.ok) {
      let detail = '';
      try { detail = clean((await response.json())?.error?.message); } catch (_) {}
      const prefix = response.status === 401 || response.status === 403
        ? 'Firebase rechazó guardar el cronograma. Revise las reglas de Firestore.'
        : `Firebase respondió con error ${response.status} al guardar el cronograma.`;
      throw new Error(`${prefix}${detail ? ` ${detail}` : ''}`);
    }
    if (response.status === 204) return {};
    return response.json();
  }

  async function getRemote(periodId) {
    const payload = await firestoreRequest(`/documents/cronogramas/${encodeURIComponent(periodId)}`, { allow404: true });
    return payload ? decodeDocument(payload) : null;
  }

  async function putRemote(snapshot) {
    const fields = Object.fromEntries(
      Object.entries({
        periodoId: snapshot.periodId,
        periodo: snapshot.period,
        version: 2,
        complexive: snapshot.complexive,
        thesis: snapshot.thesis,
        updatedAt: new Date().toISOString(),
        source: 'Informtit',
      }).map(([key, value]) => [key, encodeValue(value)]),
    );
    await firestoreRequest(`/documents/cronogramas/${encodeURIComponent(snapshot.periodId)}`, {
      method: 'PATCH',
      body: { fields },
    });
  }

  function normalizeDate(value) {
    const text = clean(value);
    let match = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(text);
    if (match) {
      const day = Number(match[1]);
      const month = Number(match[2]);
      const year = Number(match[3]);
      const date = new Date(Date.UTC(year, month - 1, day));
      if (date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day) return text;
    }
    match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(text);
    if (match) return normalizeDate(`${match[3]}/${match[2]}/${match[1]}`);
    throw new Error(`La fecha '${text}' no tiene un formato válido.`);
  }

  function normalizePercentage(value) {
    if (value === null || value === undefined || clean(value) === '') return null;
    const number = Number(String(value).replace(',', '.'));
    if (!Number.isFinite(number) || number < 0 || number > 100) throw new Error('El porcentaje de cumplimiento debe estar entre 0 y 100.');
    return Math.round(number * 100) / 100;
  }

  function normalizeEntries(entries, type) {
    if (!Array.isArray(entries)) return [];
    return entries.map((item, index) => {
      const activity = clean(item?.activity);
      if (!activity) return null;
      return {
        phase: type === 'thesis' ? clean(item.phase) : '',
        activity,
        start_date: normalizeDate(item.start_date),
        end_date: normalizeDate(item.end_date),
        executed_date: clean(item.executed_date) ? normalizeDate(item.executed_date) : '',
        execution_status: clean(item.execution_status),
        compliance_percentage: normalizePercentage(item.compliance_percentage),
        evidence: clean(item.evidence),
        observation: clean(item.observation),
        sort_order: index + 1,
      };
    }).filter(Boolean);
  }

  function templateEntries(periodId) {
    const rows = KNOWN_COMPLEXIVE[periodId] || [];
    return rows.map(([phase, activity, start_date, end_date], index) => ({
      phase,
      activity,
      start_date,
      end_date,
      executed_date: '',
      execution_status: '',
      compliance_percentage: null,
      evidence: '',
      observation: '',
      sort_order: index + 1,
    }));
  }

  function normalizeRemote(remote, report, periodId) {
    if (!remote) return null;
    const complexiveRaw = Array.isArray(remote.complexive)
      ? remote.complexive
      : Array.isArray(remote.actividades) ? remote.actividades : [];
    const thesisRaw = Array.isArray(remote.thesis) ? remote.thesis : [];
    return {
      periodId,
      period: clean(remote.periodo || report?.period || periodId),
      complexive: normalizeEntries(complexiveRaw, 'complexive'),
      thesis: normalizeEntries(thesisRaw, 'thesis'),
      source: 'Firebase UTET',
      firebaseSaved: true,
      updatedAt: clean(remote.updatedAt),
    };
  }

  function newSnapshot(report, periodId) {
    return {
      periodId,
      period: clean(report?.period || periodId),
      complexive: templateEntries(periodId),
      thesis: [],
      source: KNOWN_COMPLEXIVE[periodId] ? 'Cronograma institucional reconocido' : 'Sin cronograma oficial registrado',
      firebaseSaved: false,
      updatedAt: new Date().toISOString(),
    };
  }

  const refreshInFlight = new Map();

  async function refreshSnapshot(report, periodId, fallback = null) {
    try {
      const remote = normalizeRemote(await getRemote(periodId), report, periodId);
      if (remote && (remote.complexive.length || remote.thesis.length)) {
        writeCache(periodId, remote);
        return remote;
      }
      const seed = fallback?.complexive?.length || fallback?.thesis?.length ? fallback : newSnapshot(report, periodId);
      if (seed.complexive.length || seed.thesis.length) {
        try {
          await putRemote(seed);
          seed.firebaseSaved = true;
          seed.source = 'Firebase UTET';
          seed.updatedAt = new Date().toISOString();
        } catch (error) {
          seed.firebaseSaved = false;
          seed.syncError = clean(error?.message);
        }
      }
      writeCache(periodId, seed);
      return seed;
    } catch (error) {
      if (fallback) {
        const recovered = { ...fallback, firebaseSaved: Boolean(fallback.firebaseSaved), syncError: clean(error?.message) };
        writeCache(periodId, recovered);
        return recovered;
      }
      const seed = newSnapshot(report, periodId);
      seed.syncError = clean(error?.message);
      writeCache(periodId, seed);
      return seed;
    }
  }

  async function loadSnapshot(report, options = {}) {
    const periodId = periodIdForReport(report);
    if (!periodId) throw new Error('No se pudo reconocer el período académico del informe.');
    const cached = readCache(periodId);
    const fresh = cached && (Date.now() - Number(cached.savedAt || 0) <= FRESH_MS);
    if (cached && fresh && !options.force) return { ...cached.data, cacheMode: 'fresh' };
    if (cached && !options.force) {
      if (!refreshInFlight.has(periodId)) {
        const promise = refreshSnapshot(report, periodId, cached.data).finally(() => refreshInFlight.delete(periodId));
        refreshInFlight.set(periodId, promise);
      }
      return { ...cached.data, cacheMode: 'stale-refreshing' };
    }
    const result = await refreshSnapshot(report, periodId, cached?.data || null);
    return { ...result, cacheMode: cached ? 'refreshed' : 'network' };
  }

  function apiPayload(snapshot) {
    return {
      ok: true,
      schedules: {
        complexive: snapshot.complexive || [],
        thesis: snapshot.thesis || [],
      },
      schedule_meta: {
        period_id: snapshot.periodId,
        source: snapshot.source,
        cache_mode: snapshot.cacheMode || '',
        firebase_saved: Boolean(snapshot.firebaseSaved),
        synced_at: snapshot.updatedAt || '',
        warning: snapshot.syncError || '',
        intelligent_template: Boolean(KNOWN_COMPLEXIVE[snapshot.periodId]),
      },
    };
  }

  function parseScheduleText(text, type) {
    const entries = [];
    let currentPhase = '';
    const dateRegex = /(?:\d{2}\/\d{2}\/\d{4}|\d{4}-\d{2}-\d{2})/g;
    clean(text).split(/\r?\n/).forEach(raw => {
      const line = clean(raw).replace(/^\|+|\|+$/g, '').trim();
      if (!line || /^[-:|\s]+$/.test(line)) return;
      if (type === 'thesis' && /^Fase\s+\d+/i.test(line) && !(line.match(dateRegex) || []).length) {
        currentPhase = line.replace(/\|/g, ' ').trim();
        return;
      }
      const dates = line.match(dateRegex) || [];
      if (!dates.length) return;
      const firstIndex = line.indexOf(dates[0]);
      let activity = line.slice(0, firstIndex).replace(/\|/g, ' ').replace(/^(Actividad|Cronograma\s+\d+\s*:?)\s*/i, '').trim();
      activity = activity.replace(/\s+/g, ' ').replace(/[;,-]+$/g, '').trim();
      if (!activity || /fecha\s*(inicio|fin)/i.test(activity)) return;
      const start = normalizeDate(dates[0]);
      const end = normalizeDate(dates[1] || dates[0]);
      entries.push({
        phase: type === 'thesis' ? currentPhase : '',
        activity,
        start_date: start,
        end_date: end,
        executed_date: '',
        execution_status: '',
        compliance_percentage: null,
        evidence: '',
        observation: '',
        sort_order: entries.length + 1,
      });
    });
    if (!entries.length) throw new Error('No se detectaron actividades con fechas válidas. Pegue una tabla con Actividad, Fecha inicio y Fecha fin.');
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
      throw new Error('No se pudo leer el archivo del cronograma. Para archivos .xls antiguos, pegue la tabla directamente.');
    }
  }

  async function saveType(report, type, entries) {
    const snapshot = await loadSnapshot(report, { force: true });
    const cleaned = normalizeEntries(entries, type);
    if (!cleaned.length) throw new Error('El cronograma no contiene actividades válidas.');
    snapshot[type] = cleaned;
    snapshot.updatedAt = new Date().toISOString();
    snapshot.source = 'Caché local pendiente de Firebase';
    snapshot.firebaseSaved = false;
    delete snapshot.syncError;
    writeCache(snapshot.periodId, snapshot);
    try {
      await putRemote(snapshot);
      snapshot.firebaseSaved = true;
      snapshot.source = 'Firebase UTET';
      snapshot.updatedAt = new Date().toISOString();
      writeCache(snapshot.periodId, snapshot);
      return { ok: true, count: cleaned.length, firebase_saved: true, schedule_meta: apiPayload(snapshot).schedule_meta };
    } catch (error) {
      snapshot.syncError = clean(error?.message);
      writeCache(snapshot.periodId, snapshot);
      return { ok: false, error: `El cronograma quedó guardado en caché, pero no se pudo subir a Firebase. ${snapshot.syncError}`, cached: true, firebase_saved: false };
    }
  }

  window.fetch = async function firebaseScheduleFetch(input, init) {
    const path = pathOf(input);
    const method = methodOf(input, init);

    let match = path.match(/^\/api\/reports\/(\d+)\/schedules$/);
    if (match && method === 'GET') {
      const report = reportById(Number(match[1]));
      if (!report) return jsonResponse({ ok: false, error: 'Informe no encontrado.' }, 404);
      try {
        return jsonResponse(apiPayload(await loadSnapshot(report)));
      } catch (error) {
        return jsonResponse({ ok: false, error: clean(error?.message) || 'No se pudo cargar el cronograma.' }, 503);
      }
    }

    match = path.match(/^\/api\/reports\/(\d+)\/schedules\/(complexive|thesis)$/);
    if (match && method === 'PUT') {
      const report = reportById(Number(match[1]));
      if (!report) return jsonResponse({ ok: false, error: 'Informe no encontrado.' }, 404);
      const payload = await bodyOf(input, init);
      try {
        const result = await saveType(report, match[2], payload.entries);
        return jsonResponse(result, result.ok ? 200 : 503);
      } catch (error) {
        return jsonResponse({ ok: false, error: clean(error?.message) || 'No se pudo guardar el cronograma.' }, 400);
      }
    }

    match = path.match(/^\/api\/reports\/(\d+)\/schedules\/(complexive|thesis)\/reset$/);
    if (match && method === 'POST') {
      const report = reportById(Number(match[1]));
      if (!report) return jsonResponse({ ok: false, error: 'Informe no encontrado.' }, 404);
      const type = match[2];
      const periodId = periodIdForReport(report);
      const entries = type === 'complexive' ? templateEntries(periodId) : [];
      if (type === 'complexive' && !entries.length) {
        return jsonResponse({ ok: false, error: 'Este período todavía no tiene un cronograma institucional conocido. Puede ingresarlo manualmente.' }, 400);
      }
      try {
        const snapshot = await loadSnapshot(report, { force: true });
        snapshot[type] = entries;
        snapshot.updatedAt = new Date().toISOString();
        writeCache(periodId, snapshot);
        await putRemote(snapshot);
        snapshot.firebaseSaved = true;
        snapshot.source = 'Firebase UTET';
        writeCache(periodId, snapshot);
        return jsonResponse({ ok: true, count: entries.length, firebase_saved: true });
      } catch (error) {
        return jsonResponse({ ok: false, error: clean(error?.message) || 'No se pudo restaurar el cronograma en Firebase.' }, 503);
      }
    }

    match = path.match(/^\/api\/reports\/(\d+)\/schedules\/(complexive|thesis)\/parse$/);
    if (match && method === 'POST') {
      try {
        const payload = await bodyOf(input, init);
        const text = await readTextPayload(payload);
        return jsonResponse({ ok: true, entries: parseScheduleText(text, match[2]) });
      } catch (error) {
        return jsonResponse({ ok: false, error: clean(error?.message) || 'No se pudo interpretar el cronograma.' }, 400);
      }
    }

    return previousFetch(input, init);
  };

  document.addEventListener('click', event => {
    const button = event.target instanceof Element ? event.target.closest('#refresh-btn, #firebase-sync-btn, [data-refresh]') : null;
    if (!button) return;
    const reportId = Number(window.state?.activeReport?.id || 0);
    const report = reportId ? reportById(reportId) : null;
    const periodId = periodIdForReport(report);
    if (periodId) clearCache(periodId);
  }, true);

  window.informtitScheduleRuntime = Object.freeze({
    canonicalPeriodId,
    knownPeriodIds: Object.keys(KNOWN_COMPLEXIVE),
    clear(periodId) { clearCache(canonicalPeriodId(periodId) || clean(periodId)); },
  });
})();