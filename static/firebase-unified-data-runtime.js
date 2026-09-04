(() => {
  'use strict';

  if (!/(^|\.)github\.io$/i.test(window.location.hostname)) return;

  const REPORTS_KEY = 'informtit.githubPages.reports.v1';
  const previousFetch = window.fetch.bind(window);
  let legacyLock = Promise.resolve();

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

  function jsonResponse(payload, status = 200) {
    return Promise.resolve(new Response(JSON.stringify(payload), {
      status,
      headers: { 'Content-Type': 'application/json; charset=utf-8' },
    }));
  }

  function loadReports() {
    try {
      const reports = JSON.parse(window.localStorage.getItem(REPORTS_KEY) || '[]');
      return Array.isArray(reports) ? reports : [];
    } catch (_) {
      return [];
    }
  }

  function findReport(reportId) {
    return loadReports().find(report => Number(report.id) === Number(reportId)
      || (report.legacy_report_ids || []).some(id => Number(id) === Number(reportId))) || null;
  }

  function isUnified(report) {
    return Boolean(report)
      && clean(report.report_type).toLowerCase() !== 'pvc'
      && (clean(report.modality) === 'unified' || Boolean(report.unified_period));
  }

  async function responseJson(response) {
    let data = {};
    try { data = await response.json(); } catch (_) {}
    if (!response.ok || data?.ok === false) {
      throw new Error(data?.error || `Error ${response.status}`);
    }
    return data;
  }

  function runLocked(task) {
    const run = legacyLock.then(task, task);
    legacyLock = run.catch(() => null);
    return run;
  }

  async function fetchAs(reportId, modality, input, init) {
    return runLocked(async () => {
      const raw = window.localStorage.getItem(REPORTS_KEY) || '[]';
      let reports;
      try { reports = JSON.parse(raw); } catch (_) { reports = []; }
      const index = reports.findIndex(report => Number(report.id) === Number(reportId)
        || (report.legacy_report_ids || []).some(id => Number(id) === Number(reportId)));
      if (index < 0) throw new Error('Informe global no encontrado.');
      const canonicalId = Number(reports[index].id);
      reports[index] = { ...reports[index], modality };
      window.localStorage.setItem(REPORTS_KEY, JSON.stringify(reports));
      try {
        const rawUrl = typeof input === 'string' ? input : input?.url;
        const url = new URL(rawUrl, window.location.href);
        url.pathname = url.pathname.replace(/\/api\/reports\/\d+/, `/api/reports/${canonicalId}`);
        const nextInput = typeof input === 'string' ? `${url.pathname}${url.search}` : new Request(url.toString(), input);
        return await responseJson(await previousFetch(nextInput, init));
      } finally {
        window.localStorage.setItem(REPORTS_KEY, raw);
      }
    });
  }

  function uniqueStudents(rows) {
    const seen = new Map();
    rows.forEach(row => {
      const key = clean(row.identification || row.cedula || row.email || fold(row.full_name));
      if (!key) return;
      if (!seen.has(key)) seen.set(key, row);
      else Object.assign(seen.get(key), row);
    });
    return [...seen.values()];
  }

  function counter(rows, key) {
    const values = new Map();
    rows.forEach(row => {
      const name = clean(row[key]) || `Sin ${key === 'campus' ? 'sede' : key === 'schedule' ? 'jornada' : 'carrera'}`;
      values.set(name, (values.get(name) || 0) + 1);
    });
    return [...values.entries()]
      .sort((a, b) => a[0].localeCompare(b[0], 'es'))
      .map(([name, students]) => ({ name, students }));
  }

  function combineRequirements(a = [], b = []) {
    const result = new Map();
    [...a, ...b].forEach(item => {
      const key = clean(item.key || item.label);
      if (!result.has(key)) {
        result.set(key, { ...item, complies: 0, does_not_comply: 0, blank: 0, total: 0 });
      }
      const target = result.get(key);
      target.complies += Number(item.complies || 0);
      target.does_not_comply += Number(item.does_not_comply || 0);
      target.blank += Number(item.blank || 0);
      target.total += Number(item.total || 0);
    });
    return [...result.values()];
  }

  function combineRoster(report, presencial, online) {
    const students = uniqueStudents([
      ...(presencial.students || []).map(item => ({ ...item, modality: clean(item.modality) || 'presencial' })),
      ...(online.students || []).map(item => ({ ...item, modality: clean(item.modality) || 'en_linea' })),
    ]);
    const complete = students.filter(item => item.requirements_complete).length;
    return {
      ok: true,
      report: {
        id: report.id,
        name: report.name,
        period: report.period,
        modality: 'unified',
      },
      summary: {
        students: students.length,
        careers: new Set(students.map(item => clean(item.career_name)).filter(Boolean)).size,
        requirements_complete: complete,
        requirements_pending: students.length - complete,
        titulation_marked: students.filter(item => item.titulation_marked).length,
        complexive_project_approved: students.filter(item => item.complexive_project_approved).length,
        titles_uploaded: students.filter(item => item.titles_uploaded).length,
        notes_loaded: students.filter(item => item.notes_loaded).length,
        notes_pending: students.filter(item => !item.notes_loaded).length,
        is_imported: students.length > 0,
        presencial: students.filter(item => item.modality === 'presencial').length,
        online: students.filter(item => item.modality === 'en_linea').length,
      },
      careers: counter(students, 'career_name'),
      campuses: counter(students, 'campus'),
      schedules: counter(students, 'schedule'),
      requirements: combineRequirements(presencial.requirements, online.requirements),
      students,
      source: 'Firebase UTET · período global',
      cache_mode: `${clean(presencial.cache_mode)}+${clean(online.cache_mode)}`.replace(/^\+|\+$/g, ''),
      synced_at: presencial.synced_at || online.synced_at || '',
    };
  }

  function combineStudentDomain(presencial, online) {
    const students = uniqueStudents([
      ...(presencial.students || []).map(item => ({ ...item, modality: clean(item.modality) || 'presencial' })),
      ...(online.students || []).map(item => ({ ...item, modality: clean(item.modality) || 'en_linea' })),
    ]);
    return {
      ok: true,
      students,
      summary: {
        students: students.length,
        presencial: students.filter(item => item.modality === 'presencial').length,
        online: students.filter(item => item.modality === 'en_linea').length,
        complexive: students.filter(item => item.route === 'COMPLEXIVO').length,
        thesis: students.filter(item => item.route === 'TRABAJO_TITULACION').length,
        article: students.filter(item => item.route === 'ARTICULO').length,
        graduated: students.filter(item => Number(item.official_graduated) === 1).length,
        retired: students.filter(item => item.process_status === 'RETIRADO').length,
        review: students.filter(item => item.reconciliation_status !== 'OK').length,
      },
      open_links: [...(presencial.open_links || []), ...(online.open_links || [])],
      source: 'Firebase UTET · período global',
      cache_mode: `${clean(presencial.cache_mode)}+${clean(online.cache_mode)}`.replace(/^\+|\+$/g, ''),
      synced_at: presencial.synced_at || online.synced_at || '',
    };
  }

  function masterIdentity(students) {
    const byIdentification = new Map();
    const byEmail = new Map();
    const byName = new Map();
    students.forEach(student => {
      const modality = clean(student.modality);
      const identification = clean(student.identification || student.cedula);
      const email = clean(student.email || student.personal_email).toLowerCase();
      const name = fold(student.full_name);
      if (identification) byIdentification.set(identification, modality);
      if (email) byEmail.set(email, modality);
      if (name) {
        const current = byName.get(name);
        if (!current) byName.set(name, modality);
        else if (current !== modality) byName.set(name, 'ambiguous');
      }
    });
    return { byIdentification, byEmail, byName };
  }

  function modalityForStudent(student, master, fallback) {
    const identification = clean(student.identification || student.cedula);
    const email = clean(student.email).toLowerCase();
    const name = fold(student.full_name);
    if (identification && master.byIdentification.has(identification)) return master.byIdentification.get(identification);
    if (email && master.byEmail.has(email)) return master.byEmail.get(email);
    const byName = name ? master.byName.get(name) : '';
    if (byName && byName !== 'ambiguous') return byName;
    return fallback;
  }

  function combineNuclei(presencial, online, masterStudents) {
    const master = masterIdentity(masterStudents);
    const courseMap = new Map();
    const ingest = (payload, fallback) => {
      (payload.courses || []).forEach(course => {
        const key = clean(course.course_key) || fold(`${course.career_name}|${course.nucleus_number}|${course.course_title}|${course.teacher_name}`);
        if (!courseMap.has(key)) {
          courseMap.set(key, { ...course, students: [], modality_counts: { presencial: 0, en_linea: 0 } });
        }
        const target = courseMap.get(key);
        const studentMap = new Map(target.students.map(item => [clean(item.id || item.email || fold(item.full_name)), item]));
        (course.students || []).forEach(student => {
          const modality = modalityForStudent(student, master, fallback);
          const enriched = { ...student, modality };
          const studentKey = clean(student.id || student.email || fold(student.full_name));
          if (!studentKey) return;
          if (!studentMap.has(studentKey)) {
            target.students.push(enriched);
            studentMap.set(studentKey, enriched);
          } else {
            Object.assign(studentMap.get(studentKey), enriched);
          }
        });
      });
    };
    ingest(presencial, 'presencial');
    ingest(online, 'en_linea');

    const courses = [...courseMap.values()].map(course => {
      const counts = {
        presencial: course.students.filter(item => item.modality === 'presencial').length,
        en_linea: course.students.filter(item => item.modality === 'en_linea').length,
      };
      const modality = counts.presencial && counts.en_linea
        ? 'mixto'
        : (counts.en_linea ? 'en_linea' : 'presencial');
      return { ...course, modality, modality_counts: counts };
    });
    const students = new Set();
    courses.forEach(course => course.students.forEach(student => students.add(clean(student.id || student.email || fold(student.full_name)))));
    return {
      ok: true,
      courses,
      excel_import: courses.length ? {
        students: students.size,
        careers: new Set(courses.map(course => clean(course.career_name))).size,
        imported_rows: courses.reduce((sum, course) => sum + course.students.length, 0),
        courses: courses.length,
        duplicate_rows: 0,
        filename: 'Firebase UTET · carga global',
      } : null,
      source: 'Firebase UTET · período global',
      cache_mode: `${clean(presencial.cache_mode)}+${clean(online.cache_mode)}`.replace(/^\+|\+$/g, ''),
    };
  }

  window.fetch = async function firebaseUnifiedDataFetch(input, init) {
    const path = pathOf(input);
    const method = methodOf(input, init);
    if (method !== 'GET') return previousFetch(input, init);

    let match = path.match(/^\/api\/reports\/(\d+)\/roster$/);
    if (match) {
      const report = findReport(Number(match[1]));
      if (!isUnified(report)) return previousFetch(input, init);
      try {
        const presencial = await fetchAs(report.id, 'presencial', input, init);
        const online = await fetchAs(report.id, 'en_linea', input, init);
        return jsonResponse(combineRoster(report, presencial, online));
      } catch (error) {
        return jsonResponse({ ok: false, error: clean(error?.message) || 'No se pudo cargar la población global.' }, 503);
      }
    }

    match = path.match(/^\/api\/reports\/(\d+)\/students-domain$/);
    if (match) {
      const report = findReport(Number(match[1]));
      if (!isUnified(report)) return previousFetch(input, init);
      try {
        const presencial = await fetchAs(report.id, 'presencial', input, init);
        const online = await fetchAs(report.id, 'en_linea', input, init);
        return jsonResponse(combineStudentDomain(presencial, online));
      } catch (error) {
        return jsonResponse({ ok: false, error: clean(error?.message) || 'No se pudo cargar Estudiantes globalmente.' }, 503);
      }
    }

    match = path.match(/^\/api\/reports\/(\d+)\/nuclei$/);
    if (match) {
      const report = findReport(Number(match[1]));
      if (!isUnified(report)) return previousFetch(input, init);
      try {
        const [pNuclei, oNuclei, pStudents, oStudents] = [
          await fetchAs(report.id, 'presencial', input, init),
          await fetchAs(report.id, 'en_linea', input, init),
          await fetchAs(report.id, 'presencial', `/api/reports/${report.id}/students-domain`, {}),
          await fetchAs(report.id, 'en_linea', `/api/reports/${report.id}/students-domain`, {}),
        ];
        const masterStudents = uniqueStudents([
          ...(pStudents.students || []).map(item => ({ ...item, modality: 'presencial' })),
          ...(oStudents.students || []).map(item => ({ ...item, modality: 'en_linea' })),
        ]);
        return jsonResponse(combineNuclei(pNuclei, oNuclei, masterStudents));
      } catch (error) {
        return jsonResponse({ ok: false, error: clean(error?.message) || 'No se pudieron cargar los Núcleos globalmente.' }, 503);
      }
    }

    return previousFetch(input, init);
  };

  window.informtitUnifiedPeriodData = Object.freeze({
    isUnifiedReport: report => isUnified(report),
  });
})();