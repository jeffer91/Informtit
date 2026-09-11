(() => {
  'use strict';

  if (!/(^|\.)github\.io$/i.test(window.location.hostname)) return;
  if (!window.InformtitSheets) return;

  const REPORTS_KEY = 'informtit.githubPages.reports.v1';
  const ACTIVE_PERIOD_KEY = 'informtit.activePeriod.v2';
  const previousFetch = window.fetch.bind(window);
  const syncedPeriods = new Set();

  const clean = value => String(value ?? '').replace(/\u00a0/g, ' ').trim().replace(/\s+/g, ' ');
  const fold = value => clean(value).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toUpperCase();
  const canonicalPeriodId = value => {
    const raw = clean(value);
    const match = /^(\d{4})-(\d{2})_+(\d{4})-(\d{2})$/.exec(raw);
    return match ? `${match[1]}-${match[2]}_${match[3]}-${match[4]}` : raw;
  };
  const pathOf = input => {
    try { return new URL(typeof input === 'string' ? input : input?.url, window.location.href).pathname; }
    catch (_) { return ''; }
  };
  const methodOf = (input, init) => String(init?.method || input?.method || 'GET').toUpperCase();

  async function bodyOf(input, init) {
    if (init?.body !== undefined && init?.body !== null) {
      if (typeof init.body === 'string') {
        try { return JSON.parse(init.body); } catch (_) { return {}; }
      }
    }
    if (typeof Request !== 'undefined' && input instanceof Request) {
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

  function readLocalReports() {
    try {
      const rows = JSON.parse(localStorage.getItem(REPORTS_KEY) || '[]');
      return Array.isArray(rows) ? rows : [];
    } catch (_) { return []; }
  }

  function writeLocalReports(rows) {
    localStorage.setItem(REPORTS_KEY, JSON.stringify(Array.isArray(rows) ? rows : []));
  }

  function stableId(value) {
    let hash = 2166136261;
    for (const ch of clean(value)) { hash ^= ch.charCodeAt(0); hash = Math.imul(hash, 16777619); }
    return Math.abs(hash >>> 0) || Date.now();
  }

  function reportType(row) {
    return clean(row?.report_type || row?.tipo || row?.type).toLowerCase() === 'pvc' ? 'pvc' : 'normal';
  }

  function periodIdOf(row) {
    return canonicalPeriodId(row?.periodoId || row?.firebase_period_id || row?.period_id || row?.periodId || '');
  }

  function reportKey(row) {
    return `${periodIdOf(row) || fold(row?.period || row?.periodo || '')}::${reportType(row)}`;
  }

  function normalizeSharedReport(raw = {}) {
    const periodId = periodIdOf(raw);
    const type = reportType(raw);
    const id = Number(raw.id || raw.reportId || raw.report_id) || stableId(`${periodId}:${type}`);
    const period = clean(raw.period || raw.periodo || raw.periodName || raw.nombrePeriodo);
    return {
      ...raw,
      id,
      report_type: type,
      periodoId: periodId,
      firebase_period_id: periodId,
      period,
      name: clean(raw.name || raw.nombre || raw.title) || (type === 'pvc' ? 'Informe PVC' : 'Informe Final del Proceso de Titulación'),
      code: clean(raw.code || raw.codigo || raw.code_presencial),
      code_presencial: clean(raw.code_presencial || raw.code || raw.codigo),
      code_online: clean(raw.code_online || raw.codigo_online),
      version: clean(raw.version || raw.versionDocumento) || '1.0',
      status: clean(raw.status || raw.estado) || 'borrador',
      created_at: clean(raw.created_at || raw.createdAt || raw.fechaCreacion),
      updated_at: clean(raw.updated_at || raw.updatedAt || raw.fechaActualizacion),
      careers: Array.isArray(raw.careers) ? raw.careers : [],
      images: Array.isArray(raw.images) ? raw.images : [],
      sections: Array.isArray(raw.sections) ? raw.sections : [],
      legacy_report_ids: Array.isArray(raw.legacy_report_ids) ? raw.legacy_report_ids : [id],
      storage_mode: 'google_sheets_shared',
    };
  }

  function mergeReports(localRows, sharedRows) {
    const map = new Map();
    (localRows || []).forEach(row => map.set(reportKey(row), row));
    (sharedRows || []).forEach(raw => {
      const shared = normalizeSharedReport(raw);
      if (!periodIdOf(shared) || ['ELIMINADO', 'DELETED'].includes(fold(shared.status))) return;
      const key = reportKey(shared);
      const local = map.get(key) || {};
      map.set(key, {
        ...local,
        ...shared,
        careers: shared.careers.length ? shared.careers : (Array.isArray(local.careers) ? local.careers : []),
        images: shared.images.length ? shared.images : (Array.isArray(local.images) ? local.images : []),
        sections: shared.sections.length ? shared.sections : (Array.isArray(local.sections) ? local.sections : []),
        legacy_report_ids: [...new Set([...(local.legacy_report_ids || []), ...(shared.legacy_report_ids || []), local.id, shared.id].filter(Boolean).map(Number))],
      });
    });
    return [...map.values()].sort((a, b) => clean(b.updated_at).localeCompare(clean(a.updated_at)));
  }

  async function loadSharedReports() {
    const periodsPayload = await window.InformtitSheets.periodos();
    const periods = Array.isArray(periodsPayload?.periodos) ? periodsPayload.periodos : [];
    const ids = [...new Set(periods.map(row => canonicalPeriodId(row.periodoId || row.id)).filter(Boolean))].slice(0, 12);
    const groups = await Promise.all(ids.map(async periodId => {
      try {
        const payload = await window.InformtitSheets.informes(periodId);
        const rows = Array.isArray(payload?.informes) ? payload.informes : Array.isArray(payload?.reports) ? payload.reports : Array.isArray(payload?.rows) ? payload.rows : [];
        return rows.map(row => ({ ...row, periodoId: periodIdOf(row) || periodId }));
      } catch (_) {
        return [];
      }
    }));
    return groups.flat();
  }

  function reportPayload(report, extra = {}) {
    const periodId = periodIdOf(report);
    return {
      reportId: Number(report.id || report.reportId || 0) || undefined,
      id: Number(report.id || report.reportId || 0) || undefined,
      periodoId: periodId,
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
      updatedAt: nowIso(),
      ...extra,
    };
  }

  function nowIso() { return new Date().toISOString(); }

  async function persistPeriod(period) {
    if (!period) return;
    const periodId = canonicalPeriodId(period.id || period.periodoId || period.sourceId);
    if (!periodId || syncedPeriods.has(periodId)) return;
    syncedPeriods.add(periodId);
    const match = /^(\d{4})-(\d{2})_(\d{4})-(\d{2})$/.exec(periodId);
    const payload = {
      periodoId: periodId,
      id: periodId,
      nombre: clean(period.name || period.nombre),
      label: clean(period.name || period.nombre),
      anioInicio: match ? Number(match[1]) : undefined,
      mesInicio: match ? Number(match[2]) : undefined,
      anioFin: match ? Number(match[3]) : undefined,
      mesFin: match ? Number(match[4]) : undefined,
      estado: 'ACTIVO',
      updatedAt: nowIso(),
    };
    try {
      await window.InformtitSheets.guardarPeriodo(payload);
      const active = (() => { try { return JSON.parse(localStorage.getItem(ACTIVE_PERIOD_KEY) || 'null'); } catch (_) { return null; } })();
      if (active && canonicalPeriodId(active.id || active.periodoId || active.sourceId) === periodId) {
        localStorage.setItem(ACTIVE_PERIOD_KEY, JSON.stringify({ ...active, source: 'sheets', sourceId: periodId, id: periodId }));
      }
    } catch (error) {
      syncedPeriods.delete(periodId);
      if (typeof window.toast === 'function') window.toast(`No se pudo guardar el período en Google Sheets: ${clean(error?.message || error)}`, true);
    }
  }

  if (document?.addEventListener) {
    document.addEventListener('informtit:period-changed', event => void persistPeriod(event.detail));
  }

  window.fetch = async function pagesSharedStateFetch(input, init = {}) {
    const path = pathOf(input);
    const method = methodOf(input, init);

    if (path === '/api/reports' && method === 'GET') {
      const response = await previousFetch(input, init);
      const payload = await response.clone().json().catch(() => ({}));
      if (!response.ok || payload?.ok === false) return response;
      try {
        const shared = await loadSharedReports();
        const merged = mergeReports(payload.reports || readLocalReports(), shared);
        writeLocalReports(merged);
        return jsonResponse({ ...payload, reports: merged, storage: 'Google Sheets + caché local' }, response.status);
      } catch (_) {
        return response;
      }
    }

    if (path === '/api/reports' && method === 'POST') {
      const before = readLocalReports();
      const response = await previousFetch(input, init);
      const payload = await response.clone().json().catch(() => ({}));
      if (!response.ok || payload?.ok === false) return response;
      const created = payload?.reports?.[0] || readLocalReports().find(row => Number(row.id) === Number(payload.report_id));
      try {
        if (!created) throw new Error('No se pudo identificar el informe creado.');
        await window.InformtitSheets.guardarInforme(reportPayload(created));
        return jsonResponse({ ...payload, storage: 'google_sheets_shared' }, response.status);
      } catch (error) {
        writeLocalReports(before);
        return jsonResponse({ ok: false, error: `No se guardó el informe en Google Sheets: ${clean(error?.message || error)}` }, 502);
      }
    }

    let match = path.match(/^\/api\/reports\/(\d+)$/);
    if (match && method === 'PUT') {
      const before = readLocalReports();
      const response = await previousFetch(input, init);
      const payload = await response.clone().json().catch(() => ({}));
      if (!response.ok || payload?.ok === false) return response;
      try {
        if (!payload.report) throw new Error('No se pudo identificar el informe actualizado.');
        await window.InformtitSheets.guardarInforme(reportPayload(payload.report));
        return jsonResponse({ ...payload, storage: 'google_sheets_shared' }, response.status);
      } catch (error) {
        writeLocalReports(before);
        return jsonResponse({ ok: false, error: `No se guardaron los cambios en Google Sheets: ${clean(error?.message || error)}` }, 502);
      }
    }

    if (match && method === 'DELETE') {
      const before = readLocalReports();
      const target = before.find(row => Number(row.id) === Number(match[1]) || (row.legacy_report_ids || []).some(id => Number(id) === Number(match[1])));
      const response = await previousFetch(input, init);
      const payload = await response.clone().json().catch(() => ({}));
      if (!response.ok || payload?.ok === false) return response;
      try {
        if (target) await window.InformtitSheets.guardarInforme(reportPayload(target, { status: 'ELIMINADO', deleted: true }));
        return response;
      } catch (error) {
        writeLocalReports(before);
        return jsonResponse({ ok: false, error: `No se pudo eliminar el informe compartido: ${clean(error?.message || error)}` }, 502);
      }
    }

    return previousFetch(input, init);
  };

  window.InformtitSharedState = Object.freeze({ loadSharedReports, mergeReports, persistPeriod, version: '1.0.0' });
})();
