(() => {
  'use strict';

  if (!/(^|\.)github\.io$/i.test(window.location.hostname)) return;

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

  function catalogIds() {
    const rows = Array.isArray(window.informtitNucleiPaste?.catalog)
      ? window.informtitNucleiPaste.catalog
      : [];
    return new Set(rows.map(item => Number(item.courseId)).filter(Number.isFinite));
  }

  function detectCourseIds(text) {
    const source = String(text || '');
    const known = catalogIds();
    const detected = new Set();

    const patterns = [
      /(?:[?&]|\\&|\\u0026)course=(\d+)/gi,
      /course\/view\.php\?id=(\d+)/gi,
      /grade\/report\/(?:grader|overview|user)\/index\.php\?id=(\d+)/gi,
      /grade\/report\/grader\/index\.php[^\n\r)]*?[?&]id=(\d+)/gi,
    ];

    patterns.forEach(pattern => {
      for (const match of source.matchAll(pattern)) {
        const id = Number(match[1]);
        if (known.has(id)) detected.add(id);
      }
    });

    // El texto copiado desde Moodle puede llegar con los enlaces parcialmente
    // transformados por el navegador/Markdown. Como último respaldo, si solo
    // aparece un ID conocido del catálogo de aulas, se toma como aula Moodle.
    if (!detected.size) {
      const presentKnownIds = [...known].filter(id => {
        const pattern = new RegExp(`(^|\\D)${id}(?!\\d)`);
        return pattern.test(source);
      });
      if (presentKnownIds.length === 1) detected.add(presentKnownIds[0]);
    }

    return [...detected];
  }

  async function requestPayload(input, init) {
    if (typeof init?.body === 'string') {
      try { return JSON.parse(init.body); } catch (_) { return null; }
    }
    if (input instanceof Request) {
      try { return await input.clone().json(); } catch (_) { return null; }
    }
    return null;
  }

  window.fetch = async function nucleiPasteCourseDetectionFetch(input, init = {}) {
    const path = pathOf(input);
    const method = methodOf(input, init);
    if (!/^\/api\/reports\/\d+\/nuclei\/import-text$/.test(path) || method !== 'POST') {
      return previousFetch(input, init);
    }

    const payload = await requestPayload(input, init);
    if (!payload || Number(payload.course_id || 0)) return previousFetch(input, init);

    const detected = detectCourseIds(payload.text);
    if (detected.length === 1) {
      const nextInit = {
        ...init,
        body: JSON.stringify({ ...payload, course_id: detected[0] }),
      };
      return previousFetch(input, nextInit);
    }

    return previousFetch(input, init);
  };

  window.informtitNucleiCourseDetectionFix = Object.freeze({
    detectCourseIds,
  });
})();
