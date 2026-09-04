(() => {
  'use strict';

  if (!/(^|\.)github\.io$/i.test(window.location.hostname)) return;

  const PROJECT_ID = 'utet-4387a';
  const API_KEY = 'AIzaSyCaHf1C0BB0X_H3BDZ1o-UDAsPmLTjsZLA';
  const FIRESTORE_ROOT = `https://firestore.googleapis.com/v1/projects/${PROJECT_ID}/databases/(default)`;
  const REPORTS_KEY = 'informtit.githubPages.reports.v1';
  const previousFetch = window.fetch.bind(window);

  function clean(value) {
    return String(value ?? '').replace(/\\@/g, '@').replace(/\u00a0/g, ' ').trim().replace(/\s+/g, ' ');
  }

  function fold(value) {
    return clean(value).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toUpperCase();
  }

  function stableId(value) {
    let hash = 2166136261;
    const text = String(value || '');
    for (let index = 0; index < text.length; index += 1) {
      hash ^= text.charCodeAt(index);
      hash = Math.imul(hash, 16777619);
    }
    return Math.abs(hash >>> 0) || 1;
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
    const row = Object.fromEntries(Object.entries(document?.fields || {}).map(([key, value]) => [key, decodeValue(value)]));
    row._id = clean(document?.name).split('/').pop() || '';
    row._updateTime = document?.updateTime || '';
    return row;
  }

  async function firestore(path, options = {}) {
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
    if (!response.ok) {
      let detail = '';
      try { detail = clean((await response.json())?.error?.message); } catch (_) {}
      throw new Error(`Firebase ${response.status}${detail ? `: ${detail}` : ''}`);
    }
    return response.status === 204 ? {} : response.json();
  }

  async function queryPeriod(periodId) {
    try {
      const payload = await firestore('/documents:runQuery', {
        method: 'POST',
        body: {
          structuredQuery: {
            from: [{ collectionId: 'nucleos' }],
            where: {
              fieldFilter: {
                field: { fieldPath: 'periodoId' },
                op: 'EQUAL',
                value: encodeValue(periodId),
              },
            },
          },
        },
      });
      return (payload || []).filter(item => item.document).map(item => decodeDocument(item.document));
    } catch (_) {
      return [];
    }
  }

  async function putDocument(documentId, data) {
    const fields = Object.fromEntries(Object.entries(data).map(([key, value]) => [key, encodeValue(value)]));
    return firestore(`/documents/nucleos/${encodeURIComponent(documentId)}`, {
      method: 'PATCH',
      body: { fields },
    });
  }

  function reportById(reportId) {
    try {
      const reports = JSON.parse(localStorage.getItem(REPORTS_KEY) || '[]');
      return (Array.isArray(reports) ? reports : []).find(report => Number(report.id) === Number(reportId)
        || (report.legacy_report_ids || []).some(id => Number(id) === Number(reportId))) || null;
    } catch (_) {
      return null;
    }
  }

  async function requestPayload(input, init) {
    if (typeof init?.body === 'string') {
      try { return JSON.parse(init.body); } catch (_) { return {}; }
    }
    if (input instanceof Request) {
      try { return await input.clone().json(); } catch (_) {}
    }
    return {};
  }

  function pathOf(input) {
    try {
      const raw = typeof input === 'string' ? input : input?.url;
      return new URL(raw, window.location.href).pathname;
    } catch (_) { return ''; }
  }

  function methodOf(input, init) {
    return String(init?.method || input?.method || 'GET').toUpperCase();
  }

  async function jsonData(response) {
    return response.clone().json().catch(() => ({}));
  }

  function gradeStatus(value) {
    const grade = Number(value);
    return Number.isFinite(grade) ? (grade >= 7 ? 'APROBADO' : 'REPROBADO') : 'NO EVALUADO';
  }

  function officialStudentIndexes(students) {
    const byEmail = new Map();
    const byId = new Map();
    (students || []).forEach(student => {
      const email = clean(student.email || student.personal_email).toLowerCase();
      const id = clean(student.identification || student.cedula);
      if (email) byEmail.set(email, student);
      if (id) byId.set(id, student);
    });
    return { byEmail, byId };
  }

  async function syncPasteToCanonical(reportId, payload, result) {
    const report = reportById(reportId);
    const periodId = clean(report?.firebase_period_id);
    if (!periodId) throw new Error('El período no tiene identificador Firebase.');

    const parser = window.informtitNucleiPaste?.parseRows;
    const rows = typeof parser === 'function' ? parser(payload?.text || '') : [];
    if (!Array.isArray(rows) || !rows.length) throw new Error('No se pudieron preparar las notas para el almacenamiento compartido.');

    const studentsResponse = await previousFetch(`/api/reports/${reportId}/students-domain`, { cache: 'no-store' });
    const studentsPayload = await studentsResponse.json().catch(() => ({}));
    const indexes = officialStudentIndexes(studentsPayload.students || []);
    const assignment = result.assignment || {};
    const nucleus = Number(assignment.nucleus || payload?.nucleus_number || 0);
    if (![1, 2, 3, 4].includes(nucleus)) throw new Error('No se pudo determinar el Núcleo para sincronizar Firebase.');

    let written = 0;
    let pending = 0;
    const now = new Date().toISOString();

    for (const row of rows) {
      const email = clean(row.email).toLowerCase();
      const official = indexes.byEmail.get(email);
      const cedula = clean(official?.identification || official?.cedula);
      const grade = Number(row.final_grade);
      if (!official || !cedula || !Number.isFinite(grade)) {
        pending += 1;
        continue;
      }
      const courseId = Number(assignment.course_id || 0);
      const courseKey = courseId
        ? `moodle:${courseId}`
        : `shared:${fold(assignment.career || official.career_name)}:${nucleus}:${fold(assignment.campus || official.campus)}`;
      const docId = `${periodId}__${cedula}__N${nucleus}`;
      await putDocument(docId, {
        periodoId: periodId,
        cedula,
        nucleo: nucleus,
        notaFinal: Math.round(grade * 100) / 100,
        estado: gradeStatus(grade),
        nombre: clean(official.full_name || row.raw_name || cedula),
        correo: email,
        carrera: clean(official.career_name || assignment.career),
        sede: clean(official.campus || assignment.campus),
        modalidad: clean(official.modality),
        courseKey,
        curso: clean(assignment.subject) || `Núcleo ${nucleus}`,
        source: 'Informtit GitHub Pages',
        version: 2,
        updatedAt: now,
        eliminado: false,
      });
      written += 1;
    }

    return { written, pending, period_id: periodId };
  }

  function canonicalRows(rows) {
    return (rows || []).filter(row => clean(row.cedula) && [1, 2, 3, 4].includes(Number(row.nucleo)) && row.notaFinal !== undefined && row.notaFinal !== null);
  }

  function recalcCourse(course) {
    const students = Array.isArray(course.students) ? course.students : [];
    const grades = students.map(item => Number(item.final_grade)).filter(Number.isFinite);
    course.participant_students = students.length;
    course.graded_students = grades.length;
    course.matched_students = students.length;
    course.missing_grades = Math.max(students.length - grades.length, 0);
    course.course_average = grades.length ? Math.round((grades.reduce((sum, value) => sum + value, 0) / grades.length) * 100) / 100 : null;
    course.approved_count = students.filter(item => fold(item.final_status) === 'APROBADO').length;
    course.failed_count = students.filter(item => fold(item.final_status) === 'REPROBADO').length;
    course.unevaluated_count = Math.max(students.length - course.approved_count - course.failed_count, 0);
    return course;
  }

  async function mergeCanonicalIntoNuclei(reportId, payload) {
    const report = reportById(reportId);
    const periodId = clean(report?.firebase_period_id);
    if (!periodId) return payload;

    const [remote, studentsResponse] = await Promise.all([
      queryPeriod(periodId),
      previousFetch(`/api/reports/${reportId}/students-domain`, { cache: 'no-store' }),
    ]);
    const canonical = canonicalRows(remote);
    if (!canonical.length) return payload;

    const studentsPayload = await studentsResponse.json().catch(() => ({}));
    const indexes = officialStudentIndexes(studentsPayload.students || []);
    const courses = Array.isArray(payload.courses) ? payload.courses.map(course => ({ ...course, students: Array.isArray(course.students) ? [...course.students] : [] })) : [];
    const byCourseKey = new Map(courses.map(course => [clean(course.course_key || course.courseKey), course]).filter(([key]) => key));

    for (const remoteRow of canonical) {
      const cedula = clean(remoteRow.cedula);
      const official = indexes.byId.get(cedula) || {};
      const nucleus = Number(remoteRow.nucleo);
      const career = clean(remoteRow.carrera || official.career_name || 'Sin carrera');
      const campus = clean(remoteRow.sede || official.campus);
      const key = clean(remoteRow.courseKey) || `shared:${fold(career)}:${nucleus}:${fold(campus)}`;
      let course = byCourseKey.get(key);
      if (!course) {
        const compatible = courses.filter(item =>
          Number(item.nucleus_number || item.nucleo) === nucleus
          && fold(item.career_name || item.carrera) === fold(career)
          && (!campus || !clean(item.campus || item.sede) || fold(item.campus || item.sede) === fold(campus))
        );
        course = compatible.length === 1 ? compatible[0] : null;
      }
      if (!course) {
        course = {
          id: stableId(`${periodId}|${key}`),
          career_name: career,
          nucleus_number: nucleus,
          campus,
          course_key: key,
          course_title: clean(remoteRow.curso) || `Núcleo ${nucleus}`,
          teacher_name: '',
          students: [],
        };
        courses.push(course);
        byCourseKey.set(key, course);
      }

      const email = clean(remoteRow.correo || official.email).toLowerCase();
      const existingIndex = course.students.findIndex(student =>
        clean(student.identification || student.cedula) === cedula
        || (email && clean(student.email).toLowerCase() === email)
      );
      const student = {
        id: stableId(`${key}|${cedula}`),
        identification: cedula,
        cedula,
        full_name: clean(remoteRow.nombre || official.full_name || cedula),
        email,
        final_grade: Number(remoteRow.notaFinal),
        final_status: clean(remoteRow.estado) || gradeStatus(remoteRow.notaFinal),
        modality: clean(remoteRow.modalidad || official.modality),
        match_status: 'OK',
        match_method: 'FIREBASE_CEDULA',
        match_confidence: 100,
      };
      if (existingIndex >= 0) course.students[existingIndex] = { ...course.students[existingIndex], ...student };
      else course.students.push(student);
    }

    courses.forEach(recalcCourse);
    return { ...payload, courses, shared_firebase: { canonical_students: canonical.length, period_id: periodId } };
  }

  window.fetch = async function sharedNucleiFirebaseFetch(input, init = {}) {
    const path = pathOf(input);
    const method = methodOf(input, init);

    const pasteMatch = path.match(/^\/api\/reports\/(\d+)\/nuclei\/import-text-v2$/);
    if (pasteMatch && method === 'POST') {
      const payload = await requestPayload(input, init);
      const response = await previousFetch(input, init);
      if (!response.ok) return response;
      const result = await jsonData(response);
      try {
        const shared = await syncPasteToCanonical(Number(pasteMatch[1]), payload, result);
        return new Response(JSON.stringify({ ...result, shared_firebase: { ok: true, ...shared } }), {
          status: response.status,
          headers: { 'Content-Type': 'application/json; charset=utf-8' },
        });
      } catch (error) {
        return new Response(JSON.stringify({
          ok: false,
          error: `Las notas se procesaron, pero no se pudo completar la sincronización compartida con Firebase: ${clean(error?.message)}`,
          partial_result: result,
        }), {
          status: 503,
          headers: { 'Content-Type': 'application/json; charset=utf-8' },
        });
      }
    }

    const nucleiMatch = path.match(/^\/api\/reports\/(\d+)\/nuclei$/);
    if (nucleiMatch && method === 'GET') {
      const response = await previousFetch(input, init);
      if (!response.ok) return response;
      const payload = await jsonData(response);
      try {
        const merged = await mergeCanonicalIntoNuclei(Number(nucleiMatch[1]), payload);
        return new Response(JSON.stringify(merged), {
          status: response.status,
          headers: { 'Content-Type': 'application/json; charset=utf-8' },
        });
      } catch (error) {
        console.warn('[Informtit] No se pudieron fusionar Núcleos compartidos.', error);
        return response;
      }
    }

    return previousFetch(input, init);
  };

  window.informtitSharedNucleiFirebase = Object.freeze({
    queryPeriod,
    canonicalRows,
  });
})();