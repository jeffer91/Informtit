(() => {
  'use strict';

  const BASE_URL = 'https://script.google.com/macros/s/AKfycbwbruJOI81E8s7zyxX7y-Wb5ruP0Vnjo_J2Qbe1yPrQ1CTWUHilHTg9NbNR7w9oR2pM/exec';

  function sleep(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }

  async function parseJsonResponse(response) {
    const text = await response.text();
    let data;
    try { data = JSON.parse(text || '{}'); }
    catch { throw new Error('Apps Script devolvió una respuesta no válida.'); }
    if (!response.ok || data?.ok === false) throw new Error(data?.error || `Error ${response.status}`);
    return data;
  }

  async function get(action, params = {}, options = {}) {
    const url = new URL(BASE_URL);
    url.searchParams.set('action', action);
    Object.entries(params || {}).forEach(([key, value]) => {
      if (value !== undefined && value !== null && String(value) !== '') url.searchParams.set(key, String(value));
    });
    const attempts = Math.max(1, Number(options.attempts || 2));
    let lastError;
    for (let attempt = 0; attempt < attempts; attempt += 1) {
      try {
        const response = await fetch(url.toString(), { method: 'GET', cache: 'no-store', redirect: 'follow' });
        return await parseJsonResponse(response);
      } catch (error) {
        lastError = error;
        if (attempt + 1 < attempts) await sleep(350 * (attempt + 1));
      }
    }
    throw lastError;
  }

  async function post(action, data, options = {}) {
    const attempts = Math.max(1, Number(options.attempts || 2));
    let lastError;
    for (let attempt = 0; attempt < attempts; attempt += 1) {
      try {
        const response = await fetch(BASE_URL, {
          method: 'POST', headers: { 'Content-Type': 'text/plain;charset=UTF-8' },
          body: JSON.stringify({ action, data }), redirect: 'follow'
        });
        return await parseJsonResponse(response);
      } catch (error) {
        lastError = error;
        if (attempt + 1 < attempts) await sleep(450 * (attempt + 1));
      }
    }
    throw lastError;
  }

  async function postMany(items, options = {}) {
    const queue = Array.from(items || []);
    const concurrency = Math.max(1, Math.min(5, Number(options.concurrency || 3)));
    const results = new Array(queue.length);
    let cursor = 0, completed = 0;
    async function worker() {
      while (true) {
        const index = cursor++;
        if (index >= queue.length) return;
        const item = queue[index];
        try { results[index] = { ok: true, result: await post(item.action, item.data, { attempts: 2 }), item }; }
        catch (error) { results[index] = { ok: false, error: error.message || String(error), item }; }
        completed += 1;
        if (typeof options.onProgress === 'function') options.onProgress(completed, queue.length, results[index]);
      }
    }
    await Promise.all(Array.from({ length: concurrency }, () => worker()));
    return results;
  }

  window.InformtitSheets = {
    baseUrl: BASE_URL, get, post, postMany,
    ping: () => get('ping', {}, { attempts: 1 }),
    periodos: () => get('periodos'),
    estudiantes: () => get('estudiantes'),
    matriculas: periodoId => get('matriculas', { periodoId }),
    requisitos: periodoId => get('requisitos', { periodoId }),
    nucleos: periodoId => get('nucleos', { periodoId }),
    complexivo: periodoId => get('complexivo', { periodoId }),
    trabajoTitulacion: periodoId => get('trabajo_titulacion', { periodoId }),
    informes: periodoId => get('informes', { periodoId }),
    guardarRequisito: data => post('guardar_requisito', data),
    guardarNucleo: data => post('guardar_nucleo', data),
    guardarComplexivo: data => post('guardar_complexivo', data),
    guardarTrabajoTitulacion: data => post('guardar_trabajo_titulacion', data),
  };
})();
