(() => {
  'use strict';

  if (!/(^|\.)github\.io$/i.test(window.location.hostname)) return;

  const previousFetch = window.fetch.bind(window);
  const PROJECT_ID = 'utet-4387a';
  const API_KEY = 'AIzaSyCaHf1C0BB0X_H3BDZ1o-UDAsPmLTjsZLA';
  const FIRESTORE_ROOT = `https://firestore.googleapis.com/v1/projects/${PROJECT_ID}/databases/(default)`;
  const REPORTS_KEY = 'informtit.githubPages.reports.v1';
  const CACHE_PREFIX = 'informtit.firebase.webcache.v2.';
  const ROUTE_PREFIX = 'informtit.firebase.routeOverrides.v1.';
  const FRESH_MS = 5 * 60 * 1000;
  const REQUIREMENTS = [
    ['academic_status', 'Académico'],
    ['documentation_status', 'Documentación'],
    ['english_status', 'Inglés'],
    ['financial_status', 'Financiero'],
    ['data_update_status', 'Actualización de datos'],
    ['graduate_followup_status', 'Seguimiento a graduados'],
    ['practices_linkage_status', 'Prácticas'],
    ['linkage_status', 'Vinculación'],
  ];
  const REQUIREMENT_MAP = {
    Academico: 'academic_status',
    Documentacion: 'documentation_status',
    Financiero: 'financial_status',
    Titulacion: 'titulation_status',
    PracticasVinculacion: 'practices_linkage_status',
    Vinculacion: 'linkage_status',
    SeguimientoGraduados: 'graduate_followup_status',
    Ingles: 'english_status',
    ActualizacionDatos: 'data_update_status',
    AprobacionTitulacion: 'titulation_approval',
    AprobacionComplexivoProyecto: 'complexive_approval',
  };

  let forceRefreshUntil = 0;
  const refreshInFlight = new Map();

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

  function upper(value) {
    return clean(value).toUpperCase();
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

  function cacheKey(key) {
    return `${CACHE_PREFIX}${key}`;
  }

  function readCache(key) {
    try {
      const parsed = JSON.parse(window.localStorage.getItem(cacheKey(key)) || 'null');
      if (!parsed || typeof parsed !== 'object' || !Object.prototype.hasOwnProperty.call(parsed, 'data')) return null;
      return parsed;
    } catch (_) {
      return null;
    }
  }

  function writeCache(key, data) {
    const record = { savedAt: Date.now(), data };
    try { window.localStorage.setItem(cacheKey(key), JSON.stringify(record)); } catch (_) {}
    return data;
  }

  function removeCache(key) {
    try { window.localStorage.removeItem(cacheKey(key)); } catch (_) {}
  }

  async function cached(key, loader, options = {}) {
    const force = Boolean(options.force) || Date.now() < forceRefreshUntil;
    const record = readCache(key);
    const fresh = record && (Date.now() - Number(record.savedAt || 0) <= FRESH_MS);

    if (record && fresh && !force) return { data: record.data, cache: 'fresh' };

    if (record && !force) {
      if (!refreshInFlight.has(key)) {
        const promise = Promise.resolve()
          .then(loader)
          .then(data => writeCache(key, data))
          .catch(() => null)
          .finally(() => refreshInFlight.delete(key));
        refreshInFlight.set(key, promise);
      }
      return { data: record.data, cache: 'stale-refreshing' };
    }

    try {
      const data = await loader();
      writeCache(key, data);
      return { data, cache: 'network' };
    } catch (error) {
      if (record) return { data: record.data, cache: 'stale-fallback', error: clean(error?.message) };
      throw error;
    }
  }

  function firestoreValue(value) {
    if (!value || typeof value !== 'object') return value;
    if ('nullValue' in value) return null;
    if ('booleanValue' in value) return Boolean(value.booleanValue);
    if ('integerValue' in value) return Number(value.integerValue || 0);
    if ('doubleValue' in value) return Number(value.doubleValue || 0);
    if ('timestampValue' in value) return value.timestampValue;
    if ('stringValue' in value) return value.stringValue;
    if ('referenceValue' in value) return value.referenceValue;
    if ('geoPointValue' in value) return { ...value.geoPointValue };
    if ('arrayValue' in value) return (value.arrayValue?.values || []).map(firestoreValue);
    if ('mapValue' in value) {
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
      return { mapValue: { fields: Object.fromEntries(Object.entries(value).map(([k, v]) => [k, encodeValue(v)])) } };
    }
    return { stringValue: String(value) };
  }

  function decodeDocument(document) {
    const data = Object.fromEntries(
      Object.entries(document?.fields || {}).map(([key, value]) => [key, firestoreValue(value)]),
    );
    const name = clean(document?.name);
    data._id = name ? decodeURIComponent(name.split('/').pop()) : '';
    data._createTime = document?.createTime || '';
    data._updateTime = document?.updateTime || '';
    return data;
  }

  async function firebaseRequest(path, options = {}) {
    const url = new URL(`${FIRESTORE_ROOT}${path}`);
    url.searchParams.set('key', API_KEY);
    Object.entries(options.params || {}).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') url.searchParams.set(key, String(value));
    });
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
      throw new Error(`Firebase respondió con error ${response.status}.${detail ? ` ${detail}` : ''}`);
    }
    if (response.status === 204) return {};
    return response.json();
  }

  async function queryEqual(collection, field, value) {
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
  }

  async function listCollection(collection) {
    const rows = [];
    let pageToken = '';
    do {
      const payload = await firebaseRequest(`/documents/${collection}`, {
        allow404: true,
        params: { pageSize: 1000, pageToken },
      }) || {};
      rows.push(...(payload.documents || []).map(decodeDocument));
      pageToken = clean(payload.nextPageToken);
    } while (pageToken);
    return rows;
  }

  async function batchGetStudents(cedulas) {
    const ids = [...new Set(cedulas.map(clean).filter(Boolean))];
    const output = {};
    for (let start = 0; start < ids.length; start += 100) {
      const batch = ids.slice(start, start + 100);
      const payload = await firebaseRequest('/documents:batchGet', {
        method: 'POST',
        body: {
          documents: batch.map(id => `projects/${PROJECT_ID}/databases/(default)/documents/Estudiante/${encodeURIComponent(id)}`),
        },
      });
      (payload || []).forEach(item => {
        if (!item.found) return;
        const student = decodeDocument(item.found);
        const id = clean(student.cedula || student._id);
        if (id) output[id] = student;
      });
    }
    return output;
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

  function classifyPeriod(periodId) {
    const match = /^(\d{4})-(\d{2})__(\d{4})-(\d{2})$/.exec(clean(periodId));
    if (!match) return 'normal';
    const start = Number(match[2]);
    const end = Number(match[4]);
    return (start === 4 && end === 9) || (start === 10 && end === 3) ? 'normal' : 'pvc';
  }

  function inferModality(enrollment, student, career) {
    const text = fold([
      enrollment?.modalidadTitulacion,
      enrollment?.modalidadEstudio,
      enrollment?.modalidadAcademica,
      enrollment?.modalidad,
      student?.nombreCarreraActual,
      career?.nombreCarrera,
    ].filter(Boolean).join(' '));
    const code = clean(student?.codigoCarreraActual || enrollment?.codigoCarrera).toUpperCase();
    return /(ONLINE|EN LINEA|VIRTUAL)/.test(text) || code.includes('-L-') ? 'en_linea' : 'presencial';
  }

  function requirementState(row) {
    const pending = [];
    const blank = [];
    REQUIREMENTS.forEach(([key, label]) => {
      const value = upper(row[key]);
      if (value === 'NO CUMPLE') pending.push(label);
      else if (value !== 'CUMPLE') blank.push(label);
    });
    return {
      complete: !pending.length && !blank.length,
      pending,
      blank,
      missing: [...pending, ...blank],
    };
  }

  function stableId(value) {
    let hash = 2166136261;
    const text = clean(value);
    for (let i = 0; i < text.length; i += 1) {
      hash ^= text.charCodeAt(i);
      hash = Math.imul(hash, 16777619);
    }
    return Math.abs(hash >>> 0) || 1;
  }

  async function loadPeriodDataset(periodId) {
    periodId = clean(periodId);
    if (!periodId) throw new Error('El informe no tiene un periodo Firebase asociado.');
    const cacheResult = await cached(`period.${periodId}`, async () => {
      const [requirements, enrollments, careers, nuclei] = await Promise.all([
        queryEqual('requisitos', 'periodoId', periodId),
        queryEqual('matriculas', 'periodoId', periodId),
        listCollection('carreras'),
        queryEqual('nucleos', 'periodoId', periodId).catch(() => []),
      ]);
      const activeRequirements = requirements.filter(item => !item.eliminado);
      const activeEnrollments = enrollments.filter(item => !item.eliminado);
      const reqById = Object.fromEntries(activeRequirements.map(item => [clean(item.cedula), item]).filter(([id]) => id));
      const enrollById = Object.fromEntries(activeEnrollments.map(item => [clean(item.cedula), item]).filter(([id]) => id));
      const cedulas = [...new Set([...Object.keys(reqById), ...Object.keys(enrollById)])];
      const students = await batchGetStudents(cedulas);
      const careerByCode = Object.fromEntries(
        careers.filter(item => !item.eliminado).map(item => [clean(item.codigoCarrera || item._id), item]),
      );
      const reportType = classifyPeriod(periodId);
      const rows = [];
      const unmatched = [];

      cedulas.forEach(cedula => {
        const student = students[cedula];
        const enrollment = enrollById[cedula] || {};
        const requirement = reqById[cedula] || {};
        if (!student) {
          unmatched.push({ cedula, reason: 'No existe en Estudiante.' });
          return;
        }
        const careerCode = clean(student.codigoCarreraActual || enrollment.codigoCarrera);
        const career = careerByCode[careerCode] || {};
        const careerName = clean(
          student.nombreCarreraActual || career.nombreCarrera || enrollment.nombreCarrera || 'Sin carrera',
        );
        const values = requirement.valores && typeof requirement.valores === 'object' ? requirement.valores : {};
        const row = {
          id: stableId(cedula),
          identification: cedula,
          full_name: clean(student.nombres || enrollment.nombres || cedula),
          career_code: careerCode,
          career_name: careerName,
          modality: reportType === 'pvc' ? 'presencial' : inferModality(enrollment, student, career),
          schedule: clean(enrollment.division || enrollment.jornada || enrollment.horario),
          personal_email: clean(student.correoPersonal),
          email: clean(student.correoInstitucional).toLowerCase(),
          phone: clean(student.celular),
          campus: clean(student.sede || enrollment.sede),
          retired: Boolean(enrollment.retirado),
        };
        Object.entries(REQUIREMENT_MAP).forEach(([firebaseKey, localKey]) => {
          row[localKey] = upper(values[firebaseKey]);
        });
        const state = requirementState(row);
        row.pending_requirements = state.pending;
        row.blank_requirements = state.blank;
        row.requirements_complete = state.complete;
        row.missing_requirement_labels = state.missing;
        row.notes_loaded = false;
        row.report_career_code = row.career_code;
        row.titulation_marked = upper(row.titulation_status) === 'CUMPLE';
        row.complexive_project_approved = upper(row.complexive_approval) === 'CUMPLE';
        row.titles_uploaded = upper(row.titulation_approval) === 'CUMPLE';
        rows.push(row);
      });

      return {
        periodId,
        reportType,
        rows,
        nuclei: nuclei.filter(item => !item.eliminado),
        unmatched,
        loadedAt: new Date().toISOString(),
      };
    });
    return { ...cacheResult.data, cacheMode: cacheResult.cache };
  }

  function rowsForReport(report, dataset) {
    if (!report || dataset.reportType === 'pvc') return dataset.rows || [];
    const wanted = clean(report.modality) === 'en_linea' ? 'en_linea' : 'presencial';
    return (dataset.rows || []).filter(row => row.modality === wanted);
  }

  function counter(rows, key) {
    const values = new Map();
    rows.forEach(row => {
      const name = clean(row[key]) || `Sin ${key === 'campus' ? 'sede' : key === 'schedule' ? 'jornada' : 'carrera'}`;
      values.set(name, (values.get(name) || 0) + 1);
    });
    return [...values.entries()].sort((a, b) => a[0].localeCompare(b[0], 'es')).map(([name, students]) => ({ name, students }));
  }

  function rosterPayload(report, dataset) {
    const rows = rowsForReport(report, dataset);
    const requirementSummary = REQUIREMENTS.map(([key, label]) => {
      const values = rows.map(row => upper(row[key]));
      return {
        key,
        label,
        complies: values.filter(value => value === 'CUMPLE').length,
        does_not_comply: values.filter(value => value === 'NO CUMPLE').length,
        blank: values.filter(value => !value).length,
        total: rows.length,
      };
    });
    const complete = rows.filter(row => row.requirements_complete).length;
    return {
      ok: true,
      report: {
        id: report.id,
        name: report.name,
        period: report.period,
        modality: report.modality,
      },
      summary: {
        students: rows.length,
        careers: new Set(rows.map(row => row.career_name)).size,
        requirements_complete: complete,
        requirements_pending: rows.length - complete,
        titulation_marked: rows.filter(row => row.titulation_marked).length,
        complexive_project_approved: rows.filter(row => row.complexive_project_approved).length,
        titles_uploaded: rows.filter(row => row.titles_uploaded).length,
        notes_loaded: 0,
        notes_pending: 0,
        is_imported: rows.length > 0,
      },
      careers: counter(rows, 'career_name'),
      campuses: counter(rows, 'campus'),
      schedules: counter(rows, 'schedule'),
      requirements: requirementSummary,
      students: rows,
      source: 'Firebase UTET',
      cache_mode: dataset.cacheMode,
      synced_at: dataset.loadedAt,
    };
  }

  function loadRouteOverrides(reportId) {
    try {
      const parsed = JSON.parse(window.localStorage.getItem(`${ROUTE_PREFIX}${reportId}`) || '{}');
      return parsed && typeof parsed === 'object' ? parsed : {};
    } catch (_) {
      return {};
    }
  }

  function saveRouteOverride(reportId, studentId, route) {
    const overrides = loadRouteOverrides(reportId);
    overrides[String(studentId)] = route;
    try { window.localStorage.setItem(`${ROUTE_PREFIX}${reportId}`, JSON.stringify(overrides)); } catch (_) {}
  }

  function studentsDomainPayload(report, dataset) {
    const rows = rowsForReport(report, dataset);
    const overrides = loadRouteOverrides(report.id);
    const pvc = dataset.reportType === 'pvc';
    const students = rows.map(row => {
      const state = requirementState(row);
      const route = pvc ? 'ARTICULO' : (overrides[String(row.id)] || 'COMPLEXIVO');
      const processStatus = row.retired ? 'RETIRADO' : (state.complete ? 'ACTIVO' : 'NO_APROBADO_REQUISITO');
      return {
        ...row,
        missing_requirements: state.missing,
        route,
        route_source: pvc ? 'AUTO_PERIOD' : (overrides[String(row.id)] ? 'MANUAL' : 'DEFAULT'),
        process_status: processStatus,
        process_status_source: 'FIREBASE_REQUIREMENTS',
        official_graduated: 0,
        official_titulation_completed: upper(row.titulation_status) === 'CUMPLE' ? 1 : 0,
        reconciliation_status: 'OK',
        reconciliation_detail: 'Identidad y requisitos leídos directamente desde Firebase UTET.',
        source_links: [],
      };
    });
    const summary = {
      students: students.length,
      presencial: students.filter(item => item.modality === 'presencial').length,
      online: students.filter(item => item.modality === 'en_linea').length,
      complexive: students.filter(item => item.route === 'COMPLEXIVO').length,
      thesis: students.filter(item => item.route === 'TRABAJO_TITULACION').length,
      article: students.filter(item => item.route === 'ARTICULO').length,
      graduated: students.filter(item => Number(item.official_graduated) === 1).length,
      retired: students.filter(item => item.process_status === 'RETIRADO').length,
      review: students.filter(item => item.reconciliation_status !== 'OK').length,
    };
    return {
      ok: true,
      students,
      summary,
      open_links: [],
      source: 'Firebase UTET',
      cache_mode: dataset.cacheMode,
      synced_at: dataset.loadedAt,
    };
  }

  function nucleiGroupMatches(report, item) {
    const group = fold(item.grupoInforme || item.modalidad || '');
    if (!group) return true;
    const online = /(ONLINE|EN LINEA|EN_LINEA|VIRTUAL)/.test(group);
    return clean(report.modality) === 'en_linea' ? online : !online;
  }

  function nucleiPayload(report, dataset) {
    const rows = (dataset.nuclei || []).filter(item => nucleiGroupMatches(report, item));
    const courses = rows.map(item => {
      const results = Array.isArray(item.resultados) ? item.resultados : [];
      const students = results.map((result, index) => ({
        id: stableId(`${item._id}|${result.cedula || result.correo || index}`),
        full_name: clean(result.nombre || result.nombres || result.cedula || `Estudiante ${index + 1}`),
        email: clean(result.correo).toLowerCase(),
        final_grade: result.notaFinal ?? null,
        final_status: clean(result.estado) || 'No evaluado',
      }));
      const numeric = students.map(s => Number(s.final_grade)).filter(Number.isFinite);
      return {
        id: stableId(item._id),
        career_name: clean(item.carrera) || 'Sin carrera',
        nucleus_number: Number(item.nucleo || 1),
        campus: clean(item.sede),
        module_code: clean(item.modulo),
        period_label: clean(item.periodoCurso),
        group_code: clean(item.paralelo),
        schedule: clean(item.jornada),
        course_key: clean(item.courseKey || item._id),
        course_title: clean(item.curso) || `Núcleo ${Number(item.nucleo || 1)}`,
        teacher_name: clean(item.docente),
        course_average: numeric.length ? numeric.reduce((a, b) => a + b, 0) / numeric.length : null,
        assessments: (Array.isArray(item.actividades) ? item.actividades : []).map(activity => ({
          name: clean(activity.nombre),
          average: activity.promedio ?? null,
        })),
        students,
      };
    });
    const uniqueStudents = new Set();
    courses.forEach(course => course.students.forEach(student => uniqueStudents.add(`${student.full_name}|${student.email}`)));
    return {
      ok: true,
      courses,
      excel_import: courses.length ? {
        students: uniqueStudents.size,
        careers: new Set(courses.map(course => course.career_name)).size,
        imported_rows: courses.reduce((sum, course) => sum + course.students.length, 0),
        courses: courses.length,
        duplicate_rows: 0,
        filename: 'Firebase UTET',
      } : null,
      source: 'Firebase UTET',
      cache_mode: dataset.cacheMode,
    };
  }

  async function cachedPeriodsResponse(force = false) {
    const result = await cached('periods', async () => {
      const response = await previousFetch('/api/firebase/periods', { cache: 'no-store' });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || data?.ok === false) throw new Error(data?.error || `Error ${response.status}`);
      return data;
    }, { force });
    return { ...result.data, cache_mode: result.cache };
  }

  window.fetch = async function firebaseActiveReportFetch(input, init) {
    const path = apiPath(input);
    const method = methodOf(input, init);

    if (path === '/api/firebase/periods' && method === 'GET') {
      try {
        return jsonResponse(await cachedPeriodsResponse(false));
      } catch (error) {
        return jsonResponse({ ok: false, error: clean(error?.message) || 'No se pudo leer Firebase.' }, 503);
      }
    }

    let match = path.match(/^\/api\/reports\/(\d+)\/roster$/);
    if (match && method === 'GET') {
      const report = reportById(Number(match[1]));
      if (!report) return jsonResponse({ ok: false, error: 'Informe no encontrado.' }, 404);
      try {
        const dataset = await loadPeriodDataset(report.firebase_period_id);
        return jsonResponse(rosterPayload(report, dataset));
      } catch (error) {
        return jsonResponse({ ok: false, error: clean(error?.message) || 'No se pudo cargar Requisitos desde Firebase.' }, 503);
      }
    }

    match = path.match(/^\/api\/reports\/(\d+)\/students-domain$/);
    if (match && method === 'GET') {
      const report = reportById(Number(match[1]));
      if (!report) return jsonResponse({ ok: false, error: 'Informe no encontrado.' }, 404);
      try {
        const dataset = await loadPeriodDataset(report.firebase_period_id);
        return jsonResponse(studentsDomainPayload(report, dataset));
      } catch (error) {
        return jsonResponse({ ok: false, error: clean(error?.message) || 'No se pudo cargar Estudiantes desde Firebase.' }, 503);
      }
    }

    match = path.match(/^\/api\/reports\/(\d+)\/students-domain\/sync$/);
    if (match && method === 'POST') {
      const report = reportById(Number(match[1]));
      if (!report) return jsonResponse({ ok: false, error: 'Informe no encontrado.' }, 404);
      try {
        removeCache(`period.${report.firebase_period_id}`);
        forceRefreshUntil = Date.now() + 8000;
        const dataset = await loadPeriodDataset(report.firebase_period_id);
        return jsonResponse(studentsDomainPayload(report, dataset));
      } catch (error) {
        return jsonResponse({ ok: false, error: clean(error?.message) || 'No se pudo sincronizar Firebase.' }, 503);
      }
    }

    match = path.match(/^\/api\/reports\/(\d+)\/students-domain\/(\d+)\/route$/);
    if (match && method === 'PUT') {
      const payload = await bodyOf(input, init);
      const route = clean(payload.route).toUpperCase();
      if (!['COMPLEXIVO', 'TRABAJO_TITULACION'].includes(route)) {
        return jsonResponse({ ok: false, error: 'Ruta de titulación inválida.' }, 400);
      }
      saveRouteOverride(Number(match[1]), Number(match[2]), route);
      return jsonResponse({ ok: true, route });
    }

    match = path.match(/^\/api\/reports\/(\d+)\/nuclei$/);
    if (match && method === 'GET') {
      const report = reportById(Number(match[1]));
      if (!report) return jsonResponse({ ok: false, error: 'Informe no encontrado.' }, 404);
      try {
        const dataset = await loadPeriodDataset(report.firebase_period_id);
        return jsonResponse(nucleiPayload(report, dataset));
      } catch (error) {
        return jsonResponse({ ok: false, error: clean(error?.message) || 'No se pudo cargar Núcleos desde Firebase.' }, 503);
      }
    }

    if (path === '/api/firebase/sync' && method === 'POST') {
      const payload = await bodyOf(input, init);
      const periodId = clean(payload.periodoId || payload.period_id || payload.period);
      const response = await previousFetch(input, init);
      if (response.ok && periodId) {
        removeCache(`period.${periodId}`);
        forceRefreshUntil = Date.now() + 8000;
        loadPeriodDataset(periodId).catch(() => null);
      }
      return response;
    }

    return previousFetch(input, init);
  };

  document.addEventListener('click', event => {
    const button = event.target instanceof Element ? event.target.closest('#refresh-btn, [data-refresh], #firebase-sync-btn') : null;
    if (!button) return;
    forceRefreshUntil = Date.now() + 8000;
    const reportId = Number(window.state?.activeReport?.id || 0);
    const report = reportId ? reportById(reportId) : null;
    if (report?.firebase_period_id) removeCache(`period.${report.firebase_period_id}`);
    removeCache('periods');
  }, true);

  window.informtitFirebaseWebCache = Object.freeze({
    clearPeriod(periodId) {
      removeCache(`period.${clean(periodId)}`);
    },
    clearAll() {
      try {
        Object.keys(window.localStorage)
          .filter(key => key.startsWith(CACHE_PREFIX))
          .forEach(key => window.localStorage.removeItem(key));
      } catch (_) {}
    },
  });
})();
