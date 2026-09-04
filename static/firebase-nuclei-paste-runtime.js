(() => {
  'use strict';

  if (!/(^|\.)github\.io$/i.test(window.location.hostname)) return;

  const PROJECT_ID = 'utet-4387a';
  const API_KEY = 'AIzaSyCaHf1C0BB0X_H3BDZ1o-UDAsPmLTjsZLA';
  const FIRESTORE_ROOT = `https://firestore.googleapis.com/v1/projects/${PROJECT_ID}/databases/(default)`;
  const REPORTS_KEY = 'informtit.githubPages.reports.v1';
  const previousFetch = window.fetch.bind(window);
  const PERIOD_ID = '2025-10__2026-03';

  const COURSE_CATALOG = Object.freeze([
    {courseId:9235,career:'TÉCNICO SUPERIOR EN ENFERMERÍA',subject:'T- Nucleo 1 Enfermeria',campus:'Manta',code:'540913A01-P-1701-701-MEC-A-oct2025-mar2026-sem-hibrida-ENFMOD11G1-Manta',nucleus:1},
    {courseId:9236,career:'TÉCNICO SUPERIOR EN ENFERMERÍA',subject:'T- Nucleo 1 Enfermeria',campus:'Sur',code:'540913A01-P-1701-701-S-A-oct2025-mar2026-sem-hibrida-ENFMOD11G1-Sur',nucleus:1},
    {courseId:9237,career:'TÉCNICO SUPERIOR EN ENFERMERÍA',subject:'T- Nucleo 2 Enfermeria',campus:'Manta',code:'540913A01-P-1701-702-MEC-A-oct2025-mar2026-sem-hibrida-ENFMOD12G1-Manta',nucleus:2},
    {courseId:9238,career:'TÉCNICO SUPERIOR EN ENFERMERÍA',subject:'T- Nucleo 2 Enfermeria',campus:'Sur',code:'540913A01-P-1701-702-S-A-oct2025-mar2026-sem-hibrida-ENFMOD12G1-Sur',nucleus:2},
    {courseId:9239,career:'TÉCNICO SUPERIOR EN ENFERMERÍA',subject:'T- Nucleo 3 Enfermeria',campus:'Manta',code:'540913A01-P-1701-703-MEC-A-oct2025-mar2026-sem-hibrida-ENFMOD13G1-Manta',nucleus:3},
    {courseId:9240,career:'TÉCNICO SUPERIOR EN ENFERMERÍA',subject:'T- Nucleo 3 Enfermeria',campus:'Sur',code:'540913A01-P-1701-703-S-A-oct2025-mar2026-sem-hibrida-ENFMOD13G1-Sur',nucleus:3},
    {courseId:9241,career:'TÉCNICO SUPERIOR EN ENFERMERÍA',subject:'T- Nucleo 4 Enfermeria',campus:'Manta',code:'540913A01-P-1701-704-MEC-A-oct2025-mar2026-sem-hibrida-ENFMOD14G1-Manta',nucleus:4},
    {courseId:9242,career:'TÉCNICO SUPERIOR EN ENFERMERÍA',subject:'T- Nucleo 4 Enfermeria',campus:'Sur',code:'540913A01-P-1701-704-S-A-oct2025-mar2026-sem-hibrida-ENFMOD14G1-Sur',nucleus:4},
    {courseId:9262,career:'TECNOLOGÍA SUPERIOR EN ADMINISTRACIÓN',subject:'T-Nucleo - Gestión Comercial',campus:'Matriz',code:'550413A02-P-1701-717-M-A-oct2025-mar2026-sem-hibrida-ADMMOD13-Matriz',nucleus:4},
    {courseId:9261,career:'TECNOLOGÍA SUPERIOR EN ADMINISTRACIÓN',subject:'T-Nucleo - Gestión de Procesos y Calidad',campus:'Matriz',code:'550413A02-P-1701-716-M-A-oct2025-mar2026-sem-hibrida-ADMMOD12-Matriz',nucleus:2},
    {courseId:9259,career:'TECNOLOGÍA SUPERIOR EN ADMINISTRACIÓN',subject:'T-Nucleo - Gestión Estratégica',campus:'Matriz',code:'550413A02-P-1701-714-M-A-oct2025-mar2026-sem-hibrida-ADMMOD14-Matriz',nucleus:1},
    {courseId:9260,career:'TECNOLOGÍA SUPERIOR EN ADMINISTRACIÓN',subject:'T-Nucleo - Gestión Financiera',campus:'Matriz',code:'550413A02-P-1701-715-M-A-oct2025-mar2026-sem-hibrida-ADMMOD11-Matriz',nucleus:3},
    {courseId:9256,career:'TECNOLOGÍA SUPERIOR EN CONTABILIDAD',subject:'T- Contabilidad de Costos',campus:'Matriz',code:'550411C02-P-1701-718-M-A-oct2025-mar2026-sem-hibrida-CONTMOD13-Matriz',nucleus:2},
    {courseId:9255,career:'TECNOLOGÍA SUPERIOR EN CONTABILIDAD',subject:'T- Contabilidad Financiera',campus:'Matriz',code:'550411C02-P-1701-717-M-A-oct2025-mar2026-sem-hibrida-CONTMOD12-Matriz',nucleus:1},
    {courseId:9258,career:'TECNOLOGÍA SUPERIOR EN CONTABILIDAD',subject:'T- Gestión Financiera',campus:'Matriz',code:'550411C02-P-1701-720-M-A-oct2025-mar2026-sem-hibrida-CONTMOD14-Matriz',nucleus:4},
    {courseId:9257,career:'TECNOLOGÍA SUPERIOR EN CONTABILIDAD',subject:'T- Tributación',campus:'Matriz',code:'550411C02-P-1701-719-M-A-oct2025-mar2026-sem-hibrida-CONTMOD11-Matriz',nucleus:3},
    {courseId:9275,career:'TECNOLOGÍA SUPERIOR EN DESARROLLO DE SOFTWARE',subject:'T-Nucleo 1 Desarrollo SW',campus:'Sur',code:'550613A01-P-1701-701-S-A-oct2025-mar2026-sem-hibrida-DESMOD11G1-Sur',nucleus:1},
    {courseId:9276,career:'TECNOLOGÍA SUPERIOR EN DESARROLLO DE SOFTWARE',subject:'T-Nucleo 2 Desarrollo SW',campus:'Sur',code:'550613A01-P-1701-702-S-A-oct2025-mar2026-sem-hibrida-DESMOD12G1-Sur',nucleus:2},
    {courseId:9277,career:'TECNOLOGÍA SUPERIOR EN DESARROLLO DE SOFTWARE',subject:'T-Nucleo 3 Desarrollo SW',campus:'Sur',code:'550613A01-P-1701-703-S-A-oct2025-mar2026-sem-hibrida-DESMOD13G1-Sur',nucleus:3},
    {courseId:9278,career:'TECNOLOGÍA SUPERIOR EN DESARROLLO DE SOFTWARE',subject:'T-Nucleo 4 Desarrollo SW',campus:'Sur',code:'550613A01-P-1701-704-S-A-oct2025-mar2026-sem-hibrida-DESMOD14G1-Sur',nucleus:4},
    {courseId:9251,career:'TECNOLOGÍA SUPERIOR EN EDUCACIÓN BÁSICA',subject:'T-Núcleo 1: Psicología y neuroeducación en el entorno educativo',campus:'Matriz',code:'550113A01-P-1701-701-M-A-oct2025-mar2026-sem-hibrida-EBAMOD1G1-Matriz',nucleus:1},
    {courseId:9252,career:'TECNOLOGÍA SUPERIOR EN EDUCACIÓN BÁSICA',subject:'T-Núcleo 2: Aprendizaje y enseñanza en Educación Básica',campus:'Matriz',code:'550113A01-P-1701-702-M-A-oct2025-mar2026-sem-hibrida-EBAMOD2G1-Matriz',nucleus:2},
    {courseId:9253,career:'TECNOLOGÍA SUPERIOR EN EDUCACIÓN BÁSICA',subject:'T-Núcleo 3: Pedagogía, Sistema y Teoría del Aprendizaje',campus:'Matriz',code:'550113A01-P-1701-703-M-A-oct2025-mar2026-sem-hibrida-EBAMOD3G1-Matriz',nucleus:3},
    {courseId:9254,career:'TECNOLOGÍA SUPERIOR EN EDUCACIÓN BÁSICA',subject:'T-Núcleo 4: Planificación y Diseño Curricular',campus:'Matriz',code:'550113A01-P-1701-704-M-A-oct2025-mar2026-sem-hibrida-EBAMOD4G1-Matriz',nucleus:4},
    {courseId:9243,career:'TECNOLOGÍA SUPERIOR EN EDUCACIÓN INICIAL',subject:'T-Nucleo EI - DESARROLLO INTEGRAL',campus:'Matriz',code:'550112A01-P-1701-717-M-A-oct2025-mar2026-sem-hibrida-EDIMOD2G1-Matriz',nucleus:1},
    {courseId:9244,career:'TECNOLOGÍA SUPERIOR EN EDUCACIÓN INICIAL',subject:'T-Nucleo EI - DESARROLLO INTEGRAL',campus:'Matriz',code:'550112A01-P-1701-717-M-B-oct2025-mar2026-sem-hibrida-EDIMOD1G2-Matriz',nucleus:1},
    {courseId:9247,career:'TECNOLOGÍA SUPERIOR EN EDUCACIÓN INICIAL',subject:'T-Nucleo EI - GERENCIA PEDAGOGICA',campus:'Matriz',code:'550112A01-P-1701-719-M-A-oct2025-mar2026-sem-hibrida-EDIMOD4G1-Matriz',nucleus:2},
    {courseId:9248,career:'TECNOLOGÍA SUPERIOR EN EDUCACIÓN INICIAL',subject:'T-Nucleo EI - GERENCIA PEDAGOGICA',campus:'Matriz',code:'550112A01-P-1701-719-M-B-oct2025-mar2026-sem-hibrida-EDIMOD3G2-Matriz',nucleus:2},
    {courseId:9249,career:'TECNOLOGÍA SUPERIOR EN EDUCACIÓN INICIAL',subject:'T-Nucleo EI - HABILIDADES NEUROLINGUISTICAS',campus:'Matriz',code:'550112A01-P-1701-720-M-A-oct2025-mar2026-sem-hibrida-EDIMOD3G1-Matriz',nucleus:4},
    {courseId:9250,career:'TECNOLOGÍA SUPERIOR EN EDUCACIÓN INICIAL',subject:'T-Nucleo EI - HABILIDADES NEUROLINGUISTICAS',campus:'Matriz',code:'550112A01-P-1701-720-M-B-oct2025-mar2026-sem-hibrida-EDIMOD4G2-Matriz',nucleus:4},
    {courseId:9245,career:'TECNOLOGÍA SUPERIOR EN EDUCACIÓN INICIAL',subject:'T-Nucleo EI - PLANIFICACION Y DISEÑO CURRICULAR',campus:'Matriz',code:'550112A01-P-1701-718-M-A-oct2025-mar2026-sem-hibrida-EDIMOD1G1-Matriz',nucleus:3},
    {courseId:9246,career:'TECNOLOGÍA SUPERIOR EN EDUCACIÓN INICIAL',subject:'T-Nucleo EI - PLANIFICACION Y DISEÑO CURRICULAR',campus:'Matriz',code:'550112A01-P-1701-718-M-B-oct2025-mar2026-sem-hibrida-EDIMOD1G2-Matriz',nucleus:3},
    {courseId:9279,career:'TECNOLOGÍA SUPERIOR EN ESTÉTICA INTEGRAL',subject:'T-NUCLEO 1 EVALUACIÓN Y TRATAMIENTOS ESTÉTICOS FACIALES',campus:'Sur',code:'551012C02-P-1701-701-S-A-oct2025-mar2026-sem-hibrida-ESTMOD11G1-Sur',nucleus:1},
    {courseId:9280,career:'TECNOLOGÍA SUPERIOR EN ESTÉTICA INTEGRAL',subject:'T-NUCLEO 2 TERAPIAS Y PROCEDIMIENTOS ESTÉTICOS CORPORALES',campus:'Sur',code:'551012C02-P-1701-702-S-A-oct2025-mar2026-sem-hibrida-ESTMOD12G1-Sur',nucleus:2},
    {courseId:9281,career:'TECNOLOGÍA SUPERIOR EN ESTÉTICA INTEGRAL',subject:'T-NUCLEO 3 ESTÉTICA CAPILAR, COSMETOLOGÍA COMPLEMENTARIA Y BIOSEGURIDAD',campus:'Sur',code:'551012C02-P-1701-703-S-A-oct2025-mar2026-sem-hibrida-ESTMOD13G1-Sur',nucleus:3},
    {courseId:9282,career:'TECNOLOGÍA SUPERIOR EN ESTÉTICA INTEGRAL',subject:'T-NUCLEO 4 ASESORÍA DE IMAGEN, VISAGISMO Y DERMOESTÉTICA APLICADA',campus:'Sur',code:'551012C02-P-1701-704-S-A-oct2025-mar2026-sem-hibrida-ESTMOD14G1-Sur',nucleus:4},
    {courseId:9267,career:'TECNOLOGÍA SUPERIOR EN GESTIÓN DEL TALENTO HUMANO',subject:'T-Nucleo - Administración de la  compensación y beneficios laborales',campus:'Matriz',code:'550417A01-P-1701-714-M-A-oct2025-mar2026-sem-hibrida-GTHMOD12-Matriz',nucleus:1},
    {courseId:9268,career:'TECNOLOGÍA SUPERIOR EN GESTIÓN DEL TALENTO HUMANO',subject:'T-Nucleo - Atracción y gestión de talento humano',campus:'Matriz',code:'550417A01-P-1701-715-M-A-oct2025-mar2026-sem-hibrida-GTHMOD13-Matriz',nucleus:2},
    {courseId:9270,career:'TECNOLOGÍA SUPERIOR EN GESTIÓN DEL TALENTO HUMANO',subject:'T-Nucleo - Desarrollo y evaluación organizacional',campus:'Matriz',code:'550417A01-P-1701-717-M-A-oct2025-mar2026-sem-hibrida-GTHMOD14-Matriz',nucleus:4},
    {courseId:9269,career:'TECNOLOGÍA SUPERIOR EN GESTIÓN DEL TALENTO HUMANO',subject:'T-Nucleo - Seguridad y Salud del Trabajo',campus:'Matriz',code:'550417A01-P-1701-716-M-A-oct2025-mar2026-sem-hibrida-GTHMOD11-Matriz',nucleus:3},
    {courseId:9264,career:'TECNOLOGÍA SUPERIOR EN MARKETING DIGITAL Y COMERCIO ELECTRÓNICO',subject:'T-Nucleo - Acción del Marketing',campus:'Matriz',code:'550414G01-P-1701-714-M-A-oct2025-mar2026-sem-hibrida-MKTMOD11G1-Matriz',nucleus:4},
    {courseId:9263,career:'TECNOLOGÍA SUPERIOR EN MARKETING DIGITAL Y COMERCIO ELECTRÓNICO',subject:'T-Nucleo - Bases del Marketing',campus:'Matriz',code:'550414G01-P-1701-713-M-A-oct2025-mar2026-sem-hibrida-MKTMOD14G1-Matriz',nucleus:1},
    {courseId:9266,career:'TECNOLOGÍA SUPERIOR EN MARKETING DIGITAL Y COMERCIO ELECTRÓNICO',subject:'T-Nucleo - Comunicación',campus:'Matriz',code:'550414G01-P-1701-716-M-A-oct2025-mar2026-sem-hibrida-MKTMOD13G1-Matriz',nucleus:3},
    {courseId:9265,career:'TECNOLOGÍA SUPERIOR EN MARKETING DIGITAL Y COMERCIO ELECTRÓNICO',subject:'T-Nucleo - El consumidor',campus:'Matriz',code:'550414G01-P-1701-715-M-A-oct2025-mar2026-sem-hibrida-MKTMOD12G1-Matriz',nucleus:2},
    {courseId:9271,career:'TECNOLOGÍA SUPERIOR EN REDES Y TELECOMUNICACIONES',subject:'T-Nucleo 1 Redes',campus:'Sur',code:'550612E02-P-1701-712-S-A-oct2025-mar2026-sem-hibrida-REDMOD11G1-Sur',nucleus:1},
    {courseId:9272,career:'TECNOLOGÍA SUPERIOR EN REDES Y TELECOMUNICACIONES',subject:'T-Nucleo 2 Redes',campus:'Sur',code:'550612E02-P-1701-713-S-A-oct2025-mar2026-sem-hibrida-REDMOD12G1-Sur',nucleus:2},
    {courseId:9273,career:'TECNOLOGÍA SUPERIOR EN REDES Y TELECOMUNICACIONES',subject:'T-Nucleo 3 Redes',campus:'Sur',code:'550612E02-P-1701-714-S-A-oct2025-mar2026-sem-hibrida-REDMOD13G1-Sur',nucleus:3},
    {courseId:9274,career:'TECNOLOGÍA SUPERIOR EN REDES Y TELECOMUNICACIONES',subject:'T-Nucleo 4 Redes',campus:'Sur',code:'550612E02-P-1701-715-S-A-oct2025-mar2026-sem-hibrida-REDMOD14G1-Sur',nucleus:4},
    {courseId:9287,career:'TECNOLOGÍA SUPERIOR EN SEGURIDAD CIUDADANA Y ORDEN PÚBLICO ONLINE',subject:'T-NUCLEO 1 SEGURIDAD CIUDADANA',campus:'Matriz',code:'551032A02-L-1701-701-M-A-oct2025-mar2026-sem-hibrida-SCOPMOD14G1-Matriz',nucleus:1},
    {courseId:9288,career:'TECNOLOGÍA SUPERIOR EN SEGURIDAD CIUDADANA Y ORDEN PÚBLICO ONLINE',subject:'T-NUCLEO 2 PROCESOS DE SEGURIDAD',campus:'Matriz',code:'551032A02-L-1701-702-M-A-oct2025-mar2026-sem-hibrida-SCOPMOD12G1-Matriz',nucleus:2},
    {courseId:9289,career:'TECNOLOGÍA SUPERIOR EN SEGURIDAD CIUDADANA Y ORDEN PÚBLICO ONLINE',subject:'T-NUCLEO 3 LEGISLACIÓN EN SEGURIDAD',campus:'Matriz',code:'551032A02-L-1701-703-M-A-oct2025-mar2026-sem-hibrida-SCOPMOD11-Matriz',nucleus:3},
    {courseId:9286,career:'TECNOLOGÍA SUPERIOR EN SEGURIDAD CIUDADANA Y ORDEN PÚBLICO ONLINE',subject:'T-NUCLEO 4 INVESTIGACIÓN EN SEGURIDAD',campus:'Matriz',code:'551032A02-L-1701-704-M-A-oct2025-mar2026-sem-hibrida-SCOPMOD13G1-Matriz',nucleus:4},
  ]);

  const CATALOG_BY_ID = new Map(COURSE_CATALOG.map(item => [Number(item.courseId), item]));

  function clean(value) {
    return String(value ?? '').replace(/\\@/g, '@').replace(/\u00a0/g, ' ').trim().replace(/\s+/g, ' ');
  }

  function fold(value) {
    return clean(value).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toUpperCase();
  }

  function pathOf(input) {
    try {
      const raw = typeof input === 'string' ? input : input?.url;
      return new URL(raw, window.location.href).pathname;
    } catch (_) { return ''; }
  }

  function methodOf(input, init) {
    return String(init?.method || input?.method || 'GET').toUpperCase();
  }

  async function bodyOf(input, init) {
    if (init?.body !== undefined && init?.body !== null && typeof init.body === 'string') {
      try { return JSON.parse(init.body); } catch (_) { return {}; }
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

  function reportById(reportId) {
    try {
      const reports = JSON.parse(window.localStorage.getItem(REPORTS_KEY) || '[]');
      if (!Array.isArray(reports)) return null;
      return reports.find(report => Number(report.id) === Number(reportId)
        || (report.legacy_report_ids || []).some(id => Number(id) === Number(reportId))) || null;
    } catch (_) { return null; }
  }

  function encodeValue(value) {
    if (value === null || value === undefined) return { nullValue: null };
    if (typeof value === 'boolean') return { booleanValue: value };
    if (Number.isInteger(value)) return { integerValue: String(value) };
    if (typeof value === 'number') return { doubleValue: value };
    if (Array.isArray(value)) return { arrayValue: { values: value.map(encodeValue) } };
    if (typeof value === 'object') {
      return { mapValue: { fields: Object.fromEntries(Object.entries(value).map(([key, item]) => [key, encodeValue(item)])) } };
    }
    return { stringValue: String(value) };
  }

  async function putDocument(collection, documentId, data) {
    const url = new URL(`${FIRESTORE_ROOT}/documents/${collection}/${encodeURIComponent(documentId)}`);
    url.searchParams.set('key', API_KEY);
    const fields = Object.fromEntries(Object.entries(data).map(([key, value]) => [key, encodeValue(value)]));
    const response = await previousFetch(url.toString(), {
      method: 'PATCH',
      headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
      body: JSON.stringify({ fields }),
      cache: 'no-store',
    });
    if (!response.ok) {
      let detail = '';
      try { detail = clean((await response.json())?.error?.message); } catch (_) {}
      throw new Error(`Firebase ${response.status}${detail ? `: ${detail}` : ''}`);
    }
    return response.json();
  }

  function parseCourseIds(text) {
    const ids = new Set();
    const source = String(text || '');
    for (const match of source.matchAll(/(?:[?&\\]course=|course\/view\.php\?id=)(\d+)/gi)) ids.add(Number(match[1]));
    return [...ids].filter(id => CATALOG_BY_ID.has(id));
  }

  function extractEmail(text) {
    const normalized = String(text || '').replace(/\\@/g, '@');
    const match = normalized.match(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i);
    return match ? match[0].toLowerCase() : '';
  }

  function extractMoodleUserId(text) {
    const match = String(text || '').match(/user\/view\.php\?id=(\d+)/i);
    return match ? clean(match[1]) : '';
  }

  function markdownLabel(text) {
    let value = String(text || '');
    const bold = value.match(/\*\*([^*]+)\*\*/);
    if (bold) value = bold[1];
    else {
      const link = value.match(/\[([^\]]+)\]\([^)]*\)/);
      if (link) value = link[1];
    }
    return clean(value.replace(/\[[^\]]*\]\([^)]*\)/g, ' ').replace(/https?:\/\/\S+/gi, ' ').replace(/\*\*/g, ' '));
  }

  function numbersAfterEmail(text, email) {
    let value = String(text || '').replace(/\\@/g, '@');
    const index = email ? value.toLowerCase().indexOf(email.toLowerCase()) : -1;
    if (index >= 0) value = value.slice(index + email.length);
    value = value
      .replace(/\([^)]*https?:\/\/[^)]*\)/gi, ' ')
      .replace(/https?:\/\/\S+/gi, ' ')
      .replace(/\b(?:id|course|rev)=\d+\b/gi, ' ');
    return [...value.matchAll(/(?<!\d)(10(?:[.,]00)?|[0-9](?:[.,]\d{1,2})?)(?!\d)/g)]
      .map(match => Number(match[1].replace(',', '.')))
      .filter(number => Number.isFinite(number) && number >= 0 && number <= 10);
  }

  function parseMarkdownRows(text) {
    const rows = [];
    String(text || '').split(/\r?\n/).forEach(raw => {
      if (!raw.includes('|')) return;
      const email = extractEmail(raw);
      if (!email) return;
      const cells = raw.split('|').map(cell => cell.trim()).filter(Boolean);
      const emailIndex = cells.findIndex(cell => extractEmail(cell) === email);
      if (emailIndex < 0) return;
      const numbers = numbersAfterEmail(cells.slice(emailIndex + 1).join(' | '), '');
      if (!numbers.length) return;
      rows.push({
        raw_name: markdownLabel(cells[0]),
        email,
        moodle_user_id: extractMoodleUserId(raw),
        final_grade: numbers[numbers.length - 1],
      });
    });
    return rows;
  }

  function plainNameBeforeEmail(lines, emailIndex, email) {
    const same = clean(lines[emailIndex].replace(/\\@/g, '@').split(email)[0]);
    if (same && same.length > 3) return markdownLabel(same);
    for (let index = emailIndex - 1; index >= Math.max(0, emailIndex - 5); index -= 1) {
      const candidate = markdownLabel(lines[index]);
      if (!candidate || /direcci[oó]n de correo|nombre\s*\/\s*apellido|ocultar|svg/i.test(candidate)) continue;
      if (/^\d+(?:[.,]\d+)?$/.test(candidate)) continue;
      return candidate;
    }
    return '';
  }

  function parsePlainRows(text) {
    const lines = String(text || '').split(/\r?\n/).map(line => line.trim()).filter(Boolean);
    const indexes = lines.map((line, index) => extractEmail(line) ? index : -1).filter(index => index >= 0);
    return indexes.map((emailIndex, position) => {
      const email = extractEmail(lines[emailIndex]);
      const end = position + 1 < indexes.length ? indexes[position + 1] : lines.length;
      const chunk = lines.slice(emailIndex, end).join(' ');
      const numbers = numbersAfterEmail(chunk, email);
      return {
        raw_name: plainNameBeforeEmail(lines, emailIndex, email),
        email,
        moodle_user_id: extractMoodleUserId(lines.slice(Math.max(0, emailIndex - 3), end).join(' ')),
        final_grade: numbers.length ? numbers[numbers.length - 1] : null,
      };
    }).filter(row => row.email && row.final_grade !== null);
  }

  function dedupeRows(rows) {
    const map = new Map();
    rows.forEach(row => {
      const key = clean(row.email || row.moodle_user_id || fold(row.raw_name));
      if (key) map.set(key, row);
    });
    return [...map.values()];
  }

  function parseRows(text) {
    const markdown = parseMarkdownRows(text);
    const rows = markdown.length ? markdown : parsePlainRows(text);
    return dedupeRows(rows);
  }

  function nameTokens(value) {
    return fold(value).replace(/[^A-Z0-9 ]+/g, ' ').split(/\s+/).filter(token => token.length >= 2);
  }

  function fuzzyNameScore(rawName, officialName) {
    const raw = nameTokens(rawName);
    const official = nameTokens(officialName);
    if (!raw.length || !official.length) return 0;
    let hits = 0;
    official.forEach(token => {
      if (raw.some(candidate => candidate === token || candidate.endsWith(token) || token.endsWith(candidate))) hits += 1;
    });
    return hits / official.length;
  }

  function buildMaster(students, existingCourses) {
    const byEmail = new Map();
    const byId = new Map();
    const byMoodleUser = new Map();
    const rows = Array.isArray(students) ? students : [];
    rows.forEach(student => {
      const email = clean(student.email || student.personal_email).toLowerCase();
      const id = clean(student.identification || student.cedula);
      if (email) byEmail.set(email, student);
      if (id) byId.set(id, student);
    });
    (existingCourses || []).forEach(course => {
      (course.students || []).forEach(student => {
        const moodleId = clean(student.moodle_user_id || student.moodleUserId);
        const id = clean(student.identification || student.cedula);
        const official = id ? byId.get(id) : null;
        if (moodleId && official) byMoodleUser.set(moodleId, official);
      });
    });
    return { rows, byEmail, byId, byMoodleUser };
  }

  function matchStudent(row, master) {
    if (row.email && master.byEmail.has(row.email)) {
      return { student: master.byEmail.get(row.email), method: 'correo institucional', confidence: 1 };
    }
    if (row.moodle_user_id && master.byMoodleUser.has(row.moodle_user_id)) {
      return { student: master.byMoodleUser.get(row.moodle_user_id), method: 'ID Moodle aprendido', confidence: 1 };
    }
    if (row.raw_name) {
      const scored = master.rows
        .map(student => ({ student, score: fuzzyNameScore(row.raw_name, student.full_name) }))
        .filter(item => item.score >= 0.8)
        .sort((a, b) => b.score - a.score);
      if (scored.length && (!scored[1] || scored[0].score - scored[1].score >= 0.12)) {
        return { student: scored[0].student, method: 'nombre normalizado', confidence: scored[0].score };
      }
    }
    return { student: null, method: 'sin coincidencia', confidence: 0 };
  }

  async function readJsonResponse(response) {
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data?.ok === false) throw new Error(data?.error || `Error ${response.status}`);
    return data;
  }

  async function importText(reportId, payload) {
    const report = reportById(reportId);
    if (!report?.firebase_period_id) throw new Error('El informe no tiene un período Firebase asociado.');
    if (clean(report.firebase_period_id) !== PERIOD_ID) {
      throw new Error('El catálogo de aulas Moodle cargado corresponde a Octubre 2025 - Marzo 2026. Para otro período primero debe cargarse su catálogo de aulas.');
    }

    const text = String(payload?.text || '');
    if (!clean(text)) throw new Error('Pegue el texto completo de las calificaciones de Moodle.');

    const detectedIds = parseCourseIds(text);
    const selectedId = Number(payload?.course_id || 0);
    if (detectedIds.length > 1) {
      throw new Error(`Se detectaron varias aulas Moodle (${detectedIds.join(', ')}). Pegue un aula por vez.`);
    }
    const courseId = detectedIds[0] || selectedId;
    const course = CATALOG_BY_ID.get(courseId);
    if (!course) {
      throw new Error('No pude identificar el aula Moodle. Pegue el texto con el enlace del curso o seleccione el aula en el campo de respaldo.');
    }

    const parsedRows = parseRows(text);
    if (!parsedRows.length) {
      throw new Error('No se detectaron estudiantes con correo y nota final válidos. Copie la tabla completa de calificaciones de Moodle.');
    }

    const [studentsPayload, nucleiPayload] = await Promise.all([
      readJsonResponse(await previousFetch(`/api/reports/${reportId}/students-domain`, { cache: 'no-store' })),
      readJsonResponse(await previousFetch(`/api/reports/${reportId}/nuclei`, { cache: 'no-store' })).catch(() => ({ courses: [] })),
    ]);
    const master = buildMaster(studentsPayload.students || [], nucleiPayload.courses || []);

    const results = parsedRows.map(row => {
      const match = matchStudent(row, master);
      const official = match.student || {};
      const identification = clean(official.identification || official.cedula);
      const officialName = clean(official.full_name);
      const modality = clean(official.modality) || (course.code.includes('-L-') ? 'en_linea' : 'presencial');
      const grade = Number(row.final_grade);
      return {
        cedula: identification,
        nombre: officialName || clean(row.raw_name) || row.email,
        correo: row.email,
        notaFinal: Number.isFinite(grade) ? Math.round(grade * 100) / 100 : null,
        estado: Number.isFinite(grade) ? (grade >= 7 ? 'Aprobado' : 'Reprobado') : 'No evaluado',
        modalidad: modality,
        moodleUserId: clean(row.moodle_user_id),
        matchStatus: match.student ? 'matched' : 'review',
        matchMethod: match.method,
        matchConfidence: Math.round(Number(match.confidence || 0) * 100),
        nombreFuente: clean(row.raw_name),
      };
    });

    const matched = results.filter(item => item.matchStatus === 'matched').length;
    const review = results.length - matched;
    const documentId = `${report.firebase_period_id}__moodle_${course.courseId}`;
    const existing = (nucleiPayload.courses || []).find(item => String(item.course_key || '').includes(String(course.courseId))) || {};
    const document = {
      periodoId: report.firebase_period_id,
      periodo: clean(report.period),
      courseId: course.courseId,
      courseKey: `moodle:${course.courseId}`,
      carrera: course.career,
      nombreCarrera: course.career,
      nucleo: course.nucleus,
      sede: course.campus,
      modulo: course.code,
      curso: course.subject,
      materia: course.subject,
      docente: clean(existing.teacher_name || ''),
      modalidad: course.code.includes('-L-') ? 'en_linea' : 'presencial',
      resultados: results,
      estudiantesDetectados: results.length,
      estudiantesConciliados: matched,
      estudiantesPorRevisar: review,
      fuente: 'Informtit · texto copiado de Moodle',
      sourceFormat: 'moodle-gradebook-paste',
      updatedAt: new Date().toISOString(),
      eliminado: false,
    };

    await putDocument('nucleos', documentId, document);
    window.informtitFirebaseWebCache?.clearPeriod?.(report.firebase_period_id);

    return {
      ok: true,
      course: {
        course_id: course.courseId,
        career: course.career,
        nucleus: course.nucleus,
        campus: course.campus,
        subject: course.subject,
      },
      summary: {
        detected: results.length,
        matched,
        review,
        approved: results.filter(item => item.estado === 'Aprobado').length,
        failed: results.filter(item => item.estado === 'Reprobado').length,
      },
      unmatched: results.filter(item => item.matchStatus !== 'matched').map(item => ({
        email: item.correo,
        name: item.nombreFuente || item.nombre,
        grade: item.notaFinal,
      })),
      detected_course_id: detectedIds[0] || null,
      selected_course_id: selectedId || null,
      firebase_saved: true,
    };
  }

  window.fetch = async function firebaseNucleiPasteFetch(input, init) {
    const path = pathOf(input);
    const method = methodOf(input, init);
    const match = path.match(/^\/api\/reports\/(\d+)\/nuclei\/import-text$/);
    if (match && method === 'POST') {
      try {
        const payload = await bodyOf(input, init);
        return jsonResponse(await importText(Number(match[1]), payload), 201);
      } catch (error) {
        const message = clean(error?.message) || 'No se pudo procesar el texto de Núcleos.';
        return jsonResponse({ ok: false, error: message }, /Firebase\s+40[13]/i.test(message) ? 503 : 400);
      }
    }
    return previousFetch(input, init);
  };

  window.informtitNucleiPaste = Object.freeze({
    periodId: PERIOD_ID,
    catalog: COURSE_CATALOG.map(item => ({ ...item })),
    parseCourseIds,
    parseRows,
  });
})();
