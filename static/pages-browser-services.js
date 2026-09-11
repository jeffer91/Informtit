(() => {
  'use strict';

  if (!/(^|\.)github\.io$/i.test(window.location.hostname)) return;

  const REPORTS_KEY = 'informtit.githubPages.reports.v1';
  const PDFS_KEY = 'informtit.pages.generatedPdfs.v2';
  const previousFetch = window.fetch.bind(window);
  const jobs = new Map();
  let lastPdfOutputLabel = '';

  document.addEventListener('click', event => {
    const button = event.target instanceof Element ? event.target.closest('[data-generate-label]') : null;
    if (button?.dataset?.generateLabel) lastPdfOutputLabel = clean(button.dataset.generateLabel);
  }, true);

  const clean = value => String(value ?? '').replace(/\u00a0/g, ' ').trim().replace(/\s+/g, ' ');
  const digits = value => clean(value).replace(/\D/g, '');
  const nowIso = () => new Date().toISOString();

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
    if (init?.body !== undefined && init?.body !== null) {
      if (typeof init.body === 'string') {
        try { return JSON.parse(init.body); } catch (_) { return {}; }
      }
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

  function binaryResponse(bytes, filename = 'Informe_Titulacion.pdf') {
    return Promise.resolve(new Response(bytes, {
      status: 200,
      headers: {
        'Content-Type': 'application/pdf',
        'Content-Disposition': `attachment; filename="${String(filename).replace(/["\\]/g, '_')}"`,
        'Cache-Control': 'no-store',
      },
    }));
  }

  async function previousJson(path, fallback = null) {
    try {
      const response = await previousFetch(path, { method: 'GET', cache: 'no-store' });
      if (!response.ok) return fallback;
      const type = response.headers.get('content-type') || '';
      if (!type.includes('application/json')) return fallback;
      return await response.json();
    } catch (_) { return fallback; }
  }

  function readReports() {
    try {
      const rows = JSON.parse(localStorage.getItem(REPORTS_KEY) || '[]');
      return Array.isArray(rows) ? rows : [];
    } catch (_) { return []; }
  }

  function writeReports(rows) {
    localStorage.setItem(REPORTS_KEY, JSON.stringify(rows));
  }

  function findReportIndex(rows, reportId) {
    return rows.findIndex(report => Number(report.id) === Number(reportId)
      || (report.legacy_report_ids || []).some(id => Number(id) === Number(reportId)));
  }

  function readArtifacts() {
    try {
      const rows = JSON.parse(localStorage.getItem(PDFS_KEY) || '[]');
      return Array.isArray(rows) ? rows : [];
    } catch (_) { return []; }
  }

  function artifactMeta(item) {
    const { pdf_base64, ...meta } = item;
    return meta;
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

  function bytesToBase64(bytes) {
    let binary = '';
    const chunk = 0x8000;
    for (let i = 0; i < bytes.length; i += chunk) {
      binary += String.fromCharCode(...bytes.subarray(i, Math.min(i + chunk, bytes.length)));
    }
    return btoa(binary);
  }

  function base64ToBytes(value) {
    const binary = atob(String(value || ''));
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
    return bytes;
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

  function makePdfLine(text = '', options = {}) {
    return {
      text: safeLatin1(text),
      bold: Boolean(options.bold),
      size: Number(options.size || 10),
      gapBefore: Number(options.gapBefore || 0),
      gapAfter: Number(options.gapAfter || 0),
    };
  }

  function createPdf(lines) {
    const pageWidth = 595;
    const pageHeight = 842;
    const left = 48;
    const top = 790;
    const bottom = 50;
    const pages = [];
    let current = [];
    let y = top;

    function pushPage() {
      if (current.length) pages.push(current);
      current = [];
      y = top;
    }

    (lines || []).forEach(item => {
      const source = typeof item === 'string' ? makePdfLine(item) : item;
      const wrapped = wrapText(source.text, source.bold ? 82 : 96);
      const lineHeight = Math.max(12, source.size + 3);
      const required = source.gapBefore + (wrapped.length * lineHeight) + source.gapAfter;
      if (y - required < bottom && current.length) pushPage();
      y -= source.gapBefore;
      wrapped.forEach(text => {
        current.push({ ...source, text, y });
        y -= lineHeight;
      });
      y -= source.gapAfter;
    });
    pushPage();
    if (!pages.length) pages.push([{ ...makePdfLine('Informtit'), y: top }]);

    const objects = new Map();
    const pageIds = [];
    const catalogId = 1;
    const pagesId = 2;
    const regularFontId = 3;
    const boldFontId = 4;
    let nextId = 5;

    objects.set(catalogId, `<< /Type /Catalog /Pages ${pagesId} 0 R >>`);
    objects.set(regularFontId, '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>');
    objects.set(boldFontId, '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>');

    pages.forEach(pageLines => {
      const pageId = nextId++;
      const contentId = nextId++;
      pageIds.push(pageId);
      const commands = ['BT'];
      pageLines.forEach(line => {
        const font = line.bold ? 'F2' : 'F1';
        commands.push(`/${font} ${Math.max(8, Math.min(18, Number(line.size || 10)))} Tf`);
        commands.push(`1 0 0 1 ${left} ${Math.max(bottom, Number(line.y || top)).toFixed(1)} Tm`);
        commands.push(`(${pdfLiteral(line.text)}) Tj`);
      });
      commands.push('ET');
      const stream = `${commands.join('\n')}\n`;
      objects.set(contentId, `<< /Length ${stringBytes(stream).length} >>\nstream\n${stream}endstream`);
      objects.set(pageId, `<< /Type /Page /Parent ${pagesId} 0 R /MediaBox [0 0 ${pageWidth} ${pageHeight}] /Resources << /Font << /F1 ${regularFontId} 0 R /F2 ${boldFontId} 0 R >> >> /Contents ${contentId} 0 R >>`);
    });

    objects.set(pagesId, `<< /Type /Pages /Kids [${pageIds.map(id => `${id} 0 R`).join(' ')}] /Count ${pageIds.length} >>`);

    let pdf = '%PDF-1.4\n%âãÏÓ\n';
    const offsets = [0];
    const maxId = Math.max(...objects.keys());
    for (let id = 1; id <= maxId; id += 1) {
      offsets[id] = stringBytes(pdf).length;
      pdf += `${id} 0 obj\n${objects.get(id) || '<<>>'}\nendobj\n`;
    }
    const xref = stringBytes(pdf).length;
    pdf += `xref\n0 ${maxId + 1}\n`;
    pdf += '0000000000 65535 f \n';
    for (let id = 1; id <= maxId; id += 1) {
      pdf += `${String(offsets[id]).padStart(10, '0')} 00000 n \n`;
    }
    pdf += `trailer\n<< /Size ${maxId + 1} /Root ${catalogId} 0 R >>\nstartxref\n${xref}\n%%EOF`;
    return stringBytes(pdf);
  }

  function grade(value) {
    const number = Number(value);
    return Number.isFinite(number) ? number.toFixed(2).replace('.', ',') : '—';
  }

  function addHeading(lines, text) {
    lines.push(makePdfLine(text, { bold: true, size: 13, gapBefore: 10, gapAfter: 4 }));
  }

  function addRow(lines, label, value) {
    lines.push(makePdfLine(`${label}: ${value ?? '—'}`, { size: 9 }));
  }

  async function reportBundle(reportId) {
    const [reportData, roster, studentsDomain, nuclei, projects, schedules] = await Promise.all([
      previousJson(`/api/reports/${reportId}`, {}),
      previousJson(`/api/reports/${reportId}/roster`, {}),
      previousJson(`/api/reports/${reportId}/students-domain`, {}),
      previousJson(`/api/reports/${reportId}/nuclei`, {}),
      previousJson(`/api/reports/${reportId}/projects`, {}),
      previousJson(`/api/reports/${reportId}/schedules`, {}),
    ]);
    return {
      report: reportData?.report || {},
      roster: roster || {},
      studentsDomain: studentsDomain || {},
      nuclei: nuclei || {},
      projects: projects || {},
      schedules: schedules || {},
    };
  }

  function filterByOutput(bundle, outputLabel) {
    const label = clean(outputLabel).toLowerCase();
    const modality = label.includes('online') ? 'en_linea' : label.includes('presencial') ? 'presencial' : '';
    if (!modality) return bundle;
    const clone = typeof structuredClone === 'function' ? structuredClone(bundle) : JSON.parse(JSON.stringify(bundle));
    if (Array.isArray(clone.roster.students)) clone.roster.students = clone.roster.students.filter(row => row.modality === modality);
    if (clone.roster.summary) {
      clone.roster.summary.students = clone.roster.students?.length || 0;
      clone.roster.summary.presencial = modality === 'presencial' ? clone.roster.summary.students : 0;
      clone.roster.summary.online = modality === 'en_linea' ? clone.roster.summary.students : 0;
    }
    if (Array.isArray(clone.studentsDomain.students)) clone.studentsDomain.students = clone.studentsDomain.students.filter(row => row.modality === modality);
    if (Array.isArray(clone.nuclei.courses)) {
      clone.nuclei.courses = clone.nuclei.courses.map(course => ({
        ...course,
        students: (course.students || []).filter(student => student.modality === modality),
      })).filter(course => course.students.length);
    }
    if (Array.isArray(clone.projects.projects)) clone.projects.projects = clone.projects.projects.filter(row => row.modality === modality);
    return clone;
  }

  async function buildAudit(reportId) {
    const bundle = await reportBundle(reportId);
    const report = bundle.report || {};
    const summary = bundle.roster?.summary || {};
    const students = Array.isArray(bundle.roster?.students) ? bundle.roster.students : [];
    const courses = Array.isArray(bundle.nuclei?.courses) ? bundle.nuclei.courses : [];
    const projects = Array.isArray(bundle.projects?.projects) ? bundle.projects.projects : [];
    const controls = [];
    const push = (name, status, detail) => controls.push({ name, status, detail });

    const periodId = clean(report.periodoId || report.firebase_period_id || report.period_id);
    push('Período académico', periodId ? 'ok' : 'error', periodId ? `${report.period || periodId} · ${periodId}` : 'No existe un periodId asociado al documento.');
    push('Datos generales', report.name && report.period ? 'ok' : 'error', report.name && report.period ? 'Nombre y período identificados.' : 'Faltan nombre o período del documento.');
    push('Población', students.length ? 'ok' : 'warning', students.length ? `${students.length} estudiantes consolidados desde Google Sheets.` : 'No se detectó población para el documento.');

    const pending = Number(summary.requirements_pending || 0);
    push('Requisitos', pending ? 'warning' : 'ok', pending ? `${pending} estudiantes tienen requisitos pendientes o incompletos.` : 'No se detectaron requisitos pendientes en la población consolidada.');
    push('Núcleos', courses.length ? 'ok' : 'warning', courses.length ? `${courses.length} cursos/núcleos detectados.` : 'No existen registros de Núcleos para este período.');

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

    const state = blocking ? 'ERROR DE CARGA' : !students.length ? 'SIN POBLACIÓN' : warnings ? 'REVISAR ANTES DE EMITIR' : 'APTO PARA EMITIR';
    return {
      document_title: report.name || 'Informe Final de Titulación',
      state,
      controls,
      can_generate_pdf: !blocking,
      final_ready: !blocking && !warnings,
      mode: !students.length ? 'no_population' : 'normal',
      reconciliation_label: 'Conciliación de Núcleos',
      reconciliation: {
        imported,
        included: imported,
        excluded: 0,
        reasons: {},
      },
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
      },
    };
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

    lines.push(makePdfLine(report.name || 'Informe Final del Proceso de Titulación', { bold: true, size: 17, gapAfter: 8 }));
    lines.push(makePdfLine(outputLabel ? `Salida: ${outputLabel}` : 'Informe consolidado', { bold: true, size: 11, gapAfter: 10 }));
    addRow(lines, 'Período', report.period || '—');
    addRow(lines, 'periodId', report.periodoId || report.firebase_period_id || '—');
    addRow(lines, 'Código', report.code || report.code_presencial || '—');
    if (clean(outputLabel).toLowerCase().includes('online') && report.code_online) addRow(lines, 'Código Online', report.code_online);
    addRow(lines, 'Versión', report.version || '1.0');
    addRow(lines, 'Fecha de elaboración', report.elaboration_date || new Date().toLocaleDateString('es-EC'));
    addRow(lines, 'Estado de auditoría', audit.state);

    addHeading(lines, '1. Resumen ejecutivo');
    lines.push(makePdfLine(`El informe consolida la información institucional disponible para el período ${report.period || 'seleccionado'}. La fuente académica principal es Google Sheets mediante Google Apps Script.`));
    addRow(lines, 'Estudiantes', students.length);
    addRow(lines, 'Carreras', careers.length);
    addRow(lines, 'Requisitos completos', summary.requirements_complete || 0);
    addRow(lines, 'Requisitos pendientes', summary.requirements_pending || 0);

    addHeading(lines, '2. Requisitos para titulación');
    if (requirements.length) requirements.forEach(item => {
      lines.push(makePdfLine(`${item.label}: ${Number(item.complies || 0)} cumplen · ${Number(item.does_not_comply || 0)} no cumplen`, { size: 9 }));
    });
    else lines.push(makePdfLine('No existen datos de requisitos para esta salida.', { size: 9 }));

    addHeading(lines, '3. Distribución por carrera');
    if (careers.length) careers.forEach(item => lines.push(makePdfLine(`${item.name}: ${Number(item.students || 0)} estudiantes`, { size: 9 })));
    else lines.push(makePdfLine('Sin carreras registradas para esta salida.', { size: 9 }));

    addHeading(lines, '4. Cronogramas');
    ['complexive', 'thesis'].forEach(type => {
      const title = type === 'complexive' ? 'Examen Complexivo' : 'Trabajo de Titulación';
      lines.push(makePdfLine(title, { bold: true, size: 10, gapBefore: 3 }));
      const entries = Array.isArray(schedules?.[type]) ? schedules[type] : [];
      if (!entries.length) lines.push(makePdfLine('Sin cronograma registrado.', { size: 9 }));
      entries.forEach(entry => {
        const activity = entry.activity || entry.actividad || entry.name || entry.nombre || 'Actividad';
        const start = entry.start_date || entry.fecha_inicio || entry.start || entry.inicio || '';
        const end = entry.end_date || entry.fecha_fin || entry.end || entry.fin || '';
        lines.push(makePdfLine(`${activity} · ${start || '—'} - ${end || '—'}`, { size: 9 }));
      });
    });

    addHeading(lines, '5. Núcleos');
    if (!courses.length) lines.push(makePdfLine('No existen registros de Núcleos para esta salida.', { size: 9 }));
    courses.forEach(course => {
      lines.push(makePdfLine(`${course.career_name} · Núcleo ${course.nucleus_number} · ${course.students?.length || 0} estudiantes · promedio ${grade(course.course_average)}`, { size: 9 }));
    });

    addHeading(lines, '6. Examen Complexivo');
    const complexiveCareers = Array.isArray(report.careers) ? report.careers : [];
    if (!complexiveCareers.length) lines.push(makePdfLine('No existen resultados de Examen Complexivo para esta salida.', { size: 9 }));
    complexiveCareers.forEach(career => {
      const filtered = (career.students || []).filter(student => {
        const label = clean(outputLabel).toLowerCase();
        if (label.includes('online')) return student.modality === 'en_linea';
        if (label.includes('presencial')) return student.modality === 'presencial';
        return true;
      });
      if (filtered.length) lines.push(makePdfLine(`${career.name}: ${filtered.length} estudiantes`, { bold: true, size: 9, gapBefore: 3 }));
      filtered.forEach(student => lines.push(makePdfLine(`${student.full_name || student.identification} · ${student.final_status || 'Pendiente'} · ${grade(student.final_grade)}`, { size: 8 })));
    });

    addHeading(lines, '7. Trabajo de Titulación');
    if (!projects.length) lines.push(makePdfLine('No existen registros de Trabajo de Titulación para esta salida.', { size: 9 }));
    projects.forEach(project => {
      lines.push(makePdfLine(`${project.full_name || project.identification} · ${project.career_name || 'Sin carrera'} · ${project.final_status || 'Pendiente'} · ${grade(project.final_grade)}`, { size: 8 }));
      if (project.title) lines.push(makePdfLine(`Tema: ${project.title}`, { size: 8 }));
    });

    addHeading(lines, '8. Diagnóstico y trazabilidad');
    (audit.controls || []).forEach(control => lines.push(makePdfLine(`${control.status === 'ok' ? 'OK' : control.status === 'error' ? 'ERROR' : 'REVISAR'} · ${control.name}: ${control.detail}`, { size: 9 })));
    addRow(lines, 'Fuente de datos', audit.traceability?.source || 'GOOGLE_SHEETS');
    addRow(lines, 'Sincronizado', audit.traceability?.synced_at || '—');

    addHeading(lines, '9. Conclusiones');
    lines.push(makePdfLine(`Se consolidaron ${students.length} estudiantes y ${careers.length} carreras para la salida seleccionada. El estado de validación al momento de la generación fue «${audit.state}».`));
    lines.push(makePdfLine('Este archivo corresponde a una versión generada por Informtit y queda registrada en el historial local del navegador.', { size: 8, gapBefore: 4 }));

    return lines;
  }

  async function generateArtifact(reportId, outputLabel) {
    const bundleRaw = await reportBundle(reportId);
    const bundle = filterByOutput(bundleRaw, outputLabel);
    const audit = await buildAudit(reportId);
    const pdfBytes = createPdf(buildPdfLines(bundle, audit, outputLabel));
    const report = bundle.report || {};
    const generatedAt = nowIso();
    const artifactId = `pdf-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    const cleanLabel = clean(outputLabel) || (report.report_type === 'pvc' ? 'PVC' : 'Consolidado');
    const periodSafe = clean(report.period || 'periodo').replace(/[^A-Za-z0-9ÁÉÍÓÚÜÑáéíóúüñ_-]+/g, '_');
    const labelSafe = cleanLabel.replace(/[^A-Za-z0-9ÁÉÍÓÚÜÑáéíóúüñ_-]+/g, '_');
    const filename = `Informtit_${periodSafe}_${labelSafe}_${generatedAt.slice(0, 10)}.pdf`;
    const rows = readArtifacts().map(item => Number(item.report_id) === Number(reportId) && item.modality_label === cleanLabel && item.status === 'vigente'
      ? { ...item, status: 'historico' }
      : item);
    const artifact = {
      artifact_id: artifactId,
      report_id: Number(reportId),
      modality_label: cleanLabel,
      generated_at: generatedAt,
      status: 'vigente',
      version: clean(report.version) || '1.0',
      filename,
      size: pdfBytes.length,
      source: 'BROWSER_PDF',
      period_id: report.periodoId || report.firebase_period_id || '',
      audit_state: audit.state,
      pdf_base64: bytesToBase64(pdfBytes),
    };
    rows.unshift(artifact);
    writeArtifacts(rows);
    return artifact;
  }

  async function addImage(reportId, payload) {
    const rows = readReports();
    const index = findReportIndex(rows, reportId);
    if (index < 0) throw new Error('Informe no encontrado.');
    const dataUrl = clean(payload.data_url);
    if (!dataUrl.startsWith('data:image/')) throw new Error('La imagen no tiene un formato válido.');
    const image = {
      id: Date.now(),
      report_id: Number(rows[index].id),
      filename: clean(payload.original_name) || `imagen-${Date.now()}.png`,
      original_name: clean(payload.original_name) || 'imagen',
      title: clean(payload.title),
      description: clean(payload.description),
      source: clean(payload.source),
      career_id: payload.career_id ? Number(payload.career_id) : null,
      section: clean(payload.section) || 'evidencia_general',
      data_url: dataUrl,
      created_at: nowIso(),
    };
    rows[index].images = Array.isArray(rows[index].images) ? rows[index].images : [];
    rows[index].images.push(image);
    rows[index].updated_at = nowIso();
    try { writeReports(rows); }
    catch (_) { throw new Error('No hay espacio suficiente en el navegador para guardar esta imagen. Reduzca su tamaño o elimine evidencias anteriores.'); }
    return image;
  }

  function deleteImage(imageId) {
    const rows = readReports();
    let deleted = false;
    rows.forEach(report => {
      const before = Array.isArray(report.images) ? report.images : [];
      const after = before.filter(image => Number(image.id) !== Number(imageId));
      if (after.length !== before.length) {
        report.images = after;
        report.updated_at = nowIso();
        deleted = true;
      }
    });
    if (deleted) writeReports(rows);
    return deleted;
  }

  window.fetch = async function pagesBrowserServicesFetch(input, init = {}) {
    const path = pathOf(input);
    const method = methodOf(input, init);

    if (path === '/api/health' && method === 'GET') {
      return jsonResponse({ ok: true, mode: 'github-pages-sheets', database: 'Google Sheets', browser_services: true });
    }
    if (path === '/api/runtime-info' && method === 'GET') {
      return jsonResponse({ ok: true, build: 'GitHub Pages + Google Sheets', database: 'Google Sheets', browser_services: true });
    }

    let match = path.match(/^\/api\/reports\/(\d+)$/);
    if (match && method === 'GET') {
      const response = await previousFetch(input, init);
      if (!response.ok) return response;
      const payload = await response.clone().json().catch(() => ({}));
      if (payload?.report) {
        const roster = await previousJson(`/api/reports/${Number(match[1])}/roster`, {});
        const summary = roster?.summary || {};
        payload.report.project_summary = {
          ...(payload.report.project_summary || {}),
          period_project_id: Number(payload.report.id || match[1]),
          report_type: payload.report.report_type || 'normal',
          periodoId: payload.report.periodoId || payload.report.firebase_period_id || '',
          presencial_report_id: Number(payload.report.id || match[1]),
          online_report_id: Number(payload.report.id || match[1]),
          presencial_students: Number(summary.presencial || 0),
          online_students: Number(summary.online || 0),
        };
      }
      return jsonResponse(payload, response.status);
    }

    match = path.match(/^\/api\/reports\/(\d+)\/audit$/);
    if (match && method === 'GET') {
      try {
        const audit = await buildAudit(Number(match[1]));
        return jsonResponse({ ok: true, audit, preflight_token: `pages-${Date.now()}` });
      } catch (error) {
        return jsonResponse({ ok: false, error: error.message || String(error) }, 500);
      }
    }

    match = path.match(/^\/api\/reports\/(\d+)\/pdf-jobs$/);
    if (match && method === 'POST') {
      const reportId = Number(match[1]);
      try {
        const body = await bodyOf(input, init);
        const artifact = await generateArtifact(reportId, body.output_label || lastPdfOutputLabel || 'PDF');
        const job = {
          id: `job-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
          report_id: reportId,
          status: 'completed',
          progress: 100,
          stage: 'PDF generado',
          detail: 'La versión quedó registrada en «PDFs generados».',
          duration_seconds: 0,
          artifact_id: artifact.artifact_id,
          steps: [
            { stage: 'Validación completada', progress: 25 },
            { stage: 'Composición documental', progress: 70 },
            { stage: 'PDF generado', progress: 100 },
          ],
        };
        jobs.set(job.id, job);
        return jsonResponse({ ok: true, job }, 201);
      } catch (error) {
        return jsonResponse({ ok: false, error: error.message || String(error) }, 500);
      }
    }

    match = path.match(/^\/api\/pdf-jobs\/([^/]+)$/);
    if (match && method === 'GET') {
      const job = jobs.get(match[1]);
      return job ? jsonResponse({ ok: true, job }) : jsonResponse({ ok: false, error: 'Proceso PDF no encontrado.' }, 404);
    }

    match = path.match(/^\/api\/reports\/(\d+)\/generated-pdfs$/);
    if (match && method === 'GET') {
      const reportId = Number(match[1]);
      const rows = readArtifacts().filter(item => Number(item.report_id) === reportId).map(artifactMeta);
      return jsonResponse({ ok: true, generated_pdfs: rows, source: 'BROWSER_PDF' });
    }

    match = path.match(/^\/api\/reports\/(\d+)\/generated-pdfs\/([^/]+)\/download$/);
    if (match && method === 'GET') {
      const reportId = Number(match[1]);
      const artifact = readArtifacts().find(item => Number(item.report_id) === reportId && item.artifact_id === match[2]);
      if (!artifact?.pdf_base64) return jsonResponse({ ok: false, error: 'PDF no encontrado.' }, 404);
      return binaryResponse(base64ToBytes(artifact.pdf_base64), artifact.filename);
    }

    match = path.match(/^\/api\/reports\/(\d+)\/generated-pdfs\/([^/]+)$/);
    if (match && method === 'DELETE') {
      const reportId = Number(match[1]);
      const before = readArtifacts();
      const after = before.filter(item => !(Number(item.report_id) === reportId && item.artifact_id === match[2]));
      writeArtifacts(after);
      return jsonResponse({ ok: true, deleted: before.length - after.length });
    }

    match = path.match(/^\/api\/reports\/(\d+)\/images$/);
    if (match && method === 'POST') {
      try {
        const image = await addImage(Number(match[1]), await bodyOf(input, init));
        return jsonResponse({ ok: true, image }, 201);
      } catch (error) {
        return jsonResponse({ ok: false, error: error.message || String(error) }, 500);
      }
    }

    match = path.match(/^\/api\/images\/(\d+)$/);
    if (match && method === 'DELETE') {
      return deleteImage(Number(match[1]))
        ? jsonResponse({ ok: true, deleted_id: Number(match[1]) })
        : jsonResponse({ ok: false, error: 'Imagen no encontrada.' }, 404);
    }

    return previousFetch(input, init);
  };

  window.InformtitPagesBrowserServices = Object.freeze({
    buildAudit,
    source: 'GITHUB_PAGES_BROWSER_SERVICES',
  });
})();
