(() => {
  'use strict';

  if (!/(^|\.)github\.io$/i.test(window.location.hostname)) return;
  if (!window.InformtitSheets) return;

  const REPORTS_KEY = 'informtit.githubPages.reports.v1';
  const previousFetch = window.fetch.bind(window);
  const clean = value => String(value ?? '').replace(/\u00a0/g, ' ').trim().replace(/\s+/g, ' ');

  function pathOf(input) {
    try { return new URL(typeof input === 'string' ? input : input?.url, window.location.href).pathname; }
    catch (_) { return ''; }
  }

  function methodOf(input, init) { return String(init?.method || input?.method || 'GET').toUpperCase(); }

  async function bodyOf(input, init) {
    if (typeof init?.body === 'string') {
      try { return JSON.parse(init.body); } catch (_) { return {}; }
    }
    if (typeof Request !== 'undefined' && input instanceof Request) {
      try { return await input.clone().json(); } catch (_) {}
    }
    return {};
  }

  function parseConfig(value) {
    if (!value) return null;
    if (typeof value === 'object') return value;
    try { return JSON.parse(String(value)); } catch (_) { return null; }
  }

  function withConfig(report = {}) {
    const config = parseConfig(report.document_config || report.documentConfig || report.document_config_json);
    return config ? { ...report, document_config: config, document_config_json: JSON.stringify(config) } : report;
  }

  function readReports() {
    try {
      const rows = JSON.parse(localStorage.getItem(REPORTS_KEY) || '[]');
      return Array.isArray(rows) ? rows : [];
    } catch (_) { return []; }
  }

  function writeReports(rows) {
    try { localStorage.setItem(REPORTS_KEY, JSON.stringify(Array.isArray(rows) ? rows : [])); } catch (_) {}
  }

  function upsertLocal(report) {
    if (!report?.id) return;
    const rows = readReports();
    const index = rows.findIndex(row => Number(row.id) === Number(report.id)
      || (row.legacy_report_ids || []).some(id => Number(id) === Number(report.id)));
    if (index >= 0) rows[index] = { ...rows[index], ...report };
    else rows.push(report);
    writeReports(rows);
  }

  function periodId(report) {
    return clean(report?.periodoId || report?.firebase_period_id || report?.period_id || report?.periodId);
  }

  function reportType(report) {
    return clean(report?.report_type || report?.tipo).toLowerCase() === 'pvc' ? 'pvc' : 'normal';
  }

  function sharedPayload(report, config) {
    return {
      reportId: Number(report.id || report.reportId || 0) || undefined,
      id: Number(report.id || report.reportId || 0) || undefined,
      periodoId: periodId(report),
      report_type: reportType(report),
      tipo: reportType(report),
      name: clean(report.name || report.nombre),
      nombre: clean(report.name || report.nombre),
      period: clean(report.period || report.periodo),
      periodo: clean(report.period || report.periodo),
      code: clean(report.code || report.code_presencial),
      code_presencial: clean(report.code_presencial || report.code),
      code_online: clean(report.code_online),
      version: clean(report.version) || '1.0',
      elaboration_date: clean(report.elaboration_date),
      prepared_by: clean(report.prepared_by),
      prepared_role: clean(report.prepared_role),
      reviewed_by: clean(report.reviewed_by),
      reviewed_role: clean(report.reviewed_role),
      approved_by: clean(report.approved_by),
      approved_role: clean(report.approved_role),
      status: clean(report.status) || 'borrador',
      document_config: JSON.stringify(config || {}),
      document_config_json: JSON.stringify(config || {}),
      updatedAt: new Date().toISOString(),
    };
  }

  async function jsonPayload(response) {
    try { return await response.clone().json(); } catch (_) { return {}; }
  }

  window.fetch = async function pagesDocumentStateFetch(input, init = {}) {
    const path = pathOf(input);
    const method = methodOf(input, init);

    if (path === '/api/reports' && method === 'GET') {
      const response = await previousFetch(input, init);
      const payload = await jsonPayload(response);
      if (!response.ok || payload?.ok === false || !Array.isArray(payload.reports)) return response;
      const reports = payload.reports.map(withConfig);
      writeReports(reports);
      return new Response(JSON.stringify({ ...payload, reports }), { status: response.status, headers: { 'Content-Type': 'application/json; charset=utf-8' } });
    }

    const match = path.match(/^\/api\/reports\/(\d+)$/);
    if (match && method === 'GET') {
      const response = await previousFetch(input, init);
      const payload = await jsonPayload(response);
      if (!response.ok || payload?.ok === false || !payload.report) return response;
      const report = withConfig(payload.report);
      upsertLocal(report);
      return new Response(JSON.stringify({ ...payload, report }), { status: response.status, headers: { 'Content-Type': 'application/json; charset=utf-8' } });
    }

    if (match && method === 'PUT') {
      const request = await bodyOf(input, init);
      const response = await previousFetch(input, init);
      const payload = await jsonPayload(response);
      if (!response.ok || payload?.ok === false || !payload.report || !request.document_config) return response;
      const config = parseConfig(request.document_config) || parseConfig(request.document_config_json) || {};
      const report = withConfig({ ...payload.report, document_config: config });
      upsertLocal(report);
      let shared = true;
      let warning = '';
      try {
        await window.InformtitSheets.guardarInforme(sharedPayload(report, config));
      } catch (error) {
        shared = false;
        warning = clean(error?.message || error);
      }
      return new Response(JSON.stringify({ ...payload, report, document_config_shared: shared, sharing_warning: warning }), {
        status: response.status,
        headers: { 'Content-Type': 'application/json; charset=utf-8' },
      });
    }

    return previousFetch(input, init);
  };

  window.InformtitDocumentState = Object.freeze({ parseConfig, withConfig, version: '1.0.0' });
})();