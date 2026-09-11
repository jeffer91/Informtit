(() => {
  'use strict';

  if (!/(^|\.)github\.io$/i.test(window.location.hostname)) return;

  const previousFetch = window.fetch.bind(window);
  const PDFS_KEY = 'informtit.pages.generatedPdfs.v2';
  const jobs = new Map();
  const REQUIREMENTS = [
    ['academic_status', 'Académico'],
    ['documentation_status', 'Documentación'],
    ['financial_status', 'Financiero'],
    ['titulation_status', 'Titulación'],
    ['practices_linkage_status', 'Prácticas/Vinculación'],
    ['linkage_status', 'Vinculación'],
    ['graduate_followup_status', 'Seguimiento a Graduados'],
    ['english_status', 'Inglés'],
    ['data_update_status', 'Actualización de Datos'],
  ];

  const clean = value => String(value ?? '').replace(/\u00a0/g, ' ').trim().replace(/\s+/g, ' ');
  const fold = value => clean(value).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toUpperCase();
  const pass = value => ['CUMPLE', 'SI', 'SÍ', 'APROBADO', 'OK', 'TRUE', '1'].includes(fold(value));
  const nowIso = () => new Date().toISOString();

  function pathOf(input) {
    try { return new URL(typeof input === 'string' ? input : input?.url, window.location.href).pathname; }
    catch (_) { return ''; }
  }

  function methodOf(input, init) {
    return String(init?.method || input?.method || 'GET').toUpperCase();
  }

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

  async function fetchJson(path) {
    const response = await previousFetch(path, { method: 'GET', cache: 'no-store' });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || payload?.ok === false) throw new Error(payload?.error || `Error ${response.status}`);
    return payload;
  }

  async function reportBundle(reportId) {
    const [reportData, roster, studentsDomain, nuclei, projects, schedules] = await Promise.all([
      fetchJson(`/api/reports/${reportId}`),
      fetchJson(`/api/reports/${reportId}/roster`),
      fetchJson(`/api/reports/${reportId}/students-domain`).catch(() => ({ ok: true, students: [] })),
      fetchJson(`/api/reports/${reportId}/nuclei`),
      fetchJson(`/api/reports/${reportId}/projects`),
      fetchJson(`/api/reports/${reportId}/schedules`).catch(() => ({ ok: true, schedules: { complexive: [], thesis: [] } })),
    ]);
    return {
      report: reportData.report || {},
      roster: roster || {},
      studentsDomain: studentsDomain || {},
      nuclei: nuclei || {},
      projects: projects || {},
      schedules: schedules || {},
    };
  }

  function periodIdOf(report) {
    return clean(report?.periodoId || report?.firebase_period_id || report?.period_id);
  }

  async function sourceHealth(report) {
    const periodId = periodIdOf(report);
    const sheets = window.InformtitSheets;
    if (!periodId) return { periodId, errors: [{ source: 'Período', error: 'No existe periodId.' }], statuses: [] };
    if (!sheets) return { periodId, errors: [{ source: 'Google Sheets', error: 'InformtitSheets no está disponible.' }], statuses: [] };

    const checks = [
      ['Estudiantes', () => sheets.estudiantes()],
      ['Matrículas', () => sheets.matriculas(periodId)],
      ['Requisitos', () => sheets.requisitos(periodId)],
      ['Núcleos', () => sheets.nucleos(periodId)],
      ['Examen Complexivo', () => sheets.complexivo(periodId)],
      ['Trabajo de Titulación', () => sheets.trabajoTitulacion(periodId)],
    ];

    const settled = await Promise.all(checks.map(async ([source, fn]) => {
      try {
        await fn();
        return { source, ok: true, error: '' };
      } catch (error) {
        return { source, ok: false, error: clean(error?.message || error) || 'No respondió.' };
      }
    }));

    return { periodId, statuses: settled, errors: settled.filter(item => !item.ok) };
  }

  function modalityFromLabel(label) {
    const value = fold(label);
    if (value.includes('ONLINE') || value.includes('EN LINEA')) return 'en_linea';
    if (value.includes('PRESENCIAL')) return 'presencial';
    return '';
  }

  function recalcRoster(roster, modality) {
    const clone = typeof structuredClone === 'function' ? structuredClone(roster || {}) : JSON.parse(JSON.stringify(roster || {}));
    const allStudents = Array.isArray(clone.students) ? clone.students : [];
    const students = modality ? allStudents.filter(row => clean(row.modality) === modality) : allStudents;
    const careerMap = new Map();
    students.forEach(row => {
      const name = clean(row.career_name || row.carrera || 'SIN CARRERA');
      if (!name || fold(name) === 'SIN CARRERA') return;
      const key = fold(name);
      careerMap.set(key, { name, students: (careerMap.get(key)?.students || 0) + 1 });
    });
    const requirements = REQUIREMENTS.map(([key, label]) => ({
      label,
      complies: students.filter(row => pass(row[key])).length,
      does_not_comply: students.filter(row => !pass(row[key])).length,
    }));
    const complete = students.filter(row => row.requirements_complete === true || row.requirements_complete === 1).length;
    clone.students = students;
    clone.careers = [...careerMap.values()];
    clone.requirements = requirements;
    clone.summary = {
      ...(clone.summary || {}),
      students: students.length,
      careers: careerMap.size,
      requirements_complete: complete,
      requirements_pending: students.length - complete,
      presencial: modality === 'presencial' ? students.length : students.filter(row => clean(row.modality) === 'presencial').length,
      online: modality === 'en_linea' ? students.length : students.filter(row => clean(row.modality) === 'en_linea').length,
    };
    return clone;
  }

  function filterBundle(bundle, outputLabel) {
    const modality = modalityFromLabel(outputLabel);
    if (!modality) return bundle;
    const clone = typeof structuredClone === 'function' ? structuredClone(bundle) : JSON.parse(JSON.stringify(bundle));
    clone.roster = recalcRoster(clone.roster, modality);

    if (Array.isArray(clone.studentsDomain?.students)) {
      clone.studentsDomain.students = clone.studentsDomain.students.filter(row => clean(row.modality) === modality);
      clone.studentsDomain.summary = {
        ...(clone.studentsDomain.summary || {}),
        total: clone.studentsDomain.students.length,
      };
    }

    if (Array.isArray(clone.nuclei?.courses)) {
      clone.nuclei.courses = clone.nuclei.courses.map(course => {
        const students = (course.students || []).filter(student => clean(student.modality) === modality);
        const grades = students.map(student => Number(student.final_grade ?? student.grade ?? student.nota_final)).filter(Number.isFinite);
        return {
          ...course,
          students,
          course_average: grades.length ? grades.reduce((sum, value) => sum + value, 0) / grades.length : course.course_average,
        };
      }).filter(course => course.students.length);
    }

    if (Array.isArray(clone.projects?.projects)) {
      clone.projects.projects = clone.projects.projects.filter(row => clean(row.modality) === modality);
      const grades = clone.projects.projects.map(row => Number(row.final_grade)).filter(Number.isFinite);
      clone.projects.summary = {
        ...(clone.projects.summary || {}),
        total: clone.projects.projects.length,
        approved: clone.projects.projects.filter(row => Number(row.final_grade) >= 7).length,
        failed: clone.projects.projects.filter(row => Number.isFinite(Number(row.final_grade)) && Number(row.final_grade) < 7).length,
        average_final: grades.length ? grades.reduce((sum, value) => sum + value, 0) / grades.length : null,
      };
    }

    if (Array.isArray(clone.report?.careers)) {
      clone.report.careers = clone.report.careers.map(career => ({
        ...career,
        students: (career.students || []).filter(student => clean(student.modality) === modality),
      })).filter(career => career.students.length);
      clone.report.career_count = clone.report.careers.length;
      clone.report.complexive_records = clone.report.careers.reduce((sum, career) => sum + (career.students?.length || 0), 0);
    }
    clone.report.student_count = clone.roster?.students?.length || 0;
    return clone;
  }

  function buildAudit(bundle, health, outputLabel = '') {
    const report = bundle.report || {};
    const summary = bundle.roster?.summary || {};
    const students = Array.isArray(bundle.roster?.students) ? bundle.roster.students : [];
    const courses = Array.isArray(bundle.nuclei?.courses) ? bundle.nuclei.courses : [];
    const projects = Array.isArray(bundle.projects?.projects) ? bundle.projects.projects : [];
    const controls = [];
    const push = (name, status, detail) => controls.push({ name, status, detail });
    const periodId = periodIdOf(report);

    push('Período académico', periodId ? 'ok' : 'error', periodId ? `${report.period || periodId} · ${periodId}` : 'No existe periodId asociado al documento.');
    push('Datos generales', report.name && report.period ? 'ok' : 'error', report.name && report.period ? 'Nombre y período identificados.' : 'Faltan nombre o período del documento.');

    (health.statuses || []).forEach(item => {
      push(`Fuente · ${item.source}`, item.ok ? 'ok' : 'error', item.ok ? 'Consulta respondida correctamente.' : item.error);
    });

    push('Población', students.length ? 'ok' : 'warning', students.length ? `${students.length} estudiantes${outputLabel ? ` en la salida ${outputLabel}` : ''}.` : 'No se detectó población para esta salida.');
    const pending = Number(summary.requirements_pending || 0);
    push('Requisitos', pending ? 'warning' : 'ok', pending ? `${pending} estudiantes tienen requisitos pendientes o incompletos.` : 'No se detectaron requisitos pendientes.');
    push('Núcleos', courses.length ? 'ok' : 'warning', courses.length ? `${courses.length} cursos/núcleos detectados.` : 'No existen registros de Núcleos para esta salida.');
    const complexiveRecords = Number(report.complexive_records || 0);
    push('Resultados de titulación', (complexiveRecords || projects.length) ? 'ok' : 'warning', `${complexiveRecords} registros de Complexivo · ${projects.length} registros de Trabajo de Titulación.`);

    const blocking = controls.some(item => item.status === 'error');
    const warnings = controls.some(item => item.status === 'warning');
    const expected = students.filter(row => row.route === 'COMPLEXIVO').length;
    const withNuclei = students.filter(row => row.route === 'COMPLEXIVO' && row.has_nuclei).length;
    const missing = students.filter(row => row.route === 'COMPLEXIVO' && !row.has_nuclei).slice(0, 25).map(row => ({
      full_name: row.full_name,
      career_name: row.career_name,
    }));
    const imported = courses.reduce((sum, course) => sum + (course.students?.length || 0), 0);

    return {
      document_title: report.name || 'Informe Final de Titulación',
      output_label: clean(outputLabel),
      state: blocking ? 'ERROR DE FUENTE' : !students.length ? 'SIN POBLACIÓN' : warnings ? 'REVISAR ANTES DE EMITIR' : 'APTO PARA EMITIR',
      controls,
      can_generate_pdf: !blocking,
      final_ready: !blocking && !warnings,
      mode: !students.length ? 'no_population' : 'normal',
      reconciliation_label: 'Conciliación de Núcleos',
      reconciliation: { imported, included: imported, excluded: 0, reasons: {} },
      nuclei_population: {
        expected_students: expected,
        with_nuclei: withNuclei,
        missing_students: Math.max(0, expected - withNuclei),
        coverage: expected ? (withNuclei * 100) / expected : null,
        missing,
      },
      traceability: {
        source: 'GOOGLE_SHEETS',
        period_id: periodId,
        students: students.length,
        requirements_complete: Number(summary.requirements_complete || 0),
        requirements_pending: pending,
        synced_at: bundle.roster?.synced_at || '',
        source_errors: (health.errors || []).map(item => `${item.source}: ${item.error}`),
      },
    };
  }

  function readArtifacts() {
    try {
      const rows = JSON.parse(localStorage.getItem(PDFS_KEY) || '[]');
      return Array.isArray(rows) ? rows : [];
    } catch (_) { return []; }
  }

  function writeArtifacts(rows) {
    let next = Array.isArray(rows) ? rows.slice() : [];
    next.sort((a, b) => clean(b.generated_at).localeCompare(clean(a.generated_at)));
    next = next.slice(0, 18);
    while (next.length) {
      try {
        localStorage.setItem(PDFS_KEY, JSON.stringify(next));
        return;
      } catch (error) {
        if (next.length <= 1) throw error;
        next.pop();
      }
    }
    localStorage.removeItem(PDFS_KEY);
  }

  function safeLatin1(value) {
    return clean(value)
      .replace(/[–—]/g, '-')
      .replace(/[“”]/g, '"')
      .replace(/[‘’]/g, "'")
      .replace(/→/g, '->')
      .replace(/•/g, '-')
      .replace(/[^\x20-\xFF]/g, '?');
  }

  function pdfLiteral(value) {
    return safeLatin1(value).replace(/([\\()])/g, '\\$1');
  }

  function stringBytes(value) {
    const text = String(value);
    const out = new Uint8Array(text.length);
    for (let i = 0; i < text.length; i += 1) out[i] = text.charCodeAt(i) & 0xff;
    return out;
  }

  function bytesToBase64(bytes) {
    let binary = '';
    const chunk = 0x8000;
    for (let i = 0; i < bytes.length; i += chunk) binary += String.fromCharCode(...bytes.subarray(i, Math.min(i + chunk, bytes.length)));
    return btoa(binary);
  }

  function wrapText(value, width = 92) {
    const words = safeLatin1(value).split(/\s+/).filter(Boolean);
    if (!words.length) return [''];
    const lines = [];
    let line = '';
    words.forEach(word => {
      if (!line) { line = word; return; }
      if (`${line} ${word}`.length <= width) line += ` ${word}`;
      else { lines.push(line); line = word; }
    });
    if (line) lines.push(line);
    return lines;
  }

  function line(text = '', options = {}) {
    return { text: safeLatin1(text), bold: Boolean(options.bold), size: Number(options.size || 10), gapBefore: Number(options.gapBefore || 0), gapAfter: Number(options.gapAfter || 0) };
  }

  function createPdf(lines) {
    const pageWidth = 595, pageHeight = 842, left = 48, top = 790, bottom = 50;
    const pages = [];
    let current = [], y = top;
    const pushPage = () => { if (current.length) pages.push(current); current = []; y = top; };
    (lines || []).forEach(item => {
      const source = typeof item === 'string' ? line(item) : item;
      const wrapped = wrapText(source.text, source.bold ? 82 : 96);
      const lineHeight = Math.max(12, source.size + 3);
      const required = source.gapBefore + wrapped.length * lineHeight + source.gapAfter;
      if (y - required < bottom && current.length) pushPage();
      y -= source.gapBefore;
      wrapped.forEach(text => { current.push({ ...source, text, y }); y -= lineHeight; });
      y -= source.gapAfter;
    });
    pushPage();
    if (!pages.length) pages.push([{ ...line('Informtit'), y: top }]);

    const objects = new Map(), pageIds = [];
    const catalogId = 1, pagesId = 2, regularFontId = 3, boldFontId = 4;
    let nextId = 5;
    objects.set(catalogId, `<< /Type /Catalog /Pages ${pagesId} 0 R >>`);
    objects.set(regularFontId, '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>');
    objects.set(boldFontId, '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>');
    pages.forEach(pageLines => {
      const pageId = nextId++, contentId = nextId++;
      pageIds.push(pageId);
      const commands = ['BT'];
      pageLines.forEach(item => {
        commands.push(`/${item.bold ? 'F2' : 'F1'} ${Math.max(8, Math.min(18, Number(item.size || 10)))} Tf`);
        commands.push(`1 0 0 1 ${left} ${Math.max(bottom, Number(item.y || top)).toFixed(1)} Tm`);
        commands.push(`(${pdfLiteral(item.text)}) Tj`);
      });
      commands.push('ET');
      const stream = `${commands.join('\n')}\n`;
      objects.set(contentId, `<< /Length ${stringBytes(stream).length} >>\nstream\n${stream}endstream`);
      objects.set(pageId, `<< /Type /Page /Parent ${pagesId} 0 R /MediaBox [0 0 ${pageWidth} ${pageHeight}] /Resources << /Font << /F1 ${regularFontId} 0 R /F2 ${boldFontId} 0 R >> >> /Contents ${contentId} 0 R >>`);
    });
    objects.set(pagesId, `<< /Type /Pages /Kids [${pageIds.map(id => `${id} 0 R`).join(' ')}] /Count ${pageIds.length} >>`);
    let pdf = '%PDF-1.4\n%âãÏÓ\n';
    const offsets = [0], maxId = Math.max(...objects.keys());
    for (let id = 1; id <= maxId; id += 1) {
      offsets[id] = stringBytes(pdf).length;
      pdf += `${id} 0 obj\n${objects.get(id) || '<<>>'}\nendobj\n`;
    }
    const xref = stringBytes(pdf).length;
    pdf += `xref\n0 ${maxId + 1}\n0000000000 65535 f \n`;
    for (let id = 1; id <= maxId; id += 1) pdf += `${String(offsets[id]).padStart(10, '0')} 00000 n \n`;
    pdf += `trailer\n<< /Size ${maxId + 1} /Root ${catalogId} 0 R >>\nstartxref\n${xref}\n%%EOF`;
    return stringBytes(pdf);
  }

  function grade(value) {
    const n = Number(value);
    return Number.isFinite(n) ? n.toFixed(2).replace('.', ',') : '—';
  }

  function buildPdfLines(bundle, audit, outputLabel) {
    const report = bundle.report || {};
    const summary = bundle.roster?.summary || {};
    const students = Array.isArray(bundle.roster?.students) ? bundle.roster.students : [];
    const requirements = Array.isArray(bundle.roster?.requirements) ? bundle.roster.requirements : [];
    const careers = Array.isArray(bundle.roster?.careers) ? bundle.roster.careers : [];
    const courses = Array.isArray(bundle.nuclei?.courses) ? bundle.nuclei.courses : [];
    const projects = Array.isArray(bundle.projects?.projects) ? bundle.projects.projects : [];
    const schedules = bundle.schedules?.schedules || {};
    const lines = [];
    const heading = text => lines.push(line(text, { bold: true, size: 13, gapBefore: 10, gapAfter: 4 }));
    const row = (label, value) => lines.push(line(`${label}: ${value ?? '—'}`, { size: 9 }));

    lines.push(line(report.name || 'Informe Final del Proceso de Titulación', { bold: true, size: 17, gapAfter: 8 }));
    lines.push(line(outputLabel ? `Salida: ${outputLabel}` : 'Informe consolidado', { bold: true, size: 11, gapAfter: 10 }));
    row('Período', report.period || '—');
    row('periodId', periodIdOf(report) || '—');
    row('Código', fold(outputLabel).includes('ONLINE') ? (report.code_online || report.code || '—') : (report.code || report.code_presencial || '—'));
    row('Versión', report.version || '1.0');
    row('Estado de auditoría', audit.state);

    heading('1. Resumen ejecutivo');
    row('Estudiantes', students.length);
    row('Carreras', careers.length);
    row('Requisitos completos', summary.requirements_complete || 0);
    row('Requisitos pendientes', summary.requirements_pending || 0);

    heading('2. Requisitos para titulación');
    requirements.forEach(item => lines.push(line(`${item.label}: ${Number(item.complies || 0)} cumplen · ${Number(item.does_not_comply || 0)} no cumplen`, { size: 9 })));

    heading('3. Distribución por carrera');
    careers.forEach(item => lines.push(line(`${item.name}: ${Number(item.students || 0)} estudiantes`, { size: 9 })));

    heading('4. Cronogramas');
    ['complexive', 'thesis'].forEach(type => {
      lines.push(line(type === 'complexive' ? 'Examen Complexivo' : 'Trabajo de Titulación', { bold: true, size: 10, gapBefore: 3 }));
      const entries = Array.isArray(schedules?.[type]) ? schedules[type] : [];
      if (!entries.length) lines.push(line('Sin cronograma registrado.', { size: 9 }));
      entries.forEach(entry => lines.push(line(`${entry.activity || entry.actividad || entry.name || entry.nombre || 'Actividad'} · ${entry.start_date || entry.fecha_inicio || entry.start || entry.inicio || '—'} - ${entry.end_date || entry.fecha_fin || entry.end || entry.fin || '—'}`, { size: 9 })));
    });

    heading('5. Núcleos');
    if (!courses.length) lines.push(line('No existen registros de Núcleos para esta salida.', { size: 9 }));
    courses.forEach(course => lines.push(line(`${course.career_name} · Núcleo ${course.nucleus_number} · ${course.students?.length || 0} estudiantes · promedio ${grade(course.course_average)}`, { size: 9 })));

    heading('6. Examen Complexivo');
    const complexiveCareers = Array.isArray(report.careers) ? report.careers : [];
    if (!complexiveCareers.length) lines.push(line('No existen resultados de Examen Complexivo para esta salida.', { size: 9 }));
    complexiveCareers.forEach(career => {
      lines.push(line(`${career.name}: ${career.students?.length || 0} estudiantes`, { bold: true, size: 9, gapBefore: 3 }));
      (career.students || []).forEach(student => lines.push(line(`${student.full_name || student.identification} · ${student.final_status || 'Pendiente'} · ${grade(student.final_grade)}`, { size: 8 })));
    });

    heading('7. Trabajo de Titulación');
    if (!projects.length) lines.push(line('No existen registros de Trabajo de Titulación para esta salida.', { size: 9 }));
    projects.forEach(project => lines.push(line(`${project.full_name || project.identification} · ${project.career_name || 'Sin carrera'} · ${project.final_status || 'Pendiente'} · ${grade(project.final_grade)}`, { size: 8 })));

    heading('8. Diagnóstico y trazabilidad');
    (audit.controls || []).forEach(control => lines.push(line(`${control.status === 'ok' ? 'OK' : control.status === 'error' ? 'ERROR' : 'REVISAR'} · ${control.name}: ${control.detail}`, { size: 9 })));
    row('Fuente de datos', 'GOOGLE_SHEETS');
    row('Sincronizado', audit.traceability?.synced_at || '—');

    heading('9. Conclusiones');
    lines.push(line(`Se consolidaron ${students.length} estudiantes y ${careers.length} carreras para la salida seleccionada. El estado de validación fue «${audit.state}».`));
    return lines;
  }

  async function generateArtifact(reportId, outputLabel) {
    const rawBundle = await reportBundle(reportId);
    const health = await sourceHealth(rawBundle.report);
    if (health.errors.length) {
      throw new Error(`No se puede generar el PDF porque fallaron fuentes institucionales: ${health.errors.map(item => item.source).join(', ')}.`);
    }
    const bundle = filterBundle(rawBundle, outputLabel);
    const audit = buildAudit(bundle, health, outputLabel);
    if (!audit.can_generate_pdf) throw new Error('La auditoría detectó errores bloqueantes.');
    const bytes = createPdf(buildPdfLines(bundle, audit, outputLabel));
    const generatedAt = nowIso();
    const cleanLabel = clean(outputLabel) || (bundle.report.report_type === 'pvc' ? 'PVC' : 'Consolidado');
    const artifactId = `pdf-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    const periodSafe = clean(bundle.report.period || 'periodo').replace(/[^A-Za-z0-9ÁÉÍÓÚÜÑáéíóúüñ_-]+/g, '_');
    const labelSafe = cleanLabel.replace(/[^A-Za-z0-9ÁÉÍÓÚÜÑáéíóúüñ_-]+/g, '_');
    const rows = readArtifacts().map(item => Number(item.report_id) === Number(reportId) && item.modality_label === cleanLabel && item.status === 'vigente' ? { ...item, status: 'historico' } : item);
    const artifact = {
      artifact_id: artifactId,
      report_id: Number(reportId),
      modality_label: cleanLabel,
      generated_at: generatedAt,
      status: 'vigente',
      version: clean(bundle.report.version) || '1.0',
      filename: `Informtit_${periodSafe}_${labelSafe}_${generatedAt.slice(0, 10)}.pdf`,
      size: bytes.length,
      source: 'BROWSER_PDF_STABLE',
      period_id: periodIdOf(bundle.report),
      audit_state: audit.state,
      output_students: bundle.roster?.students?.length || 0,
      output_requirements_complete: bundle.roster?.summary?.requirements_complete || 0,
      pdf_base64: bytesToBase64(bytes),
    };
    rows.unshift(artifact);
    writeArtifacts(rows);
    return { artifact, audit };
  }

  function stabilizeUi() {
    if (!document?.querySelectorAll) return;
    document.querySelectorAll('[data-view="ai"],[data-view="coordinators"]').forEach(node => node.remove());
    document.querySelectorAll('#add-career-btn,[data-notes],[data-analysis],[data-delete-career],#career-dialog,#notes-dialog,#analysis-dialog,#students-sync-btn,[data-reset-schedule],[data-parse-schedule],[data-schedule-upload],#project-import-form,#thesis-analysis-form,[data-save-thesis-preview],[data-delete-project]').forEach(node => {
      if (node.tagName === 'DIALOG') node.remove();
      else node.style.display = 'none';
    });
    document.querySelectorAll('.student-route-select').forEach(select => {
      select.disabled = true;
      select.title = 'La ruta se determina desde la información institucional compartida.';
    });
    document.querySelectorAll('#tab-students p').forEach(node => {
      if (/ocho requisitos habilitantes/i.test(node.textContent || '')) node.textContent = node.textContent.replace(/ocho requisitos habilitantes/ig, 'nueve requisitos habilitantes');
    });
    const projects = document.querySelector('#tab-projects');
    if (projects && projects.children.length && !projects.querySelector('#pages-projects-readonly-note')) {
      const note = document.createElement('div');
      note.id = 'pages-projects-readonly-note';
      note.className = 'empty-mini';
      note.textContent = 'Trabajo de Titulación se muestra desde Google Sheets. Para cargar o actualizar resultados use la pestaña Importaciones.';
      projects.prepend(note);
    }
  }

  window.fetch = async function pagesStabilityFetch(input, init = {}) {
    const path = pathOf(input);
    const method = methodOf(input, init);

    let match = path.match(/^\/api\/reports\/(\d+)\/audit$/);
    if (match && method === 'GET') {
      try {
        const bundle = await reportBundle(Number(match[1]));
        const health = await sourceHealth(bundle.report);
        const audit = buildAudit(bundle, health, '');
        return jsonResponse({ ok: true, audit, preflight_token: `stable-${Date.now()}` });
      } catch (error) {
        return jsonResponse({ ok: false, error: clean(error?.message || error) }, 500);
      }
    }

    match = path.match(/^\/api\/reports\/(\d+)\/pdf-jobs$/);
    if (match && method === 'POST') {
      try {
        const body = await bodyOf(input, init);
        const { artifact } = await generateArtifact(Number(match[1]), body.output_label || 'PDF');
        const job = {
          id: `stable-job-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
          report_id: Number(match[1]),
          status: 'completed',
          progress: 100,
          stage: 'PDF validado y generado',
          detail: 'Cifras recalculadas para la salida seleccionada y fuentes verificadas.',
          duration_seconds: 0,
          artifact_id: artifact.artifact_id,
          steps: [
            { stage: 'Fuentes institucionales verificadas', progress: 25 },
            { stage: 'Indicadores recalculados por modalidad', progress: 65 },
            { stage: 'PDF generado', progress: 100 },
          ],
        };
        jobs.set(job.id, job);
        return jsonResponse({ ok: true, job }, 201);
      } catch (error) {
        return jsonResponse({ ok: false, error: clean(error?.message || error) }, 409);
      }
    }

    match = path.match(/^\/api\/pdf-jobs\/([^/]+)$/);
    if (match && method === 'GET' && jobs.has(match[1])) return jsonResponse({ ok: true, job: jobs.get(match[1]) });

    return previousFetch(input, init);
  };

  window.InformtitPagesStability = Object.freeze({ sourceHealth, filterBundle, buildAudit, version: '1.0.0' });

  if (document?.addEventListener) document.addEventListener('DOMContentLoaded', () => setTimeout(stabilizeUi, 0), { once: true });
  if (typeof MutationObserver !== 'undefined' && document?.body) {
    const observer = new MutationObserver(() => stabilizeUi());
    observer.observe(document.body, { childList: true, subtree: true });
  }
  setTimeout(stabilizeUi, 0);
})();
