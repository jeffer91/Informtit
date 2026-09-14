(() => {
  'use strict';

  if (!/(^|\.)github\.io$/i.test(location.hostname) || !window.InformtitNeon) return;
  const previousFetch = window.fetch.bind(window);
  const clean = value => String(value ?? '').trim();
  const pathOf = input => { try { return new URL(typeof input === 'string' ? input : input?.url, location.href).pathname; } catch (_) { return ''; } };
  const methodOf = (input, init) => String(init?.method || input?.method || 'GET').toUpperCase();
  const jsonResponse = (payload, status = 200) => Promise.resolve(new Response(JSON.stringify(payload), { status, headers:{'Content-Type':'application/json; charset=utf-8'} }));
  async function bodyOf(input, init) {
    if (typeof init?.body === 'string') { try { return JSON.parse(init.body); } catch (_) { return {}; } }
    if (typeof Request !== 'undefined' && input instanceof Request) { try { return await input.clone().json(); } catch (_) {} }
    return {};
  }
  function localReport(id) {
    if (Number(window.state?.activeReport?.id) === Number(id)) return window.state.activeReport;
    try {
      const rows = JSON.parse(localStorage.getItem('informtit.githubPages.reports.v1') || '[]');
      return (Array.isArray(rows) ? rows : []).find(row => Number(row.id) === Number(id) || (row.legacy_report_ids || []).some(value => Number(value) === Number(id))) || null;
    } catch (_) { return null; }
  }
  async function periodIdFor(reportId) {
    const report = localReport(reportId);
    const resolved = await window.InformtitPagesData?.resolvePeriodId?.(report || {});
    return clean(resolved || report?.periodoId || report?.firebase_period_id || report?.period_id);
  }

  window.fetch = async function neonSchedulesFetch(input, init = {}) {
    const path = pathOf(input), method = methodOf(input, init);
    const match = path.match(/^\/api\/reports\/(\d+)\/schedules(?:\/(complexive|thesis))?$/);
    if (!match) return previousFetch(input, init);
    try {
      const periodId = await periodIdFor(Number(match[1]));
      if (!periodId) throw new Error('No se pudo identificar el período académico.');
      if (method === 'GET') {
        const payload = await window.InformtitNeon.schedules(periodId);
        return jsonResponse({ ...payload, schedule_meta:{ source:'NEON', synced_at:new Date().toISOString() } });
      }
      if (method === 'PUT' && match[2]) {
        const body = await bodyOf(input, init);
        const payload = await window.InformtitNeon.saveSchedule(periodId, match[2], Array.isArray(body.entries) ? body.entries : []);
        return jsonResponse(payload);
      }
      return jsonResponse({ok:false,error:'Operación de cronograma no soportada.'},405);
    } catch (error) {
      return jsonResponse({ok:false,error:clean(error?.message || error)},500);
    }
  };

  window.InformtitNeonSchedules = Object.freeze({ version:'1.0.0', source:'NEON' });
})();