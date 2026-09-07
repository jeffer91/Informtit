(() => {
  'use strict';

  if (!/(^|\.)github\.io$/i.test(window.location.hostname)) return;

  const previousFetch = window.fetch.bind(window);

  function clean(value = '') {
    return String(value ?? '').replace(/\u00a0/g, ' ').trim().replace(/\s+/g, ' ');
  }

  function normalize(value = '') {
    return clean(value)
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, ' ')
      .trim();
  }

  function canonicalCareer(value = '') {
    let text = clean(value)
      .replace(/^(?:TECNOLOG[IÍ]A|T[EÉ]CNICO)\s+SUPERIOR(?:\s+UNIVERSITARIA)?\s+EN\s+/i, '')
      .replace(/\s+(?:ONLINE|EN\s+L[IÍ]NEA|VIRTUAL|PRESENCIAL)\s*$/i, '')
      .trim();

    const key = normalize(text);
    if (key.includes('redes') && key.includes('telecomunicaciones')) {
      return 'REDES Y TELECOMUNICACIONES';
    }
    return text ? text.toLocaleUpperCase('es') : 'SIN CARRERA';
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
    return new Response(JSON.stringify(payload), {
      status,
      headers: { 'Content-Type': 'application/json; charset=utf-8' },
    });
  }

  function careerOf(student = {}) {
    return clean(
      student.career_name
      || student.career
      || student.carrera
      || student.nombreCarrera
      || student.nombre_carrera
      || student.program
      || student.programa
      || '',
    );
  }

  function uniqueCareers(values) {
    const seen = new Map();
    values.forEach(value => {
      const career = canonicalCareer(value);
      const key = normalize(career);
      if (key && key !== 'sin carrera' && !seen.has(key)) seen.set(key, career);
    });
    return [...seen.values()].sort((a, b) => a.localeCompare(b, 'es', { sensitivity: 'base' }));
  }

  async function readJsonSafe(response) {
    try { return await response.clone().json(); }
    catch (_) { return null; }
  }

  window.fetch = async function nucleiCareerNormalizedFetch(input, init = {}) {
    const path = pathOf(input);
    const method = methodOf(input, init);
    const match = path.match(/^\/api\/reports\/(\d+)\/nuclei$/);

    if (!match || method !== 'GET') return previousFetch(input, init);

    const response = await previousFetch(input, init);
    if (!response.ok) return response;

    const payload = await readJsonSafe(response);
    if (!payload || typeof payload !== 'object') return response;

    const courses = Array.isArray(payload.courses)
      ? payload.courses.map(course => ({
          ...course,
          career_name: canonicalCareer(course?.career_name),
        }))
      : [];

    let rosterCareers = [];
    try {
      const rosterResponse = await previousFetch(`/api/reports/${Number(match[1])}/students-domain`, { cache: 'no-store' });
      if (rosterResponse.ok) {
        const rosterPayload = await rosterResponse.json();
        rosterCareers = (Array.isArray(rosterPayload?.students) ? rosterPayload.students : [])
          .map(careerOf)
          .filter(Boolean);
      }
    } catch (_) {}

    const careers = uniqueCareers([
      ...rosterCareers,
      ...courses.map(course => course.career_name),
    ]);

    const normalized = {
      ...payload,
      courses,
      careers,
      normalization: {
        career_mode: 'canonical',
        aliases_collapsed: true,
      },
    };

    if (normalized.excel_import && typeof normalized.excel_import === 'object') {
      normalized.excel_import = {
        ...normalized.excel_import,
        careers: careers.length,
      };
    }

    return jsonResponse(normalized, response.status);
  };

  window.informtitNucleiCareer = Object.freeze({
    canonicalCareer,
    normalize,
  });
})();