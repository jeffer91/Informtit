(() => {
  'use strict';

  if (!/(^|\.)github\.io$/i.test(window.location.hostname)) return;
  if (!window.InformtitPagesStability) return;

  const previousFetch = window.fetch.bind(window);
  const PDFS_KEY = 'informtit.pages.generatedPdfs.v2';
  const jobs = new Map();
  const clean = value => String(value ?? '').replace(/\u00a0/g, ' ').trim().replace(/\s+/g, ' ');
  const fold = value => clean(value).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toUpperCase();
  const nowIso = () => new Date().toISOString();

  function pathOf(input) {
    try { return new URL(typeof input === 'string' ? input : input?.url, window.location.href).pathname; }
    catch (_) { return ''; }
  }
  function methodOf(input, init) { return String(init?.method || input?.method || 'GET').toUpperCase(); }
  async function bodyOf(input, init) {
    if (typeof init?.body === 'string') { try { return JSON.parse(init.body); } catch (_) { return {}; } }
    if (typeof Request !== 'undefined' && input instanceof Request) { try { return await input.clone().json(); } catch (_) {} }
    return {};
  }
  function jsonResponse(payload, status = 200) {
    return Promise.resolve(new Response(JSON.stringify(payload), { status, headers: { 'Content-Type': 'application/json; charset=utf-8' } }));
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
    return { report: reportData.report || {}, roster: roster || {}, studentsDomain: studentsDomain || {}, nuclei: nuclei || {}, projects: projects || {}, schedules: schedules || {} };
  }

  function parseConfig(value) {
    if (!value) return {};
    if (typeof value === 'object') return value;
    try { return JSON.parse(String(value)); } catch (_) { return {}; }
  }
  function documentConfig(report) {
    const raw = parseConfig(report?.document_config || report?.documentConfig || report?.document_config_json);
    return {
      cover: {
        enabled: raw.cover?.enabled !== false,
        institution: clean(raw.cover?.institution || ''),
        title: clean(raw.cover?.title || report?.name || 'Informe Final del Proceso de Titulación'),
        subtitle: clean(raw.cover?.subtitle || ''),
        show_period: raw.cover?.show_period !== false,
        show_code: raw.cover?.show_code !== false,
        show_date: raw.cover?.show_date !== false,
        show_responsibles: raw.cover?.show_responsibles !== false,
      },
      header: {
        enabled: raw.header?.enabled !== false,
        left_text: clean(raw.header?.left_text || ''),
        center_text: clean(raw.header?.center_text || report?.name || 'Informe Final de Titulación'),
        show_code: raw.header?.show_code !== false,
        show_version: raw.header?.show_version !== false,
        show_period: raw.header?.show_period === true,
        exclude_cover: raw.header?.exclude_cover !== false,
      },
      sections: Array.isArray(raw.sections) ? raw.sections : [],
    };
  }
  function periodIdOf(report) { return clean(report?.periodoId || report?.firebase_period_id || report?.period_id); }
  function outputCode(report, label) { return fold(label).includes('ONLINE') ? (report.code_online || report.code || '—') : (report.code_presencial || report.code || '—'); }

  function safeLatin1(value) {
    return clean(value).replace(/[–—]/g, '-').replace(/[“”]/g, '"').replace(/[‘’]/g, "'").replace(/→/g, '->').replace(/•/g, '-').replace(/[^\x20-\xFF]/g, '?');
  }
  function pdfLiteral(value) { return safeLatin1(value).replace(/([\\()])/g, '\\$1'); }
  function stringBytes(value) {
    const text = String(value), out = new Uint8Array(text.length);
    for (let i = 0; i < text.length; i += 1) out[i] = text.charCodeAt(i) & 0xff;
    return out;
  }
  function bytesToBase64(bytes) {
    let binary = '';
    for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, Math.min(i + 0x8000, bytes.length)));
    return btoa(binary);
  }
  function wrapText(value, width = 92) {
    const words = safeLatin1(value).split(/\s+/).filter(Boolean), lines = [];
    if (!words.length) return [''];
    let current = '';
    words.forEach(word => {
      if (!current) current = word;
      else if (`${current} ${word}`.length <= width) current += ` ${word}`;
      else { lines.push(current); current = word; }
    });
    if (current) lines.push(current);
    return lines;
  }
  function line(text = '', options = {}) {
    return { text: safeLatin1(text), bold: Boolean(options.bold), size: Number(options.size || 10), gapBefore: Number(options.gapBefore || 0), gapAfter: Number(options.gapAfter || 0), pageBreakBefore: Boolean(options.pageBreakBefore) };
  }

  function createPdf(lines, options = {}) {
    const pageWidth = 595, pageHeight = 842, left = 48, bottom = 50;
    const headerText = clean(options.headerText || '');
    const coverPage = Boolean(options.coverPage);
    const headerOnCover = Boolean(options.headerOnCover);
    const pages = [];
    let current = [], pageIndex = 0;
    const headerActive = () => Boolean(headerText && (!coverPage || pageIndex > 0 || headerOnCover));
    const pageTop = () => headerActive() ? 758 : 790;
    let y = pageTop();
    const pushPage = () => {
      if (current.length) pages.push(current);
      current = [];
      pageIndex += 1;
      y = pageTop();
    };
    (lines || []).forEach(item => {
      const source = typeof item === 'string' ? line(item) : item;
      if (source.pageBreakBefore && current.length) pushPage();
      const wrapped = wrapText(source.text, source.bold ? 82 : 96);
      const lineHeight = Math.max(12, source.size + 3);
      const required = source.gapBefore + wrapped.length * lineHeight + source.gapAfter;
      if (y - required < bottom && current.length) pushPage();
      y -= source.gapBefore;
      wrapped.forEach(text => { current.push({ ...source, text, y }); y -= lineHeight; });
      y -= source.gapAfter;
    });
    if (current.length) pages.push(current);
    if (!pages.length) pages.push([{ ...line('Informtit'), y: 790 }]);

    const objects = new Map(), pageIds = [];
    const catalogId = 1, pagesId = 2, regularFontId = 3, boldFontId = 4;
    let nextId = 5;
    objects.set(catalogId, `<< /Type /Catalog /Pages ${pagesId} 0 R >>`);
    objects.set(regularFontId, '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>');
    objects.set(boldFontId, '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>');
    pages.forEach((pageLines, index) => {
      const pageId = nextId++, contentId = nextId++;
      pageIds.push(pageId);
      const commands = ['BT'];
      const showHeader = Boolean(headerText && (!coverPage || index > 0 || headerOnCover));
      if (showHeader) {
        commands.push('/F1 8 Tf');
        commands.push(`1 0 0 1 ${left} 812 Tm`);
        commands.push(`(${pdfLiteral(headerText)}) Tj`);
        commands.push('/F1 8 Tf');
        commands.push(`1 0 0 1 ${left} 800 Tm`);
        commands.push(`(${pdfLiteral('________________________________________________________________________________')}) Tj`);
      }
      pageLines.forEach(item => {
        commands.push(`/${item.bold ? 'F2' : 'F1'} ${Math.max(8, Math.min(18, Number(item.size || 10)))} Tf`);
        commands.push(`1 0 0 1 ${left} ${Math.max(bottom, Number(item.y || 790)).toFixed(1)} Tm`);
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
    for (let id = 1; id <= maxId; id += 1) { offsets[id] = stringBytes(pdf).length; pdf += `${id} 0 obj\n${objects.get(id) || '<<>>'}\nendobj\n`; }
    const xref = stringBytes(pdf).length;
    pdf += `xref\n0 ${maxId + 1}\n0000000000 65535 f \n`;
    for (let id = 1; id <= maxId; id += 1) pdf += `${String(offsets[id]).padStart(10, '0')} 00000 n \n`;
    pdf += `trailer\n<< /Size ${maxId + 1} /Root ${catalogId} 0 R >>\nstartxref\n${xref}\n%%EOF`;
    return stringBytes(pdf);
  }

  function grade(value) { const n = Number(value); return Number.isFinite(n) ? n.toFixed(2).replace('.', ',') : '—'; }

  function buildLines(bundle, audit, outputLabel) {
    const report = bundle.report || {}, config = documentConfig(report), cover = config.cover;
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

    if (cover.enabled) {
      if (cover.institution) lines.push(line(cover.institution, { bold: true, size: 12, gapAfter: 72 }));
      else lines.push(line('INSTITUCIÓN', { bold: true, size: 12, gapAfter: 72 }));
      lines.push(line(cover.title, { bold: true, size: 18, gapAfter: 12 }));
      if (cover.subtitle) lines.push(line(cover.subtitle, { size: 12, gapAfter: 24 }));
      if (cover.show_period) row('Período', report.period || '—');
      if (cover.show_code) row('Código', outputCode(report, outputLabel));
      if (cover.show_date) row('Fecha de elaboración', report.elaboration_date || '—');
      if (cover.show_responsibles) {
        lines.push(line('', { gapBefore: 80 }));
        if (report.prepared_by) row('Elaborado por', `${report.prepared_by}${report.prepared_role ? ` · ${report.prepared_role}` : ''}`);
        if (report.reviewed_by) row('Revisado por', `${report.reviewed_by}${report.reviewed_role ? ` · ${report.reviewed_role}` : ''}`);
        if (report.approved_by) row('Aprobado por', `${report.approved_by}${report.approved_role ? ` · ${report.approved_role}` : ''}`);
      }
      lines.push(line(report.name || 'Informe Final del Proceso de Titulación', { bold: true, size: 15, gapAfter: 8, pageBreakBefore: true }));
    } else {
      lines.push(line(report.name || 'Informe Final del Proceso de Titulación', { bold: true, size: 17, gapAfter: 8 }));
    }

    lines.push(line(outputLabel ? `Salida: ${outputLabel}` : 'Informe consolidado', { bold: true, size: 11, gapAfter: 10 }));
    row('Período', report.period || '—');
    row('periodId', periodIdOf(report) || '—');
    row('Código', outputCode(report, outputLabel));
    row('Versión', report.version || '1.0');
    row('Estado de auditoría', audit.state);

    heading('1. Resumen ejecutivo');
    row('Estudiantes', students.length); row('Carreras', careers.length); row('Requisitos completos', summary.requirements_complete || 0); row('Requisitos pendientes', summary.requirements_pending || 0);
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
    complexiveCareers.forEach(career => { lines.push(line(`${career.name}: ${career.students?.length || 0} estudiantes`, { bold: true, size: 9, gapBefore: 3 })); (career.students || []).forEach(student => lines.push(line(`${student.full_name || student.identification} · ${student.final_status || 'Pendiente'} · ${grade(student.final_grade)}`, { size: 8 }))); });
    heading('7. Trabajo de Titulación');
    if (!projects.length) lines.push(line('No existen registros de Trabajo de Titulación para esta salida.', { size: 9 }));
    projects.forEach(project => lines.push(line(`${project.full_name || project.identification} · ${project.career_name || 'Sin carrera'} · ${project.final_status || 'Pendiente'} · ${grade(project.final_grade)}`, { size: 8 })));
    heading('8. Diagnóstico y trazabilidad');
    (audit.controls || []).forEach(control => lines.push(line(`${control.status === 'ok' ? 'OK' : control.status === 'error' ? 'ERROR' : 'REVISAR'} · ${control.name}: ${control.detail}`, { size: 9 })));
    row('Fuente de datos', 'GOOGLE_SHEETS'); row('Sincronizado', audit.traceability?.synced_at || '—');
    heading('9. Conclusiones');
    lines.push(line(`Se consolidaron ${students.length} estudiantes y ${careers.length} carreras para la salida seleccionada. El estado de validación fue «${audit.state}».`));
    return lines;
  }

  function headerText(report, outputLabel) {
    const header = documentConfig(report).header;
    if (!header.enabled) return '';
    const meta = [];
    if (header.show_code) meta.push(outputCode(report, outputLabel));
    if (header.show_version) meta.push(`V. ${report.version || '1.0'}`);
    if (header.show_period) meta.push(report.period || '');
    return [header.left_text, header.center_text, meta.filter(Boolean).join(' · ')].filter(Boolean).join(' | ');
  }
  function readArtifacts() { try { const rows = JSON.parse(localStorage.getItem(PDFS_KEY) || '[]'); return Array.isArray(rows) ? rows : []; } catch (_) { return []; } }
  function writeArtifacts(rows) {
    let next = Array.isArray(rows) ? rows.slice() : [];
    next.sort((a, b) => clean(b.generated_at).localeCompare(clean(a.generated_at)));
    next = next.slice(0, 18);
    while (next.length) {
      try { localStorage.setItem(PDFS_KEY, JSON.stringify(next)); return; }
      catch (error) { if (next.length <= 1) throw error; next.pop(); }
    }
  }

  async function generateArtifact(reportId, outputLabel) {
    const rawBundle = await reportBundle(reportId);
    const health = await window.InformtitPagesStability.sourceHealth(rawBundle.report);
    if (health.errors.length) throw new Error(`No se puede generar el PDF porque fallaron fuentes institucionales: ${health.errors.map(item => item.source).join(', ')}.`);
    const bundle = window.InformtitPagesStability.filterBundle(rawBundle, outputLabel);
    const audit = window.InformtitPagesStability.buildAudit(bundle, health, outputLabel);
    if (!audit.can_generate_pdf) throw new Error('La auditoría detectó errores bloqueantes.');
    const config = documentConfig(bundle.report);
    const bytes = createPdf(buildLines(bundle, audit, outputLabel), {
      headerText: headerText(bundle.report, outputLabel),
      coverPage: config.cover.enabled,
      headerOnCover: config.header.enabled && !config.header.exclude_cover,
    });
    const generatedAt = nowIso(), cleanLabel = clean(outputLabel) || (bundle.report.report_type === 'pvc' ? 'PVC' : 'Consolidado');
    const artifactId = `pdf-doc-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    const periodSafe = clean(bundle.report.period || 'periodo').replace(/[^A-Za-z0-9ÁÉÍÓÚÜÑáéíóúüñ_-]+/g, '_');
    const labelSafe = cleanLabel.replace(/[^A-Za-z0-9ÁÉÍÓÚÜÑáéíóúüñ_-]+/g, '_');
    const rows = readArtifacts().map(item => Number(item.report_id) === Number(reportId) && item.modality_label === cleanLabel && item.status === 'vigente' ? { ...item, status: 'historico' } : item);
    const artifact = {
      artifact_id: artifactId, report_id: Number(reportId), modality_label: cleanLabel, generated_at: generatedAt,
      status: 'vigente', version: clean(bundle.report.version) || '1.0', filename: `Informtit_${periodSafe}_${labelSafe}_${generatedAt.slice(0, 10)}.pdf`,
      size: bytes.length, source: 'BROWSER_PDF_DOCUMENT_V2', period_id: periodIdOf(bundle.report), audit_state: audit.state,
      output_students: bundle.roster?.students?.length || 0, output_requirements_complete: bundle.roster?.summary?.requirements_complete || 0,
      cover_enabled: config.cover.enabled, header_enabled: config.header.enabled, pdf_base64: bytesToBase64(bytes),
    };
    rows.unshift(artifact); writeArtifacts(rows); return { artifact, audit };
  }

  window.fetch = async function pagesDocumentPdfFetch(input, init = {}) {
    const path = pathOf(input), method = methodOf(input, init);
    let match = path.match(/^\/api\/reports\/(\d+)\/pdf-jobs$/);
    if (match && method === 'POST') {
      try {
        const body = await bodyOf(input, init);
        const { artifact } = await generateArtifact(Number(match[1]), body.output_label || 'PDF');
        const job = {
          id: `doc-job-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`, report_id: Number(match[1]), status: 'completed', progress: 100,
          stage: 'Documento validado y generado', detail: 'Portada, cabecera, cifras por modalidad y fuentes institucionales aplicadas.', duration_seconds: 0,
          artifact_id: artifact.artifact_id,
          steps: [
            { stage: 'Fuentes institucionales verificadas', progress: 20 },
            { stage: 'Portada y cabecera aplicadas', progress: 45 },
            { stage: 'Indicadores recalculados por modalidad', progress: 70 },
            { stage: 'PDF generado', progress: 100 },
          ],
        };
        jobs.set(job.id, job); return jsonResponse({ ok: true, job }, 201);
      } catch (error) { return jsonResponse({ ok: false, error: clean(error?.message || error) }, 409); }
    }
    match = path.match(/^\/api\/pdf-jobs\/([^/]+)$/);
    if (match && method === 'GET' && jobs.has(match[1])) return jsonResponse({ ok: true, job: jobs.get(match[1]) });
    return previousFetch(input, init);
  };

  window.InformtitDocumentPdf = Object.freeze({ documentConfig, version: '2.0.0' });
})();