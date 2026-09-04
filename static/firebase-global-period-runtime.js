(() => {
  'use strict';

  if (!/(^|\.)github\.io$/i.test(window.location.hostname)) return;

  const PROJECT_ID = 'utet-4387a';
  const API_KEY = 'AIzaSyCaHf1C0BB0X_H3BDZ1o-UDAsPmLTjsZLA';
  const FIRESTORE_ROOT = `https://firestore.googleapis.com/v1/projects/${PROJECT_ID}/databases/(default)`;
  const REPORTS_COLLECTION = 'informesTitulacion';
  const REPORTS_KEY = 'informtit.githubPages.reports.v1';
  const previousFetch = window.fetch.bind(window);
  const EMAIL_RE = /^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$/i;
  const NUMBER_RE = /^-?\d{1,3}(?:[.,]\d+)?$/;
  const EXTENDED_SCHEMA = [
    'ordinary_theory', 'ordinary_theory', 'supplementary_theory', 'supplementary_theory',
    'source_total_theory', 'ordinary_practical', 'ordinary_practical',
    'supplementary_practical', 'supplementary_practical', 'source_total_practical',
    'source_total_course',
  ];
  const LEGACY_SCHEMA = [
    'ordinary_theory', 'supplementary_theory', 'source_total_theory',
    'ordinary_practical', 'supplementary_practical', 'source_total_practical',
    'source_total_course',
  ];

  function clean(value) {
    return String(value ?? '').replace(/\u00a0/g, ' ').trim().replace(/\s+/g, ' ');
  }

  function fold(value) {
    return clean(value)
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .toUpperCase();
  }

  function stableId(value) {
    let hash = 2166136261;
    const text = clean(value);
    for (let index = 0; index < text.length; index += 1) {
      hash ^= text.charCodeAt(index);
      hash = Math.imul(hash, 16777619);
    }
    return Math.abs(hash >>> 0) || 1;
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
      throw new Error(`Firebase ${response.status}${detail ? `: ${detail}` : ''}`);
    }
    if (response.status === 204) return {};
    return response.json();
  }

  async function listCollection(collection) {
    const rows = [];
    let pageToken = '';
    do {
      const payload = await firestore(`/documents/${collection}`, {
        allow404: true,
        params: { pageSize: 1000, pageToken },
      }) || {};
      rows.push(...(payload.documents || []).map(decodeDocument));
      pageToken = clean(payload.nextPageToken);
    } while (pageToken);
    return rows;
  }

  async function queryEqual(collection, field, value) {
    try {
      const payload = await firestore('/documents:runQuery', {
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

  async function putDocument(collection, documentId, data) {
    const fields = Object.fromEntries(Object.entries(data).map(([key, value]) => [key, encodeValue(value)]));
    const payload = await firestore(`/documents/${collection}/${encodeURIComponent(documentId)}`, {
      method: 'PATCH',
      body: { fields },
    });
    return decodeDocument(payload);
  }

  async function deleteDocument(collection, documentId) {
    return firestore(`/documents/${collection}/${encodeURIComponent(documentId)}`, {
      method: 'DELETE',
      allow404: true,
    });
  }

  function readLocalReports() {
    try {
      const parsed = JSON.parse(window.localStorage.getItem(REPORTS_KEY) || '[]');
      return Array.isArray(parsed) ? parsed : [];
    } catch (_) {
      return [];
    }
  }

  function writeLocalReports(reports) {
    try { window.localStorage.setItem(REPORTS_KEY, JSON.stringify(reports)); } catch (_) {}
  }

  function reportKey(report) {
    const type = clean(report?.report_type).toLowerCase() === 'pvc' ? 'pvc' : 'normal';
    return `${type}:${clean(report?.firebase_period_id) || fold(report?.period)}`;
  }

  function reportDocumentId(report) {
    return reportKey(report).replace(/[^A-Za-z0-9_-]+/g, '_').slice(0, 180);
  }

  function reportMetadata(report) {
    return {
      periodKey: reportKey(report),
      periodId: clean(report.firebase_period_id),
      period: clean(report.period),
      name: clean(report.name),
      reportType: clean(report.report_type) || 'normal',
      version: clean(report.version) || '1.0',
      elaborationDate: clean(report.elaboration_date),
      codePresencial: clean(report.code_presencial || report.code),
      codeOnline: clean(report.code_online),
      active: true,
      updatedAt: new Date().toISOString(),
    };
  }

  function metadataToReport(row, existing = null) {
    const base = existing || {};
    const reportType = clean(row.reportType).toLowerCase() === 'pvc' ? 'pvc' : 'normal';
    return {
      ...base,
      id: Number(base.id || stableId(row.periodKey || row.periodId || row.period)),
      name: clean(row.name) || clean(base.name) || 'Informe Final del Proceso de Titulación',
      period: clean(row.period) || clean(base.period),
      firebase_period_id: clean(row.periodId) || clean(base.firebase_period_id),
      report_type: reportType,
      modality: reportType === 'pvc' ? 'presencial' : 'unified',
      unified_period: reportType !== 'pvc',
      version: clean(row.version) || '1.0',
      elaboration_date: clean(row.elaborationDate),
      code: clean(row.codePresencial),
      code_presencial: clean(row.codePresencial),
      code_online: reportType === 'pvc' ? '' : clean(row.codeOnline),
      storage_mode: 'firebase_period_global',
      updated_at: clean(row.updatedAt) || new Date().toISOString(),
      careers: Array.isArray(base.careers) ? base.careers : [],
      images: Array.isArray(base.images) ? base.images : [],
      sections: Array.isArray(base.sections) ? base.sections : [],
    };
  }

  async function syncReportsFromFirebase() {
    const local = readLocalReports();
    let remote = [];
    try {
      remote = (await listCollection(REPORTS_COLLECTION)).filter(item => item.active !== false);
    } catch (error) {
      return { reports: local, remote: false, error: error.message };
    }

    const localByKey = new Map(local.map(report => [reportKey(report), report]));
    const merged = remote.map(row => metadataToReport(row, localByKey.get(clean(row.periodKey)) || null));
    const remoteKeys = new Set(merged.map(reportKey));
    local.forEach(report => {
      if (!remoteKeys.has(reportKey(report))) merged.push(report);
    });
    writeLocalReports(merged);

    // Migra una sola vez los informes existentes del navegador a Firebase.
    for (const report of merged) {
      if (remoteKeys.has(reportKey(report))) continue;
      try { await putDocument(REPORTS_COLLECTION, reportDocumentId(report), reportMetadata(report)); } catch (_) {}
    }
    return { reports: merged, remote: true, error: '' };
  }

  async function persistReport(report) {
    if (!report) return;
    try {
      await putDocument(REPORTS_COLLECTION, reportDocumentId(report), reportMetadata(report));
      report.firebase_metadata_synced = true;
      report.firebase_metadata_error = '';
    } catch (error) {
      report.firebase_metadata_synced = false;
      report.firebase_metadata_error = error.message;
    }
  }

  function findReport(reportId) {
    return readLocalReports().find(report => Number(report.id) === Number(reportId)
      || (report.legacy_report_ids || []).some(id => Number(id) === Number(reportId))) || null;
  }

  async function masterStudents(report) {
    try {
      const response = await previousFetch(`/api/reports/${Number(report.id)}/roster`, { cache: 'no-store' });
      const payload = await response.json();
      return Array.isArray(payload.students) ? payload.students : [];
    } catch (_) {
      return [];
    }
  }

  function buildMaster(students) {
    const byId = new Map();
    const byEmail = new Map();
    const byName = new Map();
    students.forEach(student => {
      const modality = clean(student.modality) || 'presencial';
      const identification = clean(student.identification || student.cedula);
      const email = clean(student.email || student.personal_email).toLowerCase();
      const name = fold(student.full_name || student.nombre || student.nombres);
      if (identification) byId.set(identification, modality);
      if (email) byEmail.set(email, modality);
      if (name) {
        if (!byName.has(name)) byName.set(name, modality);
        else if (byName.get(name) !== modality) byName.set(name, 'ambiguous');
      }
    });
    return { byId, byEmail, byName };
  }

  function resolveModality(row, master, fallback = '') {
    const identification = clean(row.identification || row.cedula || row.estudianteCedula || row.cedulaEstudiante);
    const email = clean(row.email || row.correo || row.correoInstitucional || row.correoPersonal).toLowerCase();
    const name = fold(row.full_name || row.nombre || row.nombres || row.nombreEstudiante || row.estudiante);
    if (identification && master.byId.has(identification)) return master.byId.get(identification);
    if (email && master.byEmail.has(email)) return master.byEmail.get(email);
    if (name && master.byName.has(name) && master.byName.get(name) !== 'ambiguous') return master.byName.get(name);
    const text = fold([row.modalidad, row.grupoInforme, row.carrera, row.nombreCarrera, fallback].filter(Boolean).join(' '));
    return /(ONLINE|EN LINEA|EN_LINEA|VIRTUAL)/.test(text) ? 'en_linea' : 'presencial';
  }

  function normalizeStudent(raw, defaults, master) {
    const identification = clean(raw.cedula || raw.identificacion || raw.identification || raw.estudianteCedula || raw.cedulaEstudiante);
    const email = clean(raw.correo || raw.email || raw.correoInstitucional || raw.correoPersonal).toLowerCase();
    const fullName = clean(raw.nombre || raw.nombres || raw.full_name || raw.nombreEstudiante || raw.estudiante || identification || email);
    const modality = resolveModality({ ...raw, identification, email, full_name: fullName }, master, defaults.career_name);
    return {
      id: stableId(`${identification}|${email}|${fullName}`),
      identification,
      cedula: identification,
      full_name: fullName,
      email,
      career_name: defaults.career_name,
      modality,
      ordinary_theory: numeric(raw.ordinary_theory ?? raw.teoricoOrdinario ?? raw.teorico),
      supplementary_theory: numeric(raw.supplementary_theory ?? raw.teoricoSupletorio),
      ordinary_practical: numeric(raw.ordinary_practical ?? raw.practicoOrdinario ?? raw.practico),
      supplementary_practical: numeric(raw.supplementary_practical ?? raw.practicoSupletorio),
      source_total_theory: numeric(raw.source_total_theory ?? raw.totalTeorico),
      source_total_practical: numeric(raw.source_total_practical ?? raw.totalPractico),
      source_total_course: numeric(raw.source_total_course ?? raw.totalCurso ?? raw.notaFinal ?? raw.nota_final ?? raw.final),
    };
  }

  function numeric(value) {
    if (value === null || value === undefined || value === '') return null;
    const number = Number(String(value).replace(',', '.'));
    return Number.isFinite(number) ? number : null;
  }

  function finishGrades(student) {
    const ordinary = student.source_total_course ?? (
      student.ordinary_theory != null && student.ordinary_practical != null
        ? (student.ordinary_theory * 0.4) + (student.ordinary_practical * 0.6)
        : null
    );
    const supplementary = student.supplementary_theory != null && student.supplementary_practical != null
      ? (student.supplementary_theory * 0.4) + (student.supplementary_practical * 0.6)
      : null;
    const finalGrade = supplementary ?? ordinary;
    return {
      ...student,
      ordinary_final: ordinary,
      supplementary_final: supplementary,
      final_grade: finalGrade,
      final_status: finalGrade == null ? 'No evaluado' : finalGrade >= 7 ? 'Aprobado' : 'Reprobado',
      source_difference: null,
    };
  }

  function flattenComplexive(rows) {
    const result = [];
    rows.filter(item => !item.eliminado).forEach(item => {
      const careerName = clean(item.carrera || item.nombreCarrera || item.career_name || item.carreraNombre || 'Sin carrera');
      const nested = Array.isArray(item.resultados) ? item.resultados : Array.isArray(item.estudiantes) ? item.estudiantes : null;
      if (nested) nested.forEach(student => result.push({ raw: { ...student, modalidad: student.modalidad || item.modalidad }, careerName, source: item }));
      else result.push({ raw: item, careerName, source: item });
    });
    return result;
  }

  async function complexiveCareers(report) {
    const [rows, roster] = await Promise.all([
      queryEqual('complexivo', 'periodoId', report.firebase_period_id).catch(() => []),
      masterStudents(report),
    ]);
    const master = buildMaster(roster);
    const groups = new Map();
    flattenComplexive(rows).forEach(({ raw, careerName }) => {
      const key = fold(careerName);
      if (!groups.has(key)) {
        groups.set(key, {
          id: stableId(`${report.firebase_period_id}|${key}`),
          report_id: report.id,
          name: careerName,
          students: [],
          analyses: {},
        });
      }
      const career = groups.get(key);
      const student = finishGrades(normalizeStudent(raw, { career_name: careerName }, master));
      const identity = clean(student.identification || student.email || fold(student.full_name));
      const existing = career.students.find(item => clean(item.identification || item.email || fold(item.full_name)) === identity);
      if (existing) Object.assign(existing, student);
      else career.students.push(student);
    });
    return [...groups.values()].sort((a, b) => a.name.localeCompare(b.name, 'es'));
  }

  function isNumericPlaceholder(value) {
    const text = clean(value);
    return ['-', '–', '—'].includes(text) || NUMBER_RE.test(text.replace(/\s/g, ''));
  }

  function parseNumber(value) {
    const text = clean(value);
    if (!text || ['-', '–', '—'].includes(text)) return null;
    const normalized = text.includes(',') ? text.replace(/\./g, '').replace(',', '.') : text;
    const number = Number(normalized);
    return Number.isFinite(number) ? number : null;
  }

  function cleanName(value) {
    return clean(value)
      .replace(/Matriculaci[oó]n de usuarios suspendida.*$/i, '')
      .replace(/Retroalimentaci[oó]n proporcionada.*$/i, '')
      .replace(/Suspendido Base de datos externa Dar de baja.*$/i, '')
      .trim();
  }

  function parseMoodle(text) {
    const lines = String(text || '').split(/\r?\n/).map(clean).filter(line => line && fold(line) !== 'OCULTAR');
    const emailPositions = lines.map((line, index) => EMAIL_RE.test(line) ? index : -1).filter(index => index >= 0);
    const students = [];
    emailPositions.forEach((emailIndex, position) => {
      const email = lines[emailIndex].toLowerCase();
      let fullName = 'ESTUDIANTE SIN NOMBRE';
      for (let index = emailIndex - 1; index >= 0; index -= 1) {
        const candidate = cleanName(lines[index]);
        if (!candidate || EMAIL_RE.test(candidate) || isNumericPlaceholder(candidate)) continue;
        const f = fold(candidate);
        if (f.includes('NOMBRE / APELLIDO') || f.includes('DIRECCION DE CORREO') || f.includes('COMPONENTE') || f.includes('TOTAL')) continue;
        fullName = candidate;
        break;
      }
      const end = position + 1 < emailPositions.length ? emailPositions[position + 1] : lines.length;
      const values = lines.slice(emailIndex + 1, end).filter(isNumericPlaceholder);
      const schema = values.length >= EXTENDED_SCHEMA.length ? EXTENDED_SCHEMA : LEGACY_SCHEMA;
      const parsed = values.slice(0, schema.length).map(parseNumber);
      const first = field => {
        const index = schema.findIndex(item => item === field);
        return index >= 0 ? parsed[index] : null;
      };
      students.push(finishGrades({
        full_name: fullName,
        email,
        ordinary_theory: first('ordinary_theory'),
        supplementary_theory: first('supplementary_theory'),
        source_total_theory: first('source_total_theory'),
        ordinary_practical: first('ordinary_practical'),
        supplementary_practical: first('supplementary_practical'),
        source_total_practical: first('source_total_practical'),
        source_total_course: first('source_total_course'),
      }));
    });
    return students;
  }

  async function saveComplexiveGlobal(report, careerName, text) {
    const roster = await masterStudents(report);
    const master = buildMaster(roster);
    const parsed = parseMoodle(text);
    if (!parsed.length) throw new Error('No se detectaron estudiantes válidos en el texto pegado.');
    const saved = [];
    for (const raw of parsed) {
      const modality = resolveModality(raw, master, careerName);
      const student = { ...raw, modality, career_name: careerName };
      const documentId = `${report.firebase_period_id}__${stableId(`${careerName}|${raw.email}|${raw.full_name}`)}`;
      const payload = {
        periodoId: report.firebase_period_id,
        carrera: careerName,
        cedula: clean(raw.identification),
        nombre: raw.full_name,
        correo: raw.email,
        modalidad,
        ordinary_theory: raw.ordinary_theory,
        supplementary_theory: raw.supplementary_theory,
        ordinary_practical: raw.ordinary_practical,
        supplementary_practical: raw.supplementary_practical,
        source_total_theory: raw.source_total_theory,
        source_total_practical: raw.source_total_practical,
        source_total_course: raw.source_total_course,
        notaFinal: raw.final_grade,
        estado: raw.final_status,
        fuente: 'Informtit GitHub Pages',
        updatedAt: new Date().toISOString(),
        eliminado: false,
      };
      await putDocument('complexivo', documentId, payload);
      saved.push(student);
    }
    return saved;
  }

  async function nucleiGlobal(report) {
    const [rows, roster] = await Promise.all([
      queryEqual('nucleos', 'periodoId', report.firebase_period_id).catch(() => []),
      masterStudents(report),
    ]);
    const master = buildMaster(roster);
    const courses = [];
    rows.filter(item => !item.eliminado).forEach(item => {
      const results = Array.isArray(item.resultados) ? item.resultados : [];
      const careerName = clean(item.carrera || item.nombreCarrera || item.career_name || 'Sin carrera');
      const students = results.map((raw, index) => {
        const identification = clean(raw.cedula || raw.identificacion || raw.identification);
        const email = clean(raw.correo || raw.email).toLowerCase();
        const fullName = clean(raw.nombre || raw.nombres || raw.full_name || identification || `Estudiante ${index + 1}`);
        return {
          id: stableId(`${item._id}|${identification}|${email}|${fullName}`),
          identification,
          cedula: identification,
          full_name: fullName,
          email,
          final_grade: raw.notaFinal ?? raw.nota_final ?? null,
          final_status: clean(raw.estado) || 'No evaluado',
          modality: resolveModality({ ...raw, identification, email, full_name: fullName, carrera: careerName }, master, item.modalidad || item.grupoInforme),
        };
      });
      const numericGrades = students.map(student => Number(student.final_grade)).filter(Number.isFinite);
      const modalityCounts = {
        presencial: students.filter(student => student.modality === 'presencial').length,
        en_linea: students.filter(student => student.modality === 'en_linea').length,
      };
      courses.push({
        id: stableId(item._id),
        career_name: careerName,
        nucleus_number: Number(item.nucleo || item.numeroNucleo || 1),
        campus: clean(item.sede),
        module_code: clean(item.modulo),
        period_label: clean(item.periodoCurso || item.periodo),
        group_code: clean(item.paralelo),
        schedule: clean(item.jornada || item.horario),
        course_key: clean(item.courseKey || item._id),
        course_title: clean(item.curso || item.materia) || `Núcleo ${Number(item.nucleo || 1)}`,
        teacher_name: clean(item.docente || item.profesor),
        course_average: numericGrades.length ? numericGrades.reduce((a, b) => a + b, 0) / numericGrades.length : null,
        students,
        modality: modalityCounts.presencial && modalityCounts.en_linea ? 'mixto' : modalityCounts.en_linea ? 'en_linea' : 'presencial',
        modality_counts: modalityCounts,
      });
    });
    const identities = new Set();
    courses.forEach(course => course.students.forEach(student => identities.add(clean(student.identification || student.email || fold(student.full_name)))));
    return {
      ok: true,
      courses,
      excel_import: courses.length ? {
        students: identities.size,
        careers: new Set(courses.map(course => course.career_name)).size,
        imported_rows: courses.reduce((sum, course) => sum + course.students.length, 0),
        courses: courses.length,
        duplicate_rows: 0,
        filename: 'Firebase UTET · carga global',
      } : null,
      source: 'Firebase UTET · período global',
    };
  }

  function mapProject(item, report, master) {
    const identification = clean(item.cedula || item.identificacion || item.identification || item.estudianteCedula);
    const fullName = clean(item.nombre || item.nombres || item.full_name || item.nombreEstudiante || identification);
    const careerName = clean(item.carrera || item.nombreCarrera || item.career_name || 'Sin carrera');
    const modality = resolveModality({ ...item, identification, full_name: fullName, carrera: careerName }, master, item.modalidad);
    const finalGrade = numeric(item.notaFinal ?? item.final_grade ?? item.calificacionFinal);
    return {
      id: stableId(item._id || `${identification}|${fullName}`),
      firebase_id: item._id,
      identification,
      full_name: fullName,
      career_name: careerName,
      modality,
      tutor_grade: numeric(item.notaTutor ?? item.tutor_grade),
      reader_grade: numeric(item.notaLector ?? item.reader_grade),
      written_average: numeric(item.promedioEscrito ?? item.written_average),
      practical_average: numeric(item.promedioPractico ?? item.practical_average),
      defense_average: numeric(item.promedioDefensa ?? item.defense_average),
      oral_average: numeric(item.promedioOral ?? item.oral_average),
      final_grade: finalGrade,
      act_number: clean(item.numeroActa || item.act_number),
      act_date: clean(item.fechaActa || item.act_date),
      vocal_1: clean(item.vocal1 || item.vocal_1),
      vocal_2: clean(item.vocal2 || item.vocal_2),
      vocal_3: clean(item.vocal3 || item.vocal_3),
      scores: Array.isArray(item.scores) ? item.scores : [],
    };
  }

  async function projectsGlobal(report) {
    const [rows, roster] = await Promise.all([
      queryEqual('trabajoTitulacion', 'periodoId', report.firebase_period_id).catch(() => []),
      masterStudents(report),
    ]);
    const master = buildMaster(roster);
    const projects = rows.filter(item => !item.eliminado).map(item => mapProject(item, report, master));
    const grades = projects.map(project => Number(project.final_grade)).filter(Number.isFinite);
    return {
      ok: true,
      projects,
      summary: {
        total: projects.length,
        approved: projects.filter(project => project.final_grade != null && Number(project.final_grade) >= 7).length,
        failed: projects.filter(project => project.final_grade != null && Number(project.final_grade) < 7).length,
        average_final: grades.length ? grades.reduce((a, b) => a + b, 0) / grades.length : null,
      },
      source: 'Firebase UTET · período global',
    };
  }

  function extractProjectGrades(text) {
    const source = String(text || '');
    const labels = [
      ['notaTutor', /(?:nota\s+)?tutor\s*[:=-]?\s*(\d+(?:[.,]\d+)?)/i],
      ['notaLector', /(?:nota\s+)?lector\s*[:=-]?\s*(\d+(?:[.,]\d+)?)/i],
      ['promedioEscrito', /(?:trabajo\s+escrito|promedio\s+escrito)\s*[:=-]?\s*(\d+(?:[.,]\d+)?)/i],
      ['promedioPractico', /(?:pr[aá]ctica|promedio\s+pr[aá]ctico)\s*[:=-]?\s*(\d+(?:[.,]\d+)?)/i],
      ['promedioDefensa', /(?:defensa|promedio\s+defensa)\s*[:=-]?\s*(\d+(?:[.,]\d+)?)/i],
      ['promedioOral', /(?:defensa\s+oral|promedio\s+oral)\s*[:=-]?\s*(\d+(?:[.,]\d+)?)/i],
      ['notaFinal', /(?:calificaci[oó]n|nota)\s+final\s*[:=-]?\s*(\d+(?:[.,]\d+)?)/i],
    ];
    return Object.fromEntries(labels.map(([key, regex]) => {
      const match = regex.exec(source);
      return [key, match ? numeric(match[1]) : null];
    }));
  }

  async function saveProjectGlobal(report, payload) {
    const identification = clean(payload.identification);
    if (!identification) throw new Error('La cédula es obligatoria.');
    const roster = await masterStudents(report);
    const master = buildMaster(roster);
    const grades = extractProjectGrades(payload.text);
    const modality = resolveModality({
      identification,
      full_name: payload.full_name,
      carrera: payload.career_name,
    }, master, payload.career_name);
    const documentId = `${report.firebase_period_id}__${identification}`;
    const data = {
      periodoId: report.firebase_period_id,
      cedula: identification,
      nombre: clean(payload.full_name),
      carrera: clean(payload.career_name),
      modalidad,
      ...grades,
      textoFuente: String(payload.text || ''),
      fuente: 'Informtit GitHub Pages',
      updatedAt: new Date().toISOString(),
      eliminado: false,
    };
    await putDocument('trabajoTitulacion', documentId, data);
    return { ...data, final_grade: grades.notaFinal };
  }

  function careerNameById(report, careerId) {
    return clean((report?.careers || []).find(career => Number(career.id) === Number(careerId))?.name);
  }

  async function enrichReport(report) {
    if (!report || clean(report.report_type).toLowerCase() === 'pvc' || !report.firebase_period_id) return report;
    try {
      const careers = await complexiveCareers(report);
      const updated = { ...report, careers, career_count: careers.length };
      const identities = new Set();
      careers.forEach(career => career.students.forEach(student => identities.add(clean(student.identification || student.email || fold(student.full_name)))));
      updated.complexive_records = identities.size;
      updated.student_count = Math.max(Number(updated.student_count || 0), identities.size);
      updated.modality = 'unified';
      updated.unified_period = true;
      const reports = readLocalReports();
      const index = reports.findIndex(item => Number(item.id) === Number(report.id));
      if (index >= 0) {
        reports[index] = { ...reports[index], careers, career_count: careers.length, complexive_records: identities.size };
        writeLocalReports(reports);
      }
      return updated;
    } catch (_) {
      return report;
    }
  }

  window.fetch = async function firebaseGlobalPeriodFetch(input, init) {
    const path = pathOf(input);
    const method = methodOf(input, init);

    if (path === '/api/reports' && method === 'GET') {
      await syncReportsFromFirebase();
      return previousFetch(input, init);
    }

    if (path === '/api/reports' && method === 'POST') {
      const response = await previousFetch(input, init);
      if (!response.ok) return response;
      const result = await response.clone().json().catch(() => ({}));
      const report = findReport(result.report_id);
      if (report) await persistReport(report);
      return response;
    }

    let match = path.match(/^\/api\/reports\/(\d+)$/);
    if (match) {
      const reportId = Number(match[1]);
      if (method === 'GET') {
        const response = await previousFetch(input, init);
        if (!response.ok) return response;
        const payload = await response.json().catch(() => ({}));
        if (!payload.report) return jsonResponse(payload, response.status);
        payload.report = await enrichReport(payload.report);
        return jsonResponse(payload, response.status);
      }
      if (method === 'PUT') {
        const response = await previousFetch(input, init);
        if (response.ok) {
          const report = findReport(reportId);
          if (report) await persistReport(report);
        }
        return response;
      }
      if (method === 'DELETE') {
        const report = findReport(reportId);
        const response = await previousFetch(input, init);
        if (response.ok && report) {
          try { await deleteDocument(REPORTS_COLLECTION, reportDocumentId(report)); } catch (_) {}
        }
        return response;
      }
    }

    match = path.match(/^\/api\/reports\/(\d+)\/nuclei$/);
    if (match && method === 'GET') {
      const report = findReport(Number(match[1]));
      if (!report?.firebase_period_id || clean(report.report_type).toLowerCase() === 'pvc') return previousFetch(input, init);
      try { return jsonResponse(await nucleiGlobal(report)); }
      catch (error) { return jsonResponse({ ok: false, error: error.message }, 503); }
    }

    match = path.match(/^\/api\/reports\/(\d+)\/projects$/);
    if (match && method === 'GET') {
      const report = findReport(Number(match[1]));
      if (!report?.firebase_period_id) return previousFetch(input, init);
      try { return jsonResponse(await projectsGlobal(report)); }
      catch (error) { return jsonResponse({ ok: false, error: error.message }, 503); }
    }

    match = path.match(/^\/api\/reports\/(\d+)\/projects\/parse$/);
    if (match && method === 'POST') {
      const report = findReport(Number(match[1]));
      if (!report?.firebase_period_id) return previousFetch(input, init);
      try {
        const payload = await bodyOf(input, init);
        const saved = await saveProjectGlobal(report, payload);
        return jsonResponse({ ok: true, final_grade: saved.final_grade, project: saved }, 201);
      } catch (error) {
        return jsonResponse({ ok: false, error: error.message }, 400);
      }
    }

    match = path.match(/^\/api\/reports\/(\d+)\/projects\/(\d+)$/);
    if (match && method === 'DELETE') {
      const report = findReport(Number(match[1]));
      if (!report?.firebase_period_id) return previousFetch(input, init);
      try {
        const rows = await queryEqual('trabajoTitulacion', 'periodoId', report.firebase_period_id);
        const target = rows.find(item => stableId(item._id || `${clean(item.cedula)}|${clean(item.nombre)}`) === Number(match[2]));
        if (!target?._id) throw new Error('Registro no encontrado en Firebase.');
        await deleteDocument('trabajoTitulacion', target._id);
        return jsonResponse({ ok: true, deleted_id: Number(match[2]) });
      } catch (error) {
        return jsonResponse({ ok: false, error: error.message }, 404);
      }
    }

    match = path.match(/^\/api\/careers\/(\d+)\/parse$/);
    if (match && method === 'POST') {
      const report = typeof state !== 'undefined' ? state.activeReport : null;
      if (!report?.firebase_period_id || clean(report.report_type).toLowerCase() === 'pvc') return previousFetch(input, init);
      try {
        const payload = await bodyOf(input, init);
        const careerName = careerNameById(report, Number(match[1]));
        if (!careerName) throw new Error('No se pudo identificar la carrera del período global.');
        const students = await saveComplexiveGlobal(report, careerName, payload.text);
        const enriched = await complexiveCareers(report);
        const reports = readLocalReports();
        const index = reports.findIndex(item => Number(item.id) === Number(report.id));
        if (index >= 0) {
          reports[index].careers = enriched;
          reports[index].career_count = enriched.length;
          writeLocalReports(reports);
        }
        return jsonResponse({
          ok: true,
          inserted: students.length,
          detected: students.length,
          warnings: [],
          mode: 'firebase_global_period',
        }, 201);
      } catch (error) {
        return jsonResponse({ ok: false, error: error.message }, 400);
      }
    }

    return previousFetch(input, init);
  };

  window.informtitFirebaseGlobalPeriod = Object.freeze({
    syncReportsFromFirebase,
    complexiveCareers,
    nucleiGlobal,
    projectsGlobal,
  });
})();