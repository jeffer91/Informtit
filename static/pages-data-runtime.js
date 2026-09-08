(() => {
  'use strict';

  if (!/(^|\.)github\.io$/i.test(window.location.hostname)) return;
  if (!window.InformtitSheets) return;

  const REPORTS_KEY = 'informtit.githubPages.reports.v1';
  const SETTINGS_KEY = 'informtit.sheets.settings.v1';
  const SCHEDULE_PREFIX = 'informtit.sheets.schedules.v1.';
  const previousFetch = window.fetch.bind(window);
  const datasetCache = new Map();
  const periodCache = { rows: null, promise: null };
  const careerLookup = new Map();
  const REQUIREMENTS = [
    ['academic_status', 'academico', 'Académico'],
    ['documentation_status', 'documentacion', 'Documentación'],
    ['financial_status', 'financiero', 'Financiero'],
    ['titulation_status', 'titulacion', 'Titulación'],
    ['practices_linkage_status', 'practicas', 'Prácticas/Vinculación'],
    ['linkage_status', 'vinculacion', 'Vinculación'],
    ['graduate_followup_status', 'seguimientoGraduados', 'Seguimiento a Graduados'],
    ['english_status', 'ingles', 'Inglés'],
    ['data_update_status', 'actualizacionDatos', 'Actualización de Datos'],
  ];

  const clean = value => String(value ?? '').replace(/\u00a0/g, ' ').trim().replace(/\s+/g, ' ');
  const fold = value => clean(value).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toUpperCase();
  const digits = value => clean(value).replace(/\D/g, '');
  const truthy = value => ['TRUE', '1', 'SI', 'SÍ', 'YES'].includes(fold(value));
  const pass = value => ['CUMPLE', 'SI', 'SÍ', 'APROBADO', 'OK', 'TRUE', '1'].includes(fold(value));
  const numeric = value => {
    if (value === null || value === undefined || clean(value) === '' || fold(value) === 'NULL') return null;
    const n = Number(String(value).replace(',', '.'));
    return Number.isFinite(n) ? n : null;
  };
  const stableId = value => {
    let hash = 2166136261;
    for (const ch of clean(value)) { hash ^= ch.charCodeAt(0); hash = Math.imul(hash, 16777619); }
    return Math.abs(hash >>> 0) || 1;
  };
  const pathOf = input => {
    try { return new URL(typeof input === 'string' ? input : input?.url, window.location.href).pathname; }
    catch (_) { return ''; }
  };
  const methodOf = (input, init) => String(init?.method || input?.method || 'GET').toUpperCase();
  const bodyOf = async (input, init) => {
    if (init?.body !== undefined && init?.body !== null) {
      if (typeof init.body === 'string') { try { return JSON.parse(init.body); } catch (_) { return {}; } }
    }
    if (input instanceof Request) { try { return await input.clone().json(); } catch (_) {} }
    return {};
  };
  const jsonResponse = (payload, status = 200) => Promise.resolve(new Response(JSON.stringify(payload), {
    status, headers: { 'Content-Type': 'application/json; charset=utf-8' },
  }));

  function canonicalCareer(value = '') {
    let text = clean(value)
      .replace(/^(?:TECNOLOG[IÍ]A|T[EÉ]CNICO)\s+SUPERIOR(?:\s+UNIVERSITARIA)?\s+EN\s+/i, '')
      .replace(/\s+(?:ONLINE|EN\s+L[IÍ]NEA|VIRTUAL|PRESENCIAL)\s*$/i, '')
      .trim();
    const key = fold(text);
    if (key.includes('REDES') && key.includes('TELECOMUNICACIONES')) return 'REDES Y TELECOMUNICACIONES';
    const aliases = {
      ADMINISTRACION: 'ADMINISTRACIÓN',
      'EDUCACION BASICA': 'EDUCACIÓN BÁSICA',
      'EDUCACION INICIAL': 'EDUCACIÓN INICIAL',
      ENFERMERIA: 'ENFERMERÍA',
      'ESTETICA INTEGRAL': 'ESTÉTICA INTEGRAL',
      'GESTION DEL TALENTO HUMANO': 'GESTIÓN DEL TALENTO HUMANO',
      'MARKETING DIGITAL Y COMERCIO ELECTRONICO': 'MARKETING DIGITAL Y COMERCIO ELECTRÓNICO',
      'SEGURIDAD CIUDADANA Y ORDEN PUBLICO': 'SEGURIDAD CIUDADANA Y ORDEN PÚBLICO',
    };
    return aliases[key] || (text ? text.toLocaleUpperCase('es') : 'SIN CARRERA');
  }

  function inferModality(...values) {
    const text = fold(values.filter(Boolean).join(' '));
    const code = clean(values.find(value => /-[PL]-/i.test(clean(value))) || '').toUpperCase();
    return /(ONLINE|EN LINEA|VIRTUAL)/.test(text) || code.includes('-L-') ? 'en_linea' : 'presencial';
  }

  function rawReports() {
    try { const rows = JSON.parse(localStorage.getItem(REPORTS_KEY) || '[]'); return Array.isArray(rows) ? rows : []; }
    catch (_) { return []; }
  }
  function saveReports(rows) { try { localStorage.setItem(REPORTS_KEY, JSON.stringify(rows)); } catch (_) {} }
  function reportById(id) {
    return rawReports().find(report => Number(report.id) === Number(id)
      || (report.legacy_report_ids || []).some(item => Number(item) === Number(id))) || null;
  }

  async function periods() {
    if (periodCache.rows) return periodCache.rows;
    if (!periodCache.promise) {
      periodCache.promise = window.InformtitSheets.periodos().then(data => {
        periodCache.rows = Array.isArray(data?.periodos) ? data.periodos : [];
        return periodCache.rows;
      }).finally(() => { periodCache.promise = null; });
    }
    return periodCache.promise;
  }

  function periodLabels(period) {
    return [period?.periodoId, period?.id, period?.nombre, period?.label].map(fold).filter(Boolean);
  }

  async function resolvePeriodId(report) {
    const explicit = clean(report?.firebase_period_id || report?.periodoId || report?.period_id);
    if (explicit) return explicit;
    const wanted = fold(report?.period);
    if (!wanted) return '';
    const match = (await periods()).find(period => periodLabels(period).includes(wanted));
    const id = clean(match?.periodoId || match?.id);
    if (id && report?.id) {
      const reports = rawReports();
      const index = reports.findIndex(item => Number(item.id) === Number(report.id));
      if (index >= 0) {
        reports[index].firebase_period_id = id;
        reports[index].periodoId = id;
        saveReports(reports);
        Object.assign(report, { firebase_period_id: id, periodoId: id });
      }
    }
    return id;
  }

  function arrayFrom(data, ...keys) {
    for (const key of keys) if (Array.isArray(data?.[key])) return data[key];
    return [];
  }

  async function loadDataset(periodId, force = false) {
    periodId = clean(periodId);
    if (!periodId) throw new Error('No se pudo identificar el período académico en Google Sheets.');
    const cached = datasetCache.get(periodId);
    if (!force && cached && Date.now() - cached.at < 60000) return cached.data;
    const [studentData, matriculaData, reqData, nucleiData, complexData, workData] = await Promise.all([
      window.InformtitSheets.estudiantes(),
      window.InformtitSheets.matriculas(periodId),
      window.InformtitSheets.requisitos(periodId),
      window.InformtitSheets.nucleos(periodId).catch(() => ({ nucleos: [] })),
      window.InformtitSheets.complexivo(periodId).catch(() => ({ complexivo: [] })),
      window.InformtitSheets.trabajoTitulacion(periodId).catch(() => ({ trabajoTitulacion: [] })),
    ]);
    const data = {
      students: arrayFrom(studentData, 'estudiantes', 'students'),
      enrollments: arrayFrom(matriculaData, 'matriculas', 'enrollments'),
      requirements: arrayFrom(reqData, 'requisitos', 'requirements'),
      nuclei: arrayFrom(nucleiData, 'nucleos', 'rows'),
      complexive: arrayFrom(complexData, 'complexivo', 'rows'),
      work: arrayFrom(workData, 'trabajoTitulacion', 'trabajo_titulacion', 'trabajos', 'rows'),
      syncedAt: new Date().toISOString(),
    };
    datasetCache.set(periodId, { at: Date.now(), data });
    return data;
  }

  function requirementValue(row, key) {
    const aliases = {
      academico: ['academico', 'Academico'], documentacion: ['documentacion', 'Documentacion'],
      financiero: ['financiero', 'Financiero'], titulacion: ['titulacion', 'Titulacion'],
      practicas: ['practicas', 'PracticasVinculacion', 'practicasVinculacion'], vinculacion: ['vinculacion', 'Vinculacion'],
      seguimientoGraduados: ['seguimientoGraduados', 'SeguimientoGraduados'], ingles: ['ingles', 'Ingles'],
      actualizacionDatos: ['actualizacionDatos', 'ActualizacionDatos'],
    };
    for (const alias of aliases[key] || [key]) if (row?.[alias] !== undefined) return clean(row[alias]);
    return '';
  }

  function joinedStudents(data, report) {
    const studentById = new Map();
    data.students.forEach(student => {
      const id = digits(student.cedula || student.identificacion || student.identification);
      if (id) studentById.set(id, student);
    });
    const enrollmentById = new Map();
    data.enrollments.filter(row => !truthy(row.retirado)).forEach(row => {
      const id = digits(row.cedula || row.identificacion || row.identification);
      if (id) enrollmentById.set(id, row);
    });
    const requirementById = new Map();
    data.requirements.forEach(row => {
      const id = digits(row.cedula || row.identificacion || row.identification);
      if (id) requirementById.set(id, row);
    });
    const evidenceIds = new Set();
    [...data.nuclei, ...data.complexive, ...data.work].forEach(row => {
      const id = digits(row.cedula || row.identificacion || row.identification);
      if (id) evidenceIds.add(id);
    });
    let ids = [...new Set([...enrollmentById.keys(), ...requirementById.keys(), ...evidenceIds])];
    if (!ids.length) ids = [...studentById.keys()];
    const pvc = clean(report?.report_type).toLowerCase() === 'pvc';
    return ids.map(id => {
      const student = studentById.get(id) || {};
      const enrollment = enrollmentById.get(id) || {};
      const requirement = requirementById.get(id) || {};
      const careerRaw = clean(student.carrera || student.nombreCarrera || student.nombreCarreraActual || enrollment.carrera || enrollment.nombreCarrera);
      const career = canonicalCareer(careerRaw);
      const modality = pvc ? 'articulo_academico' : clean(enrollment.modalidad || student.modalidad) || inferModality(careerRaw, student.codigoCarrera || student.codigoCarreraActual || enrollment.codigoCarrera);
      const row = {
        id: stableId(id), identification: id, cedula: id,
        full_name: clean(student.nombre || student.nombres || student.full_name || enrollment.nombre || id),
        nombre: clean(student.nombre || student.nombres || student.full_name || enrollment.nombre || id),
        career_code: clean(student.codigoCarrera || student.codigoCarreraActual || enrollment.codigoCarrera),
        career_name: career, carrera: career,
        modality, schedule: clean(enrollment.jornada || enrollment.division || enrollment.horario),
        personal_email: clean(student.correoPersonal || student.personal_email),
        email: clean(student.correoInstitucional || student.email).toLowerCase(),
        phone: clean(student.celular || student.telefono), campus: clean(student.sede || enrollment.sede),
        retired: truthy(enrollment.retirado),
      };
      const pending = [];
      const blank = [];
      REQUIREMENTS.forEach(([output, input, label]) => {
        const value = requirementValue(requirement, input);
        row[output] = fold(value);
        if (fold(value) === 'NO CUMPLE') pending.push(label);
        else if (!pass(value)) blank.push(label);
      });
      row.titulation_approval = fold(requirement.aprobacionTitulacion || requirement.AprobacionTitulacion);
      row.complexive_approval = fold(requirement.aprobacionComplexivo || requirement.aprobacionComplexivoProyecto || requirement.AprobacionComplexivoProyecto);
      row.pending_requirements = pending;
      row.blank_requirements = blank;
      row.requirements_complete = !pending.length && !blank.length;
      row.missing_requirement_labels = [...pending, ...blank];
      row.notes_loaded = data.complexive.some(item => digits(item.cedula) === id) || data.work.some(item => digits(item.cedula) === id);
      const hasNuclei = data.nuclei.some(item => digits(item.cedula) === id);
      const hasComplexive = data.complexive.some(item => digits(item.cedula) === id);
      const hasThesis = data.work.some(item => digits(item.cedula) === id);
      row.route = hasThesis && !hasComplexive && !hasNuclei ? 'TRABAJO_TITULACION' : 'COMPLEXIVO';
      row.process_status = row.retired ? 'RETIRADO' : row.requirements_complete ? 'ACTIVO' : 'NO_APROBADO_REQUISITO';
      row.has_nuclei = hasNuclei; row.has_complexive = hasComplexive; row.has_thesis = hasThesis;
      return row;
    }).filter(row => !row.retired);
  }

  async function contextForReport(reportId, force = false) {
    const report = reportById(reportId) || (typeof state !== 'undefined' && Number(state.activeReport?.id) === Number(reportId) ? state.activeReport : null);
    if (!report) throw new Error('No se encontró el informe activo.');
    const periodId = await resolvePeriodId(report);
    const data = await loadDataset(periodId, force);
    const students = joinedStudents(data, report);
    return { report, periodId, data, students };
  }

  function rosterPayload(context) {
    const rows = context.students;
    const careersMap = new Map();
    const campusesMap = new Map();
    rows.forEach(row => {
      const key = fold(row.career_name);
      if (key && key !== 'SIN CARRERA') careersMap.set(key, { name: row.career_name, students: (careersMap.get(key)?.students || 0) + 1 });
      const campus = clean(row.campus) || 'Sin sede';
      campusesMap.set(fold(campus), { name: campus, students: (campusesMap.get(fold(campus))?.students || 0) + 1 });
    });
    const requirements = REQUIREMENTS.map(([output, , label]) => ({
      label,
      complies: rows.filter(row => pass(row[output])).length,
      does_not_comply: rows.filter(row => !pass(row[output])).length,
    }));
    const complete = rows.filter(row => row.requirements_complete).length;
    return {
      ok: true,
      report: { id: context.report.id, name: context.report.name, period: context.report.period, modality: context.report.modality, report_type: context.report.report_type, periodoId: context.periodId },
      summary: {
        is_imported: rows.length > 0, students: rows.length, careers: careersMap.size,
        requirements_complete: complete, requirements_pending: rows.length - complete,
        notes_loaded: rows.filter(row => row.notes_loaded).length,
        presencial: rows.filter(row => row.modality === 'presencial').length,
        online: rows.filter(row => row.modality === 'en_linea').length,
      },
      requirements,
      careers: [...careersMap.values()].sort((a,b) => a.name.localeCompare(b.name, 'es')),
      campuses: [...campusesMap.values()].sort((a,b) => a.name.localeCompare(b.name, 'es')),
      students: rows,
      source: 'GOOGLE_SHEETS', synced_at: context.data.syncedAt,
    };
  }

  function studentsDomainPayload(context) {
    const rows = context.students.map(row => ({
      ...row,
      missing_requirements: row.missing_requirement_labels,
      official_graduated: 0,
      official_titulation_completed: pass(row.titulation_status) ? 1 : 0,
      reconciliation_status: 'OK',
      reconciliation_detail: 'Consolidado por cédula desde Google Sheets.',
    }));
    return {
      ok: true, students: rows, open_links: [], source: 'GOOGLE_SHEETS', synced_at: context.data.syncedAt,
      summary: {
        students: rows.length,
        presencial: rows.filter(row => row.modality === 'presencial').length,
        online: rows.filter(row => row.modality === 'en_linea').length,
        complexive: rows.filter(row => row.route === 'COMPLEXIVO').length,
        thesis: rows.filter(row => row.route === 'TRABAJO_TITULACION').length,
        graduated: 0,
        retired: 0,
        review: 0,
      },
    };
  }

  function nucleiPayload(context) {
    const official = new Map(context.students.map(row => [row.identification, row]));
    const groups = new Map();
    context.data.nuclei.forEach(source => {
      const id = digits(source.cedula || source.identificacion);
      if (!id) return;
      const base = official.get(id) || {};
      const nucleus = Number(source.nucleo || source.numeroNucleo || 0);
      if (![1,2,3,4].includes(nucleus)) return;
      const career = canonicalCareer(source.carrera || base.career_name || 'SIN CARRERA');
      const key = `${fold(career)}|${nucleus}`;
      if (!groups.has(key)) groups.set(key, { career, nucleus, students: new Map(), teachers: new Set() });
      const group = groups.get(key);
      const grade = numeric(source.notaFinal ?? source.nota_final);
      group.students.set(id, {
        id: stableId(`${context.periodId}|${id}|${nucleus}`), identification: id, cedula: id,
        full_name: clean(source.nombre || base.full_name || id), email: clean(source.correo || base.email).toLowerCase(),
        final_grade: grade, final_status: clean(source.estado) || (grade === null ? 'Pendiente' : grade >= 7 ? 'APROBADO' : 'REPROBADO'),
        modality: clean(source.modalidad || base.modality || 'presencial'), campus: clean(source.sede || base.campus),
      });
      if (clean(source.docente || source.profesor)) group.teachers.add(clean(source.docente || source.profesor));
    });
    const courses = [...groups.values()].map(group => {
      const students = [...group.students.values()];
      const grades = students.map(row => Number(row.final_grade)).filter(Number.isFinite);
      return {
        id: stableId(`${context.periodId}|${group.career}|${group.nucleus}`),
        career_name: group.career, nucleus_number: group.nucleus,
        course_title: `Núcleo ${group.nucleus}`, teacher_name: [...group.teachers].join(' · ') || 'Docente no registrado',
        course_key: `${fold(group.career)}__N${group.nucleus}`, students,
        course_average: grades.length ? grades.reduce((a,b) => a+b, 0) / grades.length : null,
      };
    }).sort((a,b) => a.career_name.localeCompare(b.career_name,'es') || a.nucleus_number-b.nucleus_number);
    return {
      ok: true, courses,
      careers: [...new Set(courses.map(row => row.career_name))],
      excel_import: courses.length ? {
        students: new Set(courses.flatMap(course => course.students.map(student => student.identification))).size,
        careers: new Set(courses.map(course => course.career_name)).size,
        imported_rows: courses.reduce((sum, course) => sum + course.students.length, 0),
        courses: courses.length, duplicate_rows: 0, filename: 'Google Sheets · base principal',
      } : null,
      source: 'GOOGLE_SHEETS', synced_at: context.data.syncedAt,
    };
  }

  function projectRows(context) {
    const official = new Map(context.students.map(row => [row.identification, row]));
    return context.data.work.map(source => {
      const id = digits(source.cedula || source.identificacion);
      if (!id) return null;
      const base = official.get(id) || {};
      const finalGrade = numeric(source.notaFinal ?? source.final_grade);
      return {
        id: stableId(`${context.periodId}|${id}|work`), identification: id, cedula: id,
        full_name: clean(source.nombre || base.full_name || id), career_name: canonicalCareer(source.carrera || base.career_name || 'SIN CARRERA'),
        modality: clean(source.modalidad || base.modality || 'presencial'), title: clean(source.titulo || source.tema),
        tutor: clean(source.tutor), lector: clean(source.lector), tutor_grade: numeric(source.notaTutor), reader_grade: numeric(source.notaLector),
        written_average: numeric(source.promedioEscrito), defense_average: numeric(source.promedioDefensa), final_grade: finalGrade,
        final_status: clean(source.estado) || (finalGrade === null ? 'Pendiente' : finalGrade >= 7 ? 'APROBADO' : 'REPROBADO'),
        act_number: clean(source.numeroActa || source.acta), act_date: clean(source.fechaActa),
        vocal_1: clean(source.tribunal1 || source.vocal1), vocal_2: clean(source.tribunal2 || source.vocal2), vocal_3: clean(source.tribunal3 || source.vocal3),
        detalleTribunalJson: clean(source.detalleTribunalJson), raw: source,
      };
    }).filter(Boolean);
  }

  function projectsPayload(context) {
    const projects = projectRows(context);
    const grades = projects.map(row => Number(row.final_grade)).filter(Number.isFinite);
    return {
      ok: true, projects,
      summary: { total: projects.length, approved: projects.filter(row => row.final_grade !== null && row.final_grade >= 7).length,
        failed: projects.filter(row => row.final_grade !== null && row.final_grade < 7).length,
        average_final: grades.length ? grades.reduce((a,b) => a+b,0)/grades.length : null },
      source: 'GOOGLE_SHEETS', synced_at: context.data.syncedAt,
    };
  }

  function complexiveCareers(context) {
    const official = new Map(context.students.map(row => [row.identification, row]));
    const groups = new Map();
    context.data.complexive.forEach(source => {
      const id = digits(source.cedula || source.identificacion);
      if (!id) return;
      const base = official.get(id) || {};
      const career = canonicalCareer(source.carrera || base.career_name || 'SIN CARRERA');
      const key = fold(career);
      if (!groups.has(key)) groups.set(key, { id: stableId(`${context.report.id}|${career}`), report_id: context.report.id, name: career, students: [] });
      const practical = numeric(source.notaPractico), theory = numeric(source.notaTeorico), supplementary = numeric(source.notaSupletorio);
      const finalGrade = numeric(source.notaFinal) ?? supplementary ?? ([practical,theory].every(Number.isFinite) ? (practical + theory)/2 : null);
      groups.get(key).students.push({
        id: stableId(`${context.periodId}|${id}|complexivo`), identification: id, full_name: clean(source.nombre || base.full_name || id),
        email: clean(base.email), modality: clean(source.modalidad || base.modality || 'presencial'),
        ordinary_theory: theory, ordinary_practical: practical,
        ordinary_final: [practical,theory].every(Number.isFinite) ? (practical + theory)/2 : null,
        supplementary_theory: supplementary, supplementary_practical: null,
        final_grade: finalGrade, final_status: clean(source.estado) || (finalGrade === null ? 'Pendiente' : finalGrade >= 7 ? 'Aprobado' : 'Reprobado'),
      });
    });
    return [...groups.values()].sort((a,b) => a.name.localeCompare(b.name,'es'));
  }

  function pvcSummary(context) {
    const reqIds = new Set(context.data.requirements.map(row => digits(row.cedula)).filter(Boolean));
    const article = projectRows(context).filter(row => fold(row.modality || row.title).includes('ARTICULO'));
    const resultIds = new Set(article.map(row => row.identification));
    const matched = [...resultIds].filter(id => reqIds.has(id)).length;
    const evaluated = article.filter(row => Number.isFinite(Number(row.final_grade))).length;
    const sourcePeriods = [...new Set(article.map(row => {
      try { const detail = row.detalleTribunalJson ? JSON.parse(row.detalleTribunalJson) : {}; return clean(detail.periodoFuente); }
      catch (_) { return ''; }
    }).filter(Boolean))];
    return {
      ok: true,
      summary: { pvc_total: article.length, matched, evaluated, unmatched: resultIds.size - matched,
        formula_warnings: 0, not_evaluated: article.length - evaluated, requirements_total: reqIds.size,
        only_requirements: [...reqIds].filter(id => !resultIds.has(id)).length, source_periods: sourcePeriods },
      source: 'GOOGLE_SHEETS', synced_at: context.data.syncedAt,
    };
  }

  function scheduleKey(periodId) { return `${SCHEDULE_PREFIX}${periodId}`; }
  function readSchedules(periodId) {
    try {
      const value = JSON.parse(localStorage.getItem(scheduleKey(periodId)) || '{}');
      return { complexive: Array.isArray(value.complexive) ? value.complexive : [], thesis: Array.isArray(value.thesis) ? value.thesis : [] };
    } catch (_) { return { complexive: [], thesis: [] }; }
  }
  function writeSchedules(periodId, schedules) { try { localStorage.setItem(scheduleKey(periodId), JSON.stringify(schedules)); } catch (_) {} }

  function readSettings() { try { return JSON.parse(localStorage.getItem(SETTINGS_KEY) || '{}'); } catch (_) { return {}; } }
  function writeSettings(value) { try { localStorage.setItem(SETTINGS_KEY, JSON.stringify(value || {})); } catch (_) {} }

  async function enrichReportPayload(payload, reportId) {
    if (!payload?.report) return payload;
    try {
      const context = await contextForReport(reportId);
      const careers = complexiveCareers(context);
      careerLookup.clear();
      careers.forEach(career => careerLookup.set(Number(career.id), career));
      payload.report = {
        ...payload.report,
        firebase_period_id: context.periodId, periodoId: context.periodId,
        careers, career_count: careers.length, student_count: context.students.length,
        complexive_records: careers.reduce((sum, career) => sum + career.students.length, 0),
        project_summary: {
          ...(payload.report.project_summary || {}), period_project_id: Number(payload.report.id), report_type: payload.report.report_type || 'normal', periodoId: context.periodId,
        },
        data_source: 'GOOGLE_SHEETS',
      };
    } catch (error) {
      payload.report = { ...payload.report, data_source: 'GOOGLE_SHEETS', data_source_error: clean(error?.message) };
    }
    return payload;
  }

  async function parseNucleusText(text) {
    const lines = String(text || '').split(/\r?\n/).map(clean).filter(Boolean);
    const emailRe = /^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$/i;
    const rows = [];
    const emailIndexes = lines.map((line, index) => emailRe.test(line) ? index : -1).filter(index => index >= 0);
    emailIndexes.forEach((emailIndex, position) => {
      const email = lines[emailIndex].toLowerCase();
      let name = '';
      for (let i = emailIndex - 1; i >= 0; i -= 1) {
        const candidate = lines[i];
        if (!candidate || emailRe.test(candidate) || /^[-–—\d.,]+$/.test(candidate)) continue;
        if (/NOMBRE|CORREO|DIRECCI[ÓO]N|TOTAL|COMPONENTE/i.test(candidate)) continue;
        name = candidate; break;
      }
      const end = position + 1 < emailIndexes.length ? emailIndexes[position + 1] : lines.length;
      const nums = lines.slice(emailIndex + 1, end).map(value => numeric(value)).filter(Number.isFinite);
      const grade = nums.length ? nums[nums.length - 1] : null;
      rows.push({ email, name, grade });
    });
    return rows;
  }

  window.fetch = async function sheetsPagesFetch(input, init = {}) {
    const path = pathOf(input);
    const method = methodOf(input, init);

    let match = path.match(/^\/api\/reports\/(\d+)$/);
    if (match && method === 'GET') {
      const response = await previousFetch(input, init);
      if (!response.ok) return response;
      const payload = await response.json().catch(() => ({}));
      return jsonResponse(await enrichReportPayload(payload, Number(match[1])), response.status);
    }

    match = path.match(/^\/api\/reports\/(\d+)\/(roster|students-domain|nuclei|projects|pvc\/summary)$/);
    if (match && method === 'GET') {
      try {
        const context = await contextForReport(Number(match[1]), new URL(typeof input === 'string' ? input : input.url, location.href).searchParams.has('health'));
        const route = match[2];
        if (route === 'roster') return jsonResponse(rosterPayload(context));
        if (route === 'students-domain') return jsonResponse(studentsDomainPayload(context));
        if (route === 'nuclei') return jsonResponse(nucleiPayload(context));
        if (route === 'projects') return jsonResponse(projectsPayload(context));
        if (route === 'pvc/summary') return jsonResponse(pvcSummary(context));
      } catch (error) { return jsonResponse({ ok: false, error: clean(error?.message) }, 500); }
    }

    match = path.match(/^\/api\/reports\/(\d+)\/schedules(?:\/(complexive|thesis))?$/);
    if (match) {
      try {
        const report = reportById(Number(match[1]));
        const periodId = await resolvePeriodId(report || {});
        if (!periodId) throw new Error('No se pudo identificar el período para guardar cronogramas.');
        const schedules = readSchedules(periodId);
        if (method === 'GET') return jsonResponse({ ok: true, schedules, schedule_meta: { source: 'BROWSER_LOCAL', synced_at: new Date().toISOString() } });
        if (method === 'PUT' && match[2]) {
          const body = await bodyOf(input, init);
          schedules[match[2]] = Array.isArray(body.entries) ? body.entries : [];
          writeSchedules(periodId, schedules);
          return jsonResponse({ ok: true, count: schedules[match[2]].length, source: 'BROWSER_LOCAL' });
        }
      } catch (error) { return jsonResponse({ ok: false, error: clean(error?.message) }, 500); }
    }

    match = path.match(/^\/api\/reports\/(\d+)\/generated-pdfs$/);
    if (match && method === 'GET') return jsonResponse({ ok: true, generated_pdfs: [], source: 'BROWSER_LOCAL' });

    if (path === '/api/institutional-settings') {
      if (method === 'GET') return jsonResponse({ ok: true, settings: readSettings() });
      if (method === 'PUT') { const body = await bodyOf(input, init); writeSettings(body); return jsonResponse({ ok: true, settings: body }); }
    }

    match = path.match(/^\/api\/careers\/(\d+)\/(students|summary)$/);
    if (match && method === 'GET') {
      const career = careerLookup.get(Number(match[1]));
      if (!career) return jsonResponse({ ok: true, students: [], summary: { total:0, approved:0, failed:0, supplementary_count:0, average_final:null, approved_pct:0 } });
      const students = career.students || [];
      if (match[2] === 'students') return jsonResponse({ ok: true, students });
      const grades = students.map(row => Number(row.final_grade)).filter(Number.isFinite);
      const approved = students.filter(row => Number(row.final_grade) >= 7).length;
      return jsonResponse({ ok: true, summary: {
        total: students.length, approved, failed: students.filter(row => Number.isFinite(Number(row.final_grade)) && Number(row.final_grade) < 7).length,
        supplementary_count: students.filter(row => Number.isFinite(Number(row.supplementary_theory))).length,
        average_final: grades.length ? grades.reduce((a,b)=>a+b,0)/grades.length : null,
        approved_pct: students.length ? approved * 100 / students.length : 0,
      }});
    }

    match = path.match(/^\/api\/reports\/(\d+)\/nuclei\/import-text-v2$/);
    if (match && method === 'POST') {
      try {
        const context = await contextForReport(Number(match[1]));
        const body = await bodyOf(input, init);
        const parsed = await parseNucleusText(body.text || '');
        if (!parsed.length) throw new Error('No se detectaron estudiantes con correo institucional en el texto.');
        const nucleus = Number(body.nucleus_number || ((String(body.text || '').match(/N[ÚU]CLEO\s*([1-4])/i) || [])[1]) || 0);
        if (![1,2,3,4].includes(nucleus)) throw new Error('No se pudo identificar el Núcleo 1, 2, 3 o 4. Selecciónelo manualmente.');
        const byEmail = new Map(context.students.map(row => [clean(row.email).toLowerCase(), row]).filter(([email]) => email));
        const matched = [], unmatched = [];
        for (const source of parsed) {
          const student = byEmail.get(source.email);
          if (!student || source.grade === null) { unmatched.push(source); continue; }
          matched.push({ source, student });
        }
        const careerCounts = new Map();
        matched.forEach(({ student }) => careerCounts.set(student.career_name, (careerCounts.get(student.career_name) || 0) + 1));
        const career = [...careerCounts.entries()].sort((a,b) => b[1]-a[1])[0]?.[0] || 'SIN CARRERA';
        const campusCounts = new Map();
        matched.forEach(({ student }) => { const campus = clean(student.campus); if (campus) campusCounts.set(campus, (campusCounts.get(campus)||0)+1); });
        const campus = [...campusCounts.entries()].sort((a,b)=>b[1]-a[1])[0]?.[0] || '';
        const jobs = matched.map(({ source, student }) => ({ action: 'guardar_nucleo', data: {
          periodoId: context.periodId, cedula: student.identification, nombre: student.full_name,
          carrera: student.career_name, modalidad: student.modality, sede: student.campus,
          nucleo: nucleus, notaFinal: source.grade, estado: source.grade >= 7 ? 'APROBADO' : 'REPROBADO',
          correo: source.email, curso: `Núcleo ${nucleus}`, updatedAt: new Date().toISOString(),
        }}));
        const saved = await window.InformtitSheets.postMany(jobs, { concurrency: 3 });
        const failures = saved.filter(row => !row.ok);
        if (failures.length) throw new Error(`${failures.length} registros no pudieron guardarse en Google Sheets.`);
        datasetCache.delete(context.periodId);
        const approved = matched.filter(({ source }) => source.grade >= 7).length;
        return jsonResponse({ ok: true, assignment: { nucleus, career, campus, source: 'correo institucional + población de Google Sheets' },
          summary: { detected: parsed.length, matched: matched.length, review: unmatched.length, approved, failed: matched.length-approved },
          unmatched, source: 'GOOGLE_SHEETS' });
      } catch (error) { return jsonResponse({ ok: false, error: clean(error?.message) }, 500); }
    }

    return previousFetch(input, init);
  };

  window.InformtitPagesData = Object.freeze({
    canonicalCareer, inferModality, resolvePeriodId, loadDataset, contextForReport,
    invalidate(periodId = '') { if (periodId) datasetCache.delete(clean(periodId)); else datasetCache.clear(); },
    source: 'GOOGLE_SHEETS',
  });
})();
