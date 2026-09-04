(() => {
  'use strict';

  if (!/(^|\.)github\.io$/i.test(window.location.hostname)) return;

  const PROJECT_ID = 'utet-4387a';
  const API_KEY = 'AIzaSyCaHf1C0BB0X_H3BDZ1o-UDAsPmLTjsZLA';
  const FIRESTORE_ROOT = `https://firestore.googleapis.com/v1/projects/${PROJECT_ID}/databases/(default)`;
  const previousFetch = window.fetch.bind(window);

  function clean(value) {
    return String(value ?? '').replace(/\\@/g, '@').replace(/\u00a0/g, ' ').trim().replace(/\s+/g, ' ');
  }

  function fold(value) {
    return clean(value).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toUpperCase();
  }

  function slug(value) {
    return fold(value).toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 80);
  }

  function stableHash(value) {
    let hash = 2166136261;
    const text = String(value || '');
    for (let index = 0; index < text.length; index += 1) {
      hash ^= text.charCodeAt(index);
      hash = Math.imul(hash, 16777619);
    }
    return (hash >>> 0).toString(16).padStart(8, '0');
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
    if (typeof init?.body === 'string') {
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

  async function readJson(response) {
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data?.ok === false) throw new Error(data?.error || `Error ${response.status}`);
    return data;
  }

  function catalog() {
    return Array.isArray(window.informtitNucleiPaste?.catalog) ? window.informtitNucleiPaste.catalog : [];
  }

  function detectKnownCourseIds(text) {
    const detector = window.informtitNucleiCourseDetectionFix?.detectCourseIds;
    if (typeof detector === 'function') return detector(text);
    const fallback = window.informtitNucleiPaste?.parseCourseIds;
    return typeof fallback === 'function' ? fallback(text) : [];
  }

  function detectNucleus(text) {
    const match = fold(text).match(/N[UÚ]CLEO\s*(?:N(?:RO|UMERO)?\.?\s*)?([1-4])/i)
      || fold(text).match(/NUCLEO[^0-9]{0,12}([1-4])/i);
    return match ? Number(match[1]) : 0;
  }

  function detectCampus(text) {
    const header = fold(String(text || '').split(/\r?\n/).slice(0, 12).join(' '));
    if (/\bMANTA\b/.test(header)) return 'Manta';
    if (/\bMATRIZ\b/.test(header)) return 'Matriz';
    if (/\bSUR\b/.test(header)) return 'Sur';
    return '';
  }

  function careerCore(value) {
    return fold(value)
      .replace(/\b(TECNOLOGIA|TECNICO|SUPERIOR|UNIVERSITARIA|EN|ONLINE|PRESENCIAL|TSU)\b/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  }

  function careerOf(student) {
    return clean(student?.career_name || student?.career || student?.program || student?.carrera || student?.nombre_carrera || student?.nombreCarrera);
  }

  function campusOf(student) {
    return clean(student?.campus || student?.sede || student?.branch || student?.sucursal);
  }

  function modalityOf(student) {
    return clean(student?.modality || student?.modalidad || student?.study_modality);
  }

  function fullNameOf(student) {
    return clean(student?.full_name || student?.name || student?.nombre || student?.nombre_estudiante);
  }

  function identificationOf(student) {
    return clean(student?.identification || student?.cedula || student?.document || student?.numero_identificacion);
  }

  function emailOf(student) {
    return clean(student?.email || student?.correo || student?.personal_email).toLowerCase();
  }

  function headerCourseCandidate(text, nucleus, campus) {
    const firstLines = String(text || '').split(/\r?\n/).slice(0, 12).join(' ');
    const header = fold(firstLines);
    const candidates = catalog().filter(item => !nucleus || Number(item.nucleus) === Number(nucleus));
    const scored = candidates.map(item => {
      const subject = fold(item.subject);
      const career = careerCore(item.career);
      let score = 0;
      if (subject && header.includes(subject)) score += 100;
      const subjectTokens = subject.split(/\s+/).filter(token => token.length >= 4 && !['NUCLEO', 'SUPERIOR'].includes(token));
      score += subjectTokens.filter(token => header.includes(token)).length * 5;
      const careerTokens = career.split(/\s+/).filter(token => token.length >= 4);
      score += careerTokens.filter(token => header.includes(token)).length * 7;
      if (campus && fold(item.campus) === fold(campus)) score += 20;
      return { item, score };
    }).filter(entry => entry.score > 0).sort((a, b) => b.score - a.score);
    if (!scored.length) return null;
    if (scored[0].score >= 20 && (!scored[1] || scored[0].score - scored[1].score >= 8)) return scored[0].item;
    return null;
  }

  function fallbackParseRows(text) {
    const rows = [];
    String(text || '').split(/\r?\n/).forEach(line => {
      const normalized = line.replace(/\\@/g, '@');
      const emailMatch = normalized.match(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i);
      if (!emailMatch) return;
      const email = emailMatch[0].toLowerCase();
      const tail = normalized.slice(normalized.toLowerCase().indexOf(email) + email.length)
        .replace(/https?:\/\/\S+/gi, ' ')
        .replace(/\([^)]*\)/g, ' ');
      const grades = [...tail.matchAll(/(?<!\d)(10(?:[.,]00)?|[0-9](?:[.,]\d{1,2})?)(?!\d)/g)]
        .map(match => Number(match[1].replace(',', '.')))
        .filter(value => Number.isFinite(value) && value >= 0 && value <= 10);
      if (!grades.length) return;
      const linkName = normalized.match(/\[\*\*([^*]+)\*\*\]\(/) || normalized.match(/\*\*([^*]+)\*\*/);
      rows.push({ raw_name: clean(linkName?.[1] || ''), email, moodle_user_id: '', final_grade: grades[grades.length - 1] });
    });
    return rows;
  }

  function parseRows(text) {
    const parser = window.informtitNucleiPaste?.parseRows;
    const rows = typeof parser === 'function' ? parser(text) : fallbackParseRows(text);
    return Array.isArray(rows) ? rows : [];
  }

  function nameTokens(value) {
    return fold(value).replace(/[^A-Z0-9 ]+/g, ' ').split(/\s+/).filter(token => token.length >= 2);
  }

  function nameScore(source, target) {
    const left = nameTokens(source);
    const right = nameTokens(target);
    if (!left.length || !right.length) return 0;
    const hits = right.filter(token => left.some(candidate => candidate === token || candidate.endsWith(token) || token.endsWith(candidate))).length;
    return hits / right.length;
  }

  function buildMaster(students) {
    const rows = Array.isArray(students) ? students : [];
    const byEmail = new Map();
    rows.forEach(student => {
      const email = emailOf(student);
      if (email) byEmail.set(email, student);
    });
    return { rows, byEmail };
  }

  function matchStudent(row, master) {
    if (row.email && master.byEmail.has(row.email.toLowerCase())) {
      return { student: master.byEmail.get(row.email.toLowerCase()), method: 'correo institucional', confidence: 100 };
    }
    const rawName = clean(row.raw_name);
    if (rawName) {
      const scored = master.rows.map(student => ({ student, score: nameScore(rawName, fullNameOf(student)) }))
        .filter(item => item.score >= 0.82)
        .sort((a, b) => b.score - a.score);
      if (scored.length && (!scored[1] || scored[0].score - scored[1].score >= 0.15)) {
        return { student: scored[0].student, method: 'nombre normalizado', confidence: Math.round(scored[0].score * 100) };
      }
    }
    return { student: null, method: 'sin coincidencia', confidence: 0 };
  }

  function dominantValue(values) {
    const counts = new Map();
    values.map(clean).filter(Boolean).forEach(value => counts.set(value, (counts.get(value) || 0) + 1));
    const ordered = [...counts.entries()].sort((a, b) => b[1] - a[1]);
    if (!ordered.length) return { value: '', count: 0, ambiguous: true };
    const [value, count] = ordered[0];
    const second = ordered[1]?.[1] || 0;
    return { value, count, ambiguous: second === count };
  }

  function catalogForCareer(career, nucleus, campus) {
    const core = careerCore(career);
    let candidates = catalog().filter(item => Number(item.nucleus) === Number(nucleus));
    candidates = candidates.filter(item => {
      const itemCore = careerCore(item.career);
      return itemCore === core || itemCore.includes(core) || core.includes(itemCore);
    });
    if (campus) {
      const campusMatches = candidates.filter(item => fold(item.campus) === fold(campus));
      if (campusMatches.length) candidates = campusMatches;
    }
    return candidates.length === 1 ? candidates[0] : null;
  }

  async function importText(reportId, payload) {
    const text = String(payload?.text || '');
    if (!clean(text)) throw new Error('Pegue el texto completo de las calificaciones de Moodle.');

    const parsed = parseRows(text);
    if (!parsed.length) throw new Error('No se detectaron estudiantes con correo y nota final. Copie la tabla completa de Moodle.');

    const reportResponse = await readJson(await previousFetch(`/api/reports/${reportId}`, { cache: 'no-store' }));
    const report = reportResponse.report || reportResponse;
    const periodId = clean(report?.firebase_period_id || report?.periodId || report?.period_id);
    if (!periodId) throw new Error('El informe no tiene un período Firebase asociado.');

    const studentsPayload = await readJson(await previousFetch(`/api/reports/${reportId}/students-domain`, { cache: 'no-store' }));
    const master = buildMaster(studentsPayload.students || []);
    const matchedRows = parsed.map(row => ({ row, match: matchStudent(row, master) }));
    const matchedStudents = matchedRows.map(item => item.match.student).filter(Boolean);

    const knownCourseIds = detectKnownCourseIds(text);
    const exactCourse = knownCourseIds.length === 1
      ? catalog().find(item => Number(item.courseId) === Number(knownCourseIds[0])) || null
      : null;

    const autoNucleus = Number(exactCourse?.nucleus || detectNucleus(text) || 0);
    const manualNucleus = Number(payload?.nucleus_number || 0);
    const nucleus = autoNucleus || manualNucleus;
    if (![1, 2, 3, 4].includes(nucleus)) {
      throw new Error('No pude determinar qué Núcleo es. Seleccione Núcleo 1, 2, 3 o 4 y vuelva a procesar.');
    }

    const headerCampus = clean(exactCourse?.campus || detectCampus(text));
    const headerCourse = exactCourse || headerCourseCandidate(text, nucleus, headerCampus);
    const careerMajority = dominantValue(matchedStudents.map(careerOf));
    const campusMajority = dominantValue(matchedStudents.map(campusOf));

    let career = clean(headerCourse?.career || careerMajority.value);
    let campus = clean(headerCampus || (!campusMajority.ambiguous ? campusMajority.value : ''));
    if (!career) {
      throw new Error('No pude determinar la carrera de estos estudiantes. Revise que los correos pertenezcan al período correcto.');
    }
    if (!campus) campus = 'Global';

    const course = headerCourse || catalogForCareer(career, nucleus, campus);
    if (course?.career) career = course.career;
    if (course?.campus && campus === 'Global') campus = course.campus;

    const results = matchedRows.map(({ row, match }) => {
      const official = match.student || {};
      const grade = Number(row.final_grade);
      const modality = modalityOf(official) || (course?.code?.includes('-L-') ? 'en_linea' : 'presencial');
      return {
        cedula: identificationOf(official),
        nombre: fullNameOf(official) || clean(row.raw_name) || clean(row.email),
        correo: clean(row.email).toLowerCase(),
        notaFinal: Number.isFinite(grade) ? Math.round(grade * 100) / 100 : null,
        estado: Number.isFinite(grade) ? (grade >= 7 ? 'Aprobado' : 'Reprobado') : 'No evaluado',
        modalidad: modality,
        moodleUserId: clean(row.moodle_user_id),
        matchStatus: match.student ? 'matched' : 'review',
        matchMethod: match.method,
        matchConfidence: match.confidence,
        nombreFuente: clean(row.raw_name),
      };
    });

    const matched = results.filter(item => item.matchStatus === 'matched').length;
    const review = results.length - matched;
    const modalities = [...new Set(results.map(item => clean(item.modalidad)).filter(Boolean))];
    const emailFingerprint = results.map(item => item.correo).filter(Boolean).sort().join('|');
    const documentId = course?.courseId
      ? `${periodId}__moodle_${Number(course.courseId)}`
      : `${periodId}__nucleo_${nucleus}_${slug(career)}_${slug(campus)}_${stableHash(emailFingerprint)}`;

    const assignmentSource = exactCourse
      ? 'aula Moodle'
      : headerCourse
        ? 'encabezado del texto'
        : autoNucleus
          ? 'encabezado + población oficial'
          : 'núcleo seleccionado + población oficial';

    const document = {
      periodoId: periodId,
      periodo: clean(report?.period),
      courseId: Number(course?.courseId || 0),
      courseKey: course?.courseId ? `moodle:${Number(course.courseId)}` : `nucleo:${nucleus}:${slug(career)}:${slug(campus)}:${stableHash(emailFingerprint)}`,
      carrera: career,
      nombreCarrera: career,
      nucleo: nucleus,
      sede: campus,
      modulo: clean(course?.code || ''),
      curso: clean(course?.subject || `Núcleo ${nucleus}`),
      materia: clean(course?.subject || `Núcleo ${nucleus}`),
      modalidad: modalities.length === 1 ? modalities[0] : 'mixto',
      resultados: results,
      estudiantesDetectados: results.length,
      estudiantesConciliados: matched,
      estudiantesPorRevisar: review,
      fuente: 'Informtit · texto copiado de Moodle',
      sourceFormat: 'moodle-gradebook-paste-v2',
      assignmentSource,
      updatedAt: new Date().toISOString(),
      eliminado: false,
    };

    await putDocument('nucleos', documentId, document);
    window.informtitFirebaseWebCache?.clearPeriod?.(periodId);

    return {
      ok: true,
      assignment: {
        nucleus,
        career,
        campus,
        course_id: Number(course?.courseId || 0),
        source: assignmentSource,
        auto_nucleus: Boolean(autoNucleus),
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
      firebase_saved: true,
    };
  }

  window.fetch = async function definitiveNucleiPasteFetch(input, init = {}) {
    const path = pathOf(input);
    const method = methodOf(input, init);
    const match = path.match(/^\/api\/reports\/(\d+)\/nuclei\/import-text-v2$/);
    if (!match || method !== 'POST') return previousFetch(input, init);
    try {
      const payload = await bodyOf(input, init);
      return jsonResponse(await importText(Number(match[1]), payload), 201);
    } catch (error) {
      const message = clean(error?.message) || 'No se pudo procesar el texto de Núcleos.';
      return jsonResponse({ ok: false, error: message }, /Firebase\s+40[13]/i.test(message) ? 503 : 400);
    }
  };

  window.informtitDefinitiveNucleiPaste = Object.freeze({ detectNucleus, detectCampus, careerCore });
})();
