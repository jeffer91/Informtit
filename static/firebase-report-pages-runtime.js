(() => {
  'use strict';

  if (!/(^|\.)github\.io$/i.test(window.location.hostname)) return;

  const REPORTS_KEY = 'informtit.githubPages.reports.v1';
  const COUNTER_KEY = 'informtit.githubPages.reportCounter.v1';
  const nativeFetch = window.fetch.bind(window);

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

  function rawReports() {
    try {
      const parsed = JSON.parse(window.localStorage.getItem(REPORTS_KEY) || '[]');
      return Array.isArray(parsed) ? parsed : [];
    } catch (_) {
      return [];
    }
  }

  function saveReports(reports) {
    window.localStorage.setItem(REPORTS_KEY, JSON.stringify(reports));
  }

  function nextId() {
    let current = 0;
    try { current = Number(window.localStorage.getItem(COUNTER_KEY) || 0); } catch (_) {}
    const base = Math.max(current + 1, Date.now());
    try { window.localStorage.setItem(COUNTER_KEY, String(base)); } catch (_) {}
    return base;
  }

  function reportType(report) {
    return clean(report?.report_type).toLowerCase() === 'pvc' ? 'pvc' : 'normal';
  }

  function periodKey(report) {
    return clean(report?.firebase_period_id) || fold(report?.period);
  }

  function studentIdentity(student = {}) {
    return clean(student.identification || student.cedula || student.email || student.full_name || student.name).toLowerCase();
  }

  function mergeCareers(reports, canonicalId) {
    const byName = new Map();
    reports.forEach(source => {
      const sourceModality = clean(source.modality) || 'presencial';
      (Array.isArray(source.careers) ? source.careers : []).forEach(career => {
        const key = fold(career.name || career.career_name || `Carrera ${career.id || ''}`);
        let target = byName.get(key);
        if (!target) {
          target = {
            ...career,
            id: Number(career.id || nextId()),
            report_id: canonicalId,
            students: [],
            analyses: { ...(career.analyses || {}) },
            source_modalities: [],
          };
          byName.set(key, target);
        }
        if (!target.source_modalities.includes(sourceModality)) target.source_modalities.push(sourceModality);
        const students = Array.isArray(career.students) ? career.students : [];
        const existing = new Map(target.students.map(item => [studentIdentity(item), item]));
        students.forEach(student => {
          const identity = studentIdentity(student) || `row:${target.students.length}`;
          const previous = existing.get(identity);
          const enriched = {
            ...student,
            modality: clean(student.modality) || sourceModality,
          };
          if (previous) Object.assign(previous, enriched);
          else {
            target.students.push(enriched);
            existing.set(identity, enriched);
          }
        });
      });
    });
    return [...byName.values()];
  }

  function mergeDistinct(reports, field) {
    const seen = new Set();
    const result = [];
    reports.forEach(report => {
      (Array.isArray(report[field]) ? report[field] : []).forEach(item => {
        const key = clean(item?.id || item?.section_key || item?.filename || JSON.stringify(item));
        if (seen.has(key)) return;
        seen.add(key);
        result.push(item);
      });
    });
    return result;
  }

  function normalizeReport(report) {
    const careers = Array.isArray(report.careers) ? report.careers : [];
    const images = Array.isArray(report.images) ? report.images : [];
    const sections = Array.isArray(report.sections) ? report.sections : [];
    const studentCount = careers.reduce((sum, career) => (
      sum + (Array.isArray(career.students) ? career.students.length : 0)
    ), 0);
    return {
      ...report,
      careers,
      images,
      sections,
      career_count: Number(report.career_count ?? careers.length ?? 0),
      student_count: Number(report.student_count ?? studentCount ?? 0),
    };
  }

  function mergeNormalGroup(group) {
    const ordered = [...group].sort((a, b) => Number(a.id || 0) - Number(b.id || 0));
    const presencial = ordered.find(item => clean(item.modality) === 'presencial');
    const online = ordered.find(item => clean(item.modality) === 'en_linea');
    const base = presencial || ordered[0] || {};
    const id = Number(base.id || nextId());
    const careers = mergeCareers(ordered, id);
    const studentCount = careers.reduce((sum, career) => sum + (career.students?.length || 0), 0);
    const legacyIds = [...new Set(ordered.flatMap(item => [Number(item.id || 0), ...(item.legacy_report_ids || []).map(Number)]).filter(Boolean))];
    const codePresencial = clean(presencial?.code_presencial || presencial?.code || base.code_presencial || base.code);
    const codeOnline = clean(online?.code_online || online?.code || base.code_online);
    const updatedAt = ordered.map(item => clean(item.updated_at)).sort().pop() || new Date().toISOString();
    const createdAt = ordered.map(item => clean(item.created_at)).filter(Boolean).sort()[0] || new Date().toISOString();

    return normalizeReport({
      ...base,
      id,
      modality: 'unified',
      unified_period: true,
      report_type: 'normal',
      firebase_period_id: clean(base.firebase_period_id || ordered.find(item => item.firebase_period_id)?.firebase_period_id),
      code: codePresencial,
      code_presencial: codePresencial,
      code_online: codeOnline,
      careers,
      images: mergeDistinct(ordered, 'images'),
      sections: mergeDistinct(ordered, 'sections'),
      career_count: careers.length,
      student_count: Math.max(
        studentCount,
        ordered.reduce((sum, item) => sum + Number(item.student_count || 0), 0),
      ),
      legacy_report_ids: legacyIds,
      storage_mode: 'github_pages_period_unified',
      created_at: createdAt,
      updated_at: updatedAt,
    });
  }

  function migrateReports(reports) {
    const normalGroups = new Map();
    const pvc = [];
    reports.forEach(raw => {
      const report = normalizeReport(raw);
      if (reportType(report) === 'pvc') {
        pvc.push({ ...report, unified_period: false });
        return;
      }
      const key = periodKey(report) || `legacy:${report.id}`;
      if (!normalGroups.has(key)) normalGroups.set(key, []);
      normalGroups.get(key).push(report);
    });
    return [
      ...[...normalGroups.values()].map(mergeNormalGroup),
      ...pvc,
    ].sort((a, b) => clean(b.updated_at).localeCompare(clean(a.updated_at)));
  }

  function loadReports() {
    const before = rawReports();
    const migrated = migrateReports(before);
    const beforeText = JSON.stringify(before);
    const afterText = JSON.stringify(migrated);
    if (beforeText !== afterText) saveReports(migrated);
    return migrated;
  }

  function publicReport(report) {
    const normalized = normalizeReport(report);
    return {
      ...normalized,
      career_count: normalized.career_count,
      student_count: normalized.student_count,
    };
  }

  function reportTemplate(payload, reportTypeValue) {
    const timestamp = new Date().toISOString();
    const id = nextId();
    const pvc = reportTypeValue === 'pvc';
    const period = clean(payload.period);
    return normalizeReport({
      id,
      name: clean(payload.name) || (pvc ? 'Informe PVC' : 'Informe Final del Proceso de Titulación'),
      period,
      modality: pvc ? 'presencial' : 'unified',
      unified_period: !pvc,
      report_type: reportTypeValue,
      firebase_period_id: clean(payload.firebase_period_id),
      code: clean(payload.code_presencial || payload.code),
      code_presencial: clean(payload.code_presencial || payload.code),
      code_online: pvc ? '' : clean(payload.code_online),
      version: clean(payload.version) || '1.0',
      elaboration_date: clean(payload.elaboration_date),
      prepared_by: clean(payload.prepared_by),
      prepared_role: clean(payload.prepared_role),
      reviewed_by: clean(payload.reviewed_by),
      reviewed_role: clean(payload.reviewed_role),
      approved_by: clean(payload.approved_by),
      approved_role: clean(payload.approved_role),
      status: 'borrador',
      created_at: timestamp,
      updated_at: timestamp,
      careers: [],
      images: [],
      sections: [],
      career_count: 0,
      student_count: 0,
      legacy_report_ids: [id],
      storage_mode: pvc ? 'github_pages_local' : 'github_pages_period_unified',
    });
  }

  function findReport(reports, id) {
    return reports.find(item => Number(item.id) === Number(id)
      || (item.legacy_report_ids || []).some(value => Number(value) === Number(id)));
  }

  function reportIndex(reports, id) {
    return reports.findIndex(item => Number(item.id) === Number(id)
      || (item.legacy_report_ids || []).some(value => Number(value) === Number(id)));
  }

  function findCareer(reports, careerId) {
    for (const report of reports) {
      const index = (report.careers || []).findIndex(item => Number(item.id) === Number(careerId));
      if (index >= 0) return { report, index, career: report.careers[index] };
    }
    return null;
  }

  function emptySummary() {
    return {
      total: 0,
      approved: 0,
      failed: 0,
      supplementary_count: 0,
      approved_pct: 0,
      average_final: 0,
    };
  }

  window.fetch = async function githubPagesReportFetch(input, init) {
    const path = apiPath(input);
    const method = methodOf(input, init);

    if (path === '/api/reports' && method === 'GET') {
      const reports = loadReports().map(publicReport);
      return jsonResponse({ ok: true, reports, storage: 'GitHub Pages + Firebase UTET · período unificado' });
    }

    if (path === '/api/reports' && method === 'POST') {
      const payload = await requestBody(input, init);
      const reportTypeValue = clean(payload.report_type).toLowerCase() === 'pvc' ? 'pvc' : 'normal';
      const reports = loadReports();
      const probe = { firebase_period_id: payload.firebase_period_id, period: payload.period };
      const duplicate = reportTypeValue === 'normal'
        ? reports.find(item => reportType(item) === 'normal' && periodKey(item) === periodKey(probe))
        : null;
      if (duplicate) {
        return jsonResponse({
          ok: false,
          error: 'Ya existe un informe global para este período académico. Abra el informe existente.',
          report_id: duplicate.id,
        }, 409);
      }

      const created = reportTemplate(payload, reportTypeValue);
      reports.push(created);
      saveReports(reports);
      return jsonResponse({
        ok: true,
        report_type: reportTypeValue,
        report_id: created.id,
        report_ids: reportTypeValue === 'normal' ? { unified: created.id } : { pvc: created.id },
        reports: [publicReport(created)],
        storage: created.storage_mode,
      }, 201);
    }

    let match = path.match(/^\/api\/reports\/(\d+)$/);
    if (match) {
      const id = Number(match[1]);
      const reports = loadReports();
      const index = reportIndex(reports, id);
      if (index < 0) return jsonResponse({ ok: false, error: 'Informe no encontrado.' }, 404);

      if (method === 'GET') {
        return jsonResponse({ ok: true, report: publicReport(reports[index]) });
      }
      if (method === 'PUT') {
        const payload = await requestBody(input, init);
        reports[index] = normalizeReport({
          ...reports[index],
          ...payload,
          id: reports[index].id,
          modality: reports[index].unified_period ? 'unified' : reports[index].modality,
          updated_at: new Date().toISOString(),
        });
        saveReports(reports);
        return jsonResponse({ ok: true, report: publicReport(reports[index]) });
      }
      if (method === 'DELETE') {
        const deleted = reports.splice(index, 1)[0];
        saveReports(reports);
        return jsonResponse({ ok: true, deleted_id: deleted.id });
      }
    }

    match = path.match(/^\/api\/reports\/(\d+)\/careers$/);
    if (match && method === 'POST') {
      const reportId = Number(match[1]);
      const payload = await requestBody(input, init);
      const reports = loadReports();
      const report = findReport(reports, reportId);
      if (!report) return jsonResponse({ ok: false, error: 'Informe no encontrado.' }, 404);
      report.careers = Array.isArray(report.careers) ? report.careers : [];
      const career = {
        id: nextId(),
        report_id: report.id,
        name: clean(payload.name) || 'Carrera',
        students: [],
        analyses: {},
      };
      report.careers.push(career);
      report.career_count = report.careers.length;
      report.updated_at = new Date().toISOString();
      saveReports(reports);
      return jsonResponse({ ok: true, career }, 201);
    }

    match = path.match(/^\/api\/careers\/(\d+)$/);
    if (match && method === 'DELETE') {
      const careerId = Number(match[1]);
      const reports = loadReports();
      const found = findCareer(reports, careerId);
      if (!found) return jsonResponse({ ok: false, error: 'Carrera no encontrada.' }, 404);
      found.report.careers.splice(found.index, 1);
      found.report.career_count = found.report.careers.length;
      found.report.updated_at = new Date().toISOString();
      saveReports(reports);
      return jsonResponse({ ok: true, deleted_id: careerId });
    }

    match = path.match(/^\/api\/careers\/(\d+)\/students$/);
    if (match && method === 'GET') {
      const reports = loadReports();
      const found = findCareer(reports, Number(match[1]));
      if (!found) return jsonResponse({ ok: false, error: 'Carrera no encontrada.' }, 404);
      return jsonResponse({ ok: true, students: Array.isArray(found.career.students) ? found.career.students : [] });
    }

    match = path.match(/^\/api\/careers\/(\d+)\/summary$/);
    if (match && method === 'GET') {
      const reports = loadReports();
      const found = findCareer(reports, Number(match[1]));
      if (!found) return jsonResponse({ ok: false, error: 'Carrera no encontrada.' }, 404);
      const students = Array.isArray(found.career.students) ? found.career.students : [];
      if (!students.length) return jsonResponse({ ok: true, summary: emptySummary() });
      const approved = students.filter(item => clean(item.final_status).toLowerCase() === 'aprobado').length;
      const failed = students.length - approved;
      const finals = students.map(item => Number(item.final_grade)).filter(Number.isFinite);
      const average = finals.length ? finals.reduce((a, b) => a + b, 0) / finals.length : 0;
      return jsonResponse({
        ok: true,
        summary: {
          total: students.length,
          approved,
          failed,
          supplementary_count: students.filter(item => Number(item.supplementary_theory) || Number(item.supplementary_practical)).length,
          approved_pct: students.length ? (approved * 100) / students.length : 0,
          average_final: average,
        },
      });
    }

    return nativeFetch(input, init);
  };

  window.informtitGithubPagesReports = Object.freeze({
    load: () => loadReports().map(publicReport),
    clear: () => {
      window.localStorage.removeItem(REPORTS_KEY);
      window.localStorage.removeItem(COUNTER_KEY);
    },
  });
})();