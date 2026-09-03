(() => {
  'use strict';

  if (!/(^|\.)github\.io$/i.test(window.location.hostname)) return;

  const firebaseConfig = {
    apiKey: 'AIzaSyCaHf1C0BB0X_H3BDZ1o-UDAsPmLTjsZLA',
    authDomain: 'utet-4387a.firebaseapp.com',
    projectId: 'utet-4387a',
    storageBucket: 'utet-4387a.firebasestorage.app',
    messagingSenderId: '902848131454',
    appId: '1:902848131454:web:47f515eb6480834724c32f',
  };
  const databaseRoot = `https://firestore.googleapis.com/v1/projects/${firebaseConfig.projectId}/databases/(default)`;
  const nativeFetch = window.fetch.bind(window);
  const allowedCollections = new Set([
    'Estudiante', 'carreras', 'historial', 'importaciones', 'matriculas',
    'periodos', 'requisitos', 'nucleos', 'complexivo', 'trabajoTitulacion',
    'articulo', 'notas',
  ]);
  const months = {
    ENERO: 1, FEBRERO: 2, MARZO: 3, ABRIL: 4, MAYO: 5, JUNIO: 6,
    JULIO: 7, AGOSTO: 8, SEPTIEMBRE: 9, SETIEMBRE: 9, OCTUBRE: 10,
    NOVIEMBRE: 11, DICIEMBRE: 12,
  };
  const monthNames = [
    '', 'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
    'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre',
  ];
  const state = {
    connected: false,
    lastError: '',
    periods: [],
    complexive: [],
    refreshPromise: null,
  };

  window.INFORMTIT_FIREBASE_DIRECT = true;
  window.INFORMTIT_FIREBASE_CONFIG = Object.freeze({ ...firebaseConfig });

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

  function firestoreValue(value) {
    if (!value || typeof value !== 'object') return value;
    if (Object.prototype.hasOwnProperty.call(value, 'nullValue')) return null;
    if (Object.prototype.hasOwnProperty.call(value, 'booleanValue')) return Boolean(value.booleanValue);
    if (Object.prototype.hasOwnProperty.call(value, 'integerValue')) return Number(value.integerValue || 0);
    if (Object.prototype.hasOwnProperty.call(value, 'doubleValue')) return Number(value.doubleValue || 0);
    if (Object.prototype.hasOwnProperty.call(value, 'timestampValue')) return value.timestampValue;
    if (Object.prototype.hasOwnProperty.call(value, 'stringValue')) return value.stringValue;
    if (Object.prototype.hasOwnProperty.call(value, 'referenceValue')) return value.referenceValue;
    if (Object.prototype.hasOwnProperty.call(value, 'geoPointValue')) return { ...value.geoPointValue };
    if (Object.prototype.hasOwnProperty.call(value, 'arrayValue')) {
      return (value.arrayValue?.values || []).map(firestoreValue);
    }
    if (Object.prototype.hasOwnProperty.call(value, 'mapValue')) {
      return Object.fromEntries(
        Object.entries(value.mapValue?.fields || {}).map(([key, item]) => [key, firestoreValue(item)]),
      );
    }
    return null;
  }

  function encodeValue(value) {
    if (value === null || value === undefined) return { nullValue: null };
    if (typeof value === 'boolean') return { booleanValue: value };
    if (Number.isInteger(value)) return { integerValue: String(value) };
    if (typeof value === 'number') return { doubleValue: value };
    if (Array.isArray(value)) return { arrayValue: { values: value.map(encodeValue) } };
    if (typeof value === 'object') {
      return {
        mapValue: {
          fields: Object.fromEntries(Object.entries(value).map(([key, item]) => [key, encodeValue(item)])),
        },
      };
    }
    return { stringValue: String(value) };
  }

  function decodeDocument(document) {
    const result = Object.fromEntries(
      Object.entries(document?.fields || {}).map(([key, value]) => [key, firestoreValue(value)]),
    );
    const name = clean(document?.name);
    result._id = name ? decodeURIComponent(name.split('/').pop()) : '';
    result._createTime = document?.createTime || '';
    result._updateTime = document?.updateTime || '';
    return result;
  }

  async function firebaseRequest(path, options = {}) {
    const url = new URL(`${databaseRoot}${path}`);
    url.searchParams.set('key', firebaseConfig.apiKey);
    Object.entries(options.params || {}).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') url.searchParams.set(key, String(value));
    });
    const response = await nativeFetch(url.toString(), {
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
      try {
        const payload = await response.json();
        detail = clean(payload?.error?.message);
      } catch (_) {}
      const message = response.status === 401 || response.status === 403
        ? `Firebase rechazó la lectura. Revise las reglas de Firestore.${detail ? ` ${detail}` : ''}`
        : `Firebase respondió con error ${response.status}.${detail ? ` ${detail}` : ''}`;
      throw new Error(message);
    }
    if (response.status === 204) return {};
    return response.json();
  }

  function assertCollection(collection) {
    if (!allowedCollections.has(collection)) throw new Error(`Colección Firebase no autorizada: ${collection}`);
  }

  async function listCollection(collection, pageSize = 1000) {
    assertCollection(collection);
    const rows = [];
    let pageToken = '';
    do {
      const payload = await firebaseRequest(`/documents/${collection}`, {
        allow404: true,
        params: { pageSize: Math.min(Math.max(Number(pageSize) || 1, 1), 1000), pageToken },
      }) || {};
      rows.push(...(payload.documents || []).map(decodeDocument));
      pageToken = clean(payload.nextPageToken);
    } while (pageToken);
    return rows;
  }

  async function getDocument(collection, documentId) {
    assertCollection(collection);
    const payload = await firebaseRequest(
      `/documents/${collection}/${encodeURIComponent(clean(documentId))}`,
      { allow404: true },
    );
    return payload ? decodeDocument(payload) : null;
  }

  async function queryEqual(collection, field, value) {
    assertCollection(collection);
    try {
      const payload = await firebaseRequest('/documents:runQuery', {
        method: 'POST',
        body: {
          structuredQuery: {
            from: [{ collectionId: collection }],
            where: {
              fieldFilter: {
                field: { fieldPath: field },
                op: 'EQUAL',
                value: encodeValue(value),
              },
            },
          },
        },
      });
      return (payload || []).filter(item => item.document).map(item => decodeDocument(item.document));
    } catch (_) {
      const rows = await listCollection(collection);
      return rows.filter(item => item?.[field] === value);
    }
  }

  function periodLabel(periodId) {
    const match = /^(\d{4})-(\d{2})__(\d{4})-(\d{2})$/.exec(clean(periodId));
    if (!match) return clean(periodId);
    const [, y1, m1, y2, m2] = match;
    return `${monthNames[Number(m1)] || m1} ${y1} - ${monthNames[Number(m2)] || m2} ${y2}`;
  }

  function periodMonths(value) {
    const text = clean(value);
    let match = /(\d{4})-(\d{1,2})\s*__\s*(\d{4})-(\d{1,2})/.exec(text);
    if (match) return [Number(match[2]), Number(match[4])];
    const normalized = fold(text);
    const names = Object.keys(months).sort((a, b) => b.length - a.length).join('|');
    match = new RegExp(`\\b(${names})\\b\\s+\\d{4}\\s*(?:-|–|—|A|AL)\\s*\\b(${names})\\b\\s+\\d{4}`).exec(normalized);
    if (match) return [months[match[1]], months[match[2]]];
    return null;
  }

  function classifyPeriod(value) {
    const pair = periodMonths(value);
    return pair && ((pair[0] === 4 && pair[1] === 9) || (pair[0] === 10 && pair[1] === 3))
      ? 'normal'
      : 'pvc';
  }

  async function listPeriods() {
    const rows = (await listCollection('periodos')).filter(item => !item.eliminado);
    const periods = rows.map(item => {
      const periodoId = clean(item.periodoId || item._id);
      const reportType = classifyPeriod(periodoId || item.label);
      return {
        periodoId,
        label: clean(item.label) || periodLabel(periodoId),
        inicio: item.inicio || '',
        fin: item.fin || '',
        activo: item.activo !== false,
        orden: Number(item.orden || 0),
        report_type: reportType,
        report_label: reportType === 'pvc' ? 'PVC' : 'Presencial + Online',
      };
    }).filter(item => item.periodoId);
    periods.sort((a, b) => (b.orden - a.orden) || b.periodoId.localeCompare(a.periodoId));
    state.periods = periods;
    return periods;
  }

  function modality(enrollment, student, career) {
    const value = fold([
      enrollment?.modalidadTitulacion,
      enrollment?.modalidadEstudio,
      enrollment?.modalidadAcademica,
      enrollment?.modalidad,
      student?.nombreCarreraActual,
      career?.nombreCarrera,
    ].filter(Boolean).join(' '));
    const code = clean(student?.codigoCarreraActual || enrollment?.codigoCarrera).toUpperCase();
    return /(ONLINE|EN LINEA|VIRTUAL)/.test(value) || code.includes('-L-') ? 'en_linea' : 'presencial';
  }

  async function batchGetStudents(cedulas) {
    const unique = [...new Set(cedulas.map(clean).filter(Boolean))];
    const output = new Map();
    for (let start = 0; start < unique.length; start += 100) {
      const batch = unique.slice(start, start + 100);
      const payload = await firebaseRequest('/documents:batchGet', {
        method: 'POST',
        body: {
          documents: batch.map(cedula => (
            `projects/${firebaseConfig.projectId}/databases/(default)/documents/Estudiante/${encodeURIComponent(cedula)}`
          )),
        },
      });
      (payload || []).forEach(item => {
        if (!item.found) return;
        const student = decodeDocument(item.found);
        const key = clean(student.cedula || student._id);
        if (key) output.set(key, student);
      });
    }
    return output;
  }

  async function syncPeriod(periodId) {
    periodId = clean(periodId);
    if (!periodId) throw new Error('Seleccione un periodo.');
    const period = await getDocument('periodos', periodId) || { periodoId: periodId, label: periodLabel(periodId) };
    const reportType = classifyPeriod(periodId);
    const [requirements, enrollments, careers] = await Promise.all([
      queryEqual('requisitos', 'periodoId', periodId),
      queryEqual('matriculas', 'periodoId', periodId),
      listCollection('carreras'),
    ]);
    const activeReq = requirements.filter(item => !item.eliminado);
    const activeEnroll = enrollments.filter(item => !item.eliminado);
    const reqById = new Map(activeReq.map(item => [clean(item.cedula), item]).filter(([key]) => key));
    const enrollById = new Map(activeEnroll.map(item => [clean(item.cedula), item]).filter(([key]) => key));
    const cedulas = [...new Set([...reqById.keys(), ...enrollById.keys()])];
    const students = await batchGetStudents(cedulas);
    const careerByCode = new Map(
      careers.filter(item => !item.eliminado).map(item => [clean(item.codigoCarrera || item._id), item]),
    );
    let presencial = 0;
    let enLinea = 0;
    const unmatched = [];
    cedulas.forEach(cedula => {
      const student = students.get(cedula);
      if (!student) {
        unmatched.push({
          cedula,
          in_requirements: reqById.has(cedula),
          in_enrollment: enrollById.has(cedula),
          reason: 'No existe en la colección Estudiante.',
        });
        return;
      }
      if (reportType === 'pvc') {
        presencial += 1;
        return;
      }
      const enrollment = enrollById.get(cedula) || {};
      const career = careerByCode.get(clean(student.codigoCarreraActual || enrollment.codigoCarrera)) || {};
      if (modality(enrollment, student, career) === 'en_linea') enLinea += 1;
      else presencial += 1;
    });

    const snapshot = {
      period_id: periodId,
      label: clean(period.label) || periodLabel(periodId),
      report_type: reportType,
      synced_at: new Date().toISOString(),
      students: students.size,
      requirements: activeReq.length,
      enrollments: activeEnroll.length,
      presencial,
      en_linea: reportType === 'pvc' ? 0 : enLinea,
      unmatched: unmatched.length,
    };
    try {
      window.localStorage.setItem(`informtit.firebase.sync.${periodId}`, JSON.stringify(snapshot));
      window.localStorage.setItem('informtit.firebase.lastPeriod', periodId);
    } catch (_) {}

    return {
      ok: true,
      periodoId: periodId,
      period: snapshot.label,
      report_type: reportType,
      report_ids: {},
      report_id: 0,
      requirements: {
        students: students.size,
        requirements: activeReq.length,
        enrollments: activeEnroll.length,
        presencial,
        en_linea: snapshot.en_linea,
        unmatched_students: unmatched,
      },
      restored: {},
      written: {},
      warnings: [],
      mode: 'firebase_direct_web',
      protected_collections: ['Estudiante', 'carreras', 'historial', 'importaciones', 'matriculas', 'periodos', 'requisitos'],
      writable_collections: ['nucleos', 'complexivo', 'trabajoTitulacion', 'articulo'],
    };
  }

  function jsonResponse(payload, status = 200) {
    return new Response(JSON.stringify(payload), {
      status,
      headers: { 'Content-Type': 'application/json; charset=utf-8' },
    });
  }

  function apiPath(input) {
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

  async function requestBody(input, init) {
    if (init?.body) return JSON.parse(String(init.body));
    if (input instanceof Request) {
      try { return await input.clone().json(); } catch (_) {}
    }
    return {};
  }

  const interceptedFetch = window.fetch.bind(window);
  window.fetch = async function firebasePagesFetch(input, init) {
    const path = apiPath(input);
    const method = methodOf(input, init);
    try {
      if (method === 'GET' && path === '/api/firebase/status') {
        return jsonResponse({
          ok: true,
          project_id: firebaseConfig.projectId,
          configured: true,
          connected: state.connected,
          source: 'Firebase Firestore directo',
          mode: 'github_pages',
        });
      }
      if (method === 'GET' && path === '/api/firebase/periods') {
        return jsonResponse({ ok: true, periods: await listPeriods(), source: 'Firebase directo' });
      }
      if (method === 'POST' && path === '/api/firebase/sync') {
        const body = await requestBody(input, init);
        return jsonResponse(await syncPeriod(body.period_id));
      }
    } catch (error) {
      state.connected = false;
      state.lastError = error?.message || String(error);
      renderConnectionCard();
      return jsonResponse({ ok: false, error: state.lastError }, 503);
    }
    return interceptedFetch(input, init);
  };

  function metricByLabel(label) {
    return [...document.querySelectorAll('#dashboard-metrics .metric')].find(metric => (
      clean(metric.querySelector('span')?.textContent).toLowerCase() === label.toLowerCase()
    ));
  }

  function setMetric(labelCandidates, value) {
    const metric = labelCandidates.map(metricByLabel).find(Boolean);
    if (!metric) return;
    const strong = metric.querySelector('strong');
    if (strong && strong.textContent !== String(value)) strong.textContent = String(value);
  }

  function careerKey(item) {
    return clean(
      item.carrera || item.nombreCarrera || item.career_name || item.codigoCarrera ||
      item.carreraCodigo || item.codigo_carrera || '',
    );
  }

  function removeServerPanel() {
    const panel = document.getElementById('informtit-web-bridge');
    if (panel) panel.remove();
  }

  function renderConnectionCard() {
    removeServerPanel();
    let card = document.getElementById('firebase-pages-status');
    if (!card) {
      card = document.createElement('div');
      card.id = 'firebase-pages-status';
      const dashboard = document.getElementById('view-dashboard');
      if (dashboard) dashboard.insertBefore(card, dashboard.firstChild);
      else return;
    }
    const ok = state.connected;
    card.style.cssText = [
      'margin:0 0 16px', 'padding:13px 15px', 'border-radius:12px',
      `background:${ok ? '#ecfdf3' : '#fff7ed'}`,
      `border:1px solid ${ok ? '#a7f3d0' : '#fed7aa'}`,
      `color:${ok ? '#14532d' : '#7c2d12'}`,
      'font:13px/1.45 system-ui,-apple-system,Segoe UI,sans-serif',
    ].join(';');
    card.innerHTML = ok
      ? `<strong style="display:block;margin-bottom:3px">Firebase UTET conectado</strong>
         <span>Proyecto <b>${firebaseConfig.projectId}</b> · Firestore. Informtit lee los periodos y datos oficiales directamente desde Firebase.</span>`
      : `<strong style="display:block;margin-bottom:3px">Firebase UTET configurado</strong>
         <span>${clean(state.lastError) || 'Comprobando acceso a Firestore...'}</span>`;
  }

  async function refreshDashboard() {
    if (state.refreshPromise) return state.refreshPromise;
    state.refreshPromise = (async () => {
      renderConnectionCard();
      try {
        const [periods, complexive] = await Promise.all([
          listPeriods(),
          listCollection('complexivo').catch(() => []),
        ]);
        state.complexive = complexive.filter(item => !item.eliminado);
        state.connected = true;
        state.lastError = '';
        setMetric(['Períodos', 'Informes'], periods.length);
        setMetric(['Carreras en Complexivo', 'Carreras'], new Set(state.complexive.map(careerKey).filter(Boolean)).size);
        setMetric(['Registros en Complexivo', 'Estudiantes procesados'], state.complexive.length);
        renderConnectionCard();
        window.dispatchEvent(new CustomEvent('informtit:firebase-connected', {
          detail: { projectId: firebaseConfig.projectId, periods: periods.length },
        }));
        return { ok: true, periods, complexive: state.complexive };
      } catch (error) {
        state.connected = false;
        state.lastError = error?.message || String(error);
        renderConnectionCard();
        throw error;
      } finally {
        state.refreshPromise = null;
      }
    })();
    return state.refreshPromise;
  }

  window.informtitFirebasePages = Object.freeze({
    config: Object.freeze({ ...firebaseConfig }),
    listPeriods,
    listCollection,
    queryEqual,
    syncPeriod,
    refreshDashboard,
    get connected() { return state.connected; },
  });

  let scheduled = false;
  const observer = new MutationObserver(() => {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => {
      scheduled = false;
      removeServerPanel();
      renderConnectionCard();
      if (state.connected) {
        setMetric(['Períodos', 'Informes'], state.periods.length);
        setMetric(['Carreras en Complexivo', 'Carreras'], new Set(state.complexive.map(careerKey).filter(Boolean)).size);
        setMetric(['Registros en Complexivo', 'Estudiantes procesados'], state.complexive.length);
      }
    });
  });

  function install() {
    removeServerPanel();
    renderConnectionCard();
    observer.observe(document.body, { childList: true, subtree: true });
    document.getElementById('refresh-btn')?.addEventListener('click', () => {
      window.setTimeout(() => refreshDashboard().catch(() => {}), 60);
    });
    window.setTimeout(() => refreshDashboard().catch(() => {}), 80);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install, { once: true });
  else install();
})();
