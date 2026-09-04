(() => {
  'use strict';

  if (!/(^|\.)github\.io$/i.test(window.location.hostname)) return;

  const REPORTS_KEY = 'informtit.githubPages.reports.v1';
  const COUNTER_KEY = 'informtit.githubPages.reportCounter.v1';
  const nativeFetch = window.fetch.bind(window);

  function clean(value) {
    return String(value ?? '').trim();
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

  function loadReports() {
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

  function normalizeReport(report) {
    const careers = Array.isArray(report.careers) ? report.careers : [];
    const images = Array.isArray(report.images) ? report.images : [];
    const sections = Array.isArray(report.sections) ? report.sections : [];
    return {
      ...report,
      careers,
      images,
      sections,
      career_count: Number(report.career_count ?? careers.length ?? 0),
      student_count: Number(report.student_count ?? careers.reduce((sum, career) => (
        sum + (Array.isArray(career.students) ? career.students.length : 0)
      ), 0)),
    };
  }

  function publicReport(report) {
    const normalized = normalizeReport(report);
    return {
      ...normalized,
      career_count: normalized.career_count,
      student_count: normalized.student_count,
    };
  }

  function reportTemplate(payload, modality, reportType) {
    const timestamp = new Date().toISOString();
    const id = nextId();
    const pvc = reportType === 'pvc';
    const period = clean(payload.period);
    return {
      id,
      name: clean(payload.name) || (pvc ? 'Informe PVC' : 'Informe Final del Proceso de Titulación'),
      period,
      modality: pvc ? 'presencial' : modality,
      report_type: reportType,
      code: clean(payload.code),
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
      storage_mode: 'github_pages_local',
    };
  }

  function findReport(reports, id) {
    return reports.find(item => Number(item.id) === Number(id));
  }

  function reportIndex(reports, id) {
    return reports.findIndex(item => Number(item.id) === Number(id));
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
      const reports = loadReports()
        .map(publicReport)
        .sort((a, b) => clean(b.updated_at).localeCompare(clean(a.updated_at)));
      return jsonResponse({ ok: true, reports, storage: 'GitHub Pages local + Firebase UTET' });
    }

    if (path === '/api/reports' && method === 'POST') {
      const payload = await requestBody(input, init);
      const reportType = clean(payload.report_type).toLowerCase() === 'pvc' ? 'pvc' : 'normal';
      const reports = loadReports();
      const created = reportType === 'pvc'
        ? [reportTemplate(payload, 'presencial', 'pvc')]
        : [
            reportTemplate(payload, 'presencial', 'normal'),
            reportTemplate(payload, 'en_linea', 'normal'),
          ];
      reports.push(...created);
      saveReports(reports);
      return jsonResponse({
        ok: true,
        report_type: reportType,
        report_id: created[0].id,
        report_ids: Object.fromEntries(created.map(item => [item.modality, item.id])),
        reports: created.map(publicReport),
        storage: 'github_pages_local',
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
        report_id: reportId,
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
