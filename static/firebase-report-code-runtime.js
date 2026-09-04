(() => {
  'use strict';

  if (!/(^|\.)github\.io$/i.test(window.location.hostname)) return;

  const REPORTS_KEY = 'informtit.githubPages.reports.v1';
  const previousFetch = window.fetch.bind(window);

  function clean(value) {
    return String(value ?? '').trim();
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

  function parsePeriodId(value) {
    const match = /^(\d{4})-(\d{2})__(\d{4})-(\d{2})$/.exec(clean(value));
    if (!match) return null;
    return { year: Number(match[1]), month: Number(match[2]) };
  }

  function reportYearMonth(payload) {
    const explicit = clean(payload?.code_month);
    if (/^\d{4}-(0[1-9]|1[0-2])$/.test(explicit)) return explicit;

    const parsed = parsePeriodId(payload?.firebase_period_id);
    if (!parsed) return '';
    const index = (parsed.year * 12) + (parsed.month - 1) + 2;
    const year = Math.floor(index / 12);
    const month = (index % 12) + 1;
    return `${year}-${String(month).padStart(2, '0')}`;
  }

  function reportCode(modality, ym) {
    if (!ym) return '';
    const sequence = modality === 'en_linea' ? '02' : '01';
    return `UTET-INF-${sequence}-PRO-95-${ym}`;
  }

  function localToday() {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
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
    try { window.localStorage.setItem(REPORTS_KEY, JSON.stringify(reports)); } catch (_) {}
  }

  function fixCreatedReports(result, payload) {
    const ids = new Set((result?.reports || []).map(item => Number(item?.id)).filter(Number.isFinite));
    if (Number.isFinite(Number(result?.report_id))) ids.add(Number(result.report_id));
    Object.values(result?.report_ids || {}).forEach(value => {
      if (Number.isFinite(Number(value))) ids.add(Number(value));
    });
    if (!ids.size) return;

    const ym = reportYearMonth(payload);
    const presencialCode = reportCode('presencial', ym);
    const onlineCode = reportCode('en_linea', ym);
    const reports = loadReports();
    let changed = false;
    reports.forEach(report => {
      if (!ids.has(Number(report.id))) return;
      const unified = clean(report.modality) === 'unified' || Boolean(report.unified_period);
      const pvc = clean(report.report_type).toLowerCase() === 'pvc';

      if (presencialCode && report.code !== presencialCode) {
        report.code = presencialCode;
        changed = true;
      }
      if (presencialCode && report.code_presencial !== presencialCode) {
        report.code_presencial = presencialCode;
        changed = true;
      }
      const expectedOnline = pvc ? '' : onlineCode;
      if ((unified || !pvc) && report.code_online !== expectedOnline) {
        report.code_online = expectedOnline;
        changed = true;
      }
      if (report.version !== '1.0') {
        report.version = '1.0';
        changed = true;
      }
      const date = clean(payload?.elaboration_date) || localToday();
      if (report.elaboration_date !== date) {
        report.elaboration_date = date;
        changed = true;
      }
      if (clean(payload?.firebase_period_id) && report.firebase_period_id !== clean(payload.firebase_period_id)) {
        report.firebase_period_id = clean(payload.firebase_period_id);
        changed = true;
      }
      if (ym && report.report_code_month !== ym) {
        report.report_code_month = ym;
        changed = true;
      }
    });
    if (changed) saveReports(reports);
  }

  window.fetch = async function modalityCodeFetch(input, init) {
    const path = pathOf(input);
    const method = methodOf(input, init);

    if (path === '/api/reports' && method === 'POST') {
      const payload = await bodyOf(input, init);
      payload.version = '1.0';
      if (!clean(payload.elaboration_date)) payload.elaboration_date = localToday();
      const ym = reportYearMonth(payload);
      if (ym) {
        payload.code_month = ym;
        payload.code_presencial = reportCode('presencial', ym);
        payload.code_online = reportCode('en_linea', ym);
        payload.code = payload.code_presencial;
      }

      const nextInit = { ...(init || {}), body: JSON.stringify(payload) };
      const response = await previousFetch(input, nextInit);
      if (!response.ok) return response;

      let result = null;
      try { result = await response.clone().json(); } catch (_) {}
      if (result) fixCreatedReports(result, payload);
      return response;
    }

    return previousFetch(input, init);
  };
})();