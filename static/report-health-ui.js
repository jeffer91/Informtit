(() => {
  'use strict';

  if (typeof renderReport !== 'function' || typeof api !== 'function') return;

  let firstReportId = 0;
  let requestToken = 0;

  const STATUS = Object.freeze({
    correct: { label: 'Correcto', className: 'health-correct' },
    review: { label: 'Revisar', className: 'health-review' },
    incomplete: { label: 'Incompleto', className: 'health-incomplete' },
    empty: { label: 'Sin datos', className: 'health-empty' },
    pending: { label: 'Pendiente', className: 'health-pending' },
  });

  function clean(value) {
    return String(value ?? '').trim();
  }

  function esc(value) {
    if (typeof escapeHtml === 'function') return escapeHtml(clean(value));
    return clean(value).replace(/[&<>"']/g, char => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;',
    }[char]));
  }

  function number(value) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }

  function reportIsPvc(report) {
    const project = report?.project_summary || {};
    return clean(report?.report_type || project?.report_type).toLowerCase() === 'pvc';
  }

  async function safeApi(path) {
    try {
      const data = await api(path);
      return { ok: true, data };
    } catch (error) {
      return { ok: false, error: clean(error?.message) || 'No disponible' };
    }
  }

  function ensureStructure(reportId) {
    const tabs = document.getElementById('report-tabs');
    const workspace = document.getElementById('report-workspace');
    if (!tabs || !workspace || workspace.hidden) return null;

    let button = tabs.querySelector('[data-tab="summary"]');
    if (!button) {
      button = document.createElement('button');
      button.type = 'button';
      button.className = 'tab';
      button.dataset.tab = 'summary';
      button.textContent = 'Resumen';
      tabs.insertBefore(button, tabs.firstElementChild);
    }

    let content = document.getElementById('tab-summary');
    if (!content) {
      content = document.createElement('div');
      content.id = 'tab-summary';
      content.className = 'tab-content';
      const roster = document.getElementById('tab-roster');
      roster?.parentElement?.insertBefore(content, roster);
    }

    if (firstReportId !== reportId) {
      firstReportId = reportId;
      tabs.querySelectorAll('.tab').forEach(tab => tab.classList.remove('active'));
      workspace.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));
      button.classList.add('active');
      content.classList.add('active');
    }

    return content;
  }

  function openTab(tab) {
    const button = document.querySelector(`#report-tabs .tab[data-tab="${tab}"]`);
    if (button && !button.hidden) button.click();
  }

  function rosterStatus(result) {
    if (!result.ok) return {
      key: 'requirements', title: 'Requisitos', status: 'review', detail: result.error, tab: 'roster', required: true,
    };
    const summary = result.data?.summary || {};
    const students = number(summary.students);
    if (!students) return {
      key: 'requirements', title: 'Requisitos', status: 'empty', detail: 'No se encontró población del período.', tab: 'roster', required: true,
    };
    return {
      key: 'requirements', title: 'Requisitos', status: 'correct',
      detail: `${students} estudiantes · ${number(summary.requirements_complete)} completos · ${number(summary.requirements_pending)} con requisitos pendientes`,
      tab: 'roster', required: true,
    };
  }

  function scheduleStatus(result, pvc) {
    const title = pvc ? 'Cronogramas de Artículo Académico' : 'Cronogramas';
    if (!result.ok) return {
      key: 'schedule', title, status: 'review', detail: result.error, tab: 'schedules', required: true,
    };

    const schedules = result.data?.schedules || {};
    const complexive = pvc ? [] : (schedules.complexive || []);
    const article = schedules.thesis || [];
    const all = pvc ? article : [...complexive, ...article];

    if (!all.length) return {
      key: 'schedule', title, status: 'empty',
      detail: pvc ? 'Todavía no hay cronogramas de Artículo Académico guardados.' : 'No hay actividades registradas.',
      tab: 'schedules', required: true,
    };

    if (pvc) {
      const names = new Set(article.map(item => clean(item.phase)).filter(Boolean));
      const groups = names.size || 1;
      return {
        key: 'schedule', title, status: 'correct',
        detail: `${groups} cronograma${groups === 1 ? '' : 's'} · ${article.length} actividades`,
        tab: 'schedules', required: true,
      };
    }

    const incompleteExecution = all.filter(item => {
      const value = clean(item.execution_status).toLowerCase();
      return value && (value !== 'cumplido' || number(item.compliance_percentage) !== 100);
    });
    let status = incompleteExecution.length ? 'review' : 'correct';
    if (!complexive.length || !article.length) status = 'incomplete';
    const pieces = [`${complexive.length} Complexivo`, `${article.length} Trabajo de Titulación`];
    if (!incompleteExecution.length) pieces.push('100 % cumplido');
    else pieces.push(`${incompleteExecution.length} por revisar`);
    return { key: 'schedule', title, status, detail: pieces.join(' · '), tab: 'schedules', required: true };
  }

  function pvcResultsStatus(result) {
    if (!result.ok) return {
      key: 'pvc-results', title: 'Resultados PVC', status: 'review', detail: result.error, tab: 'projects', required: true,
    };

    const summary = result.data?.summary || {};
    const total = number(summary.pvc_total);
    const matched = number(summary.matched);
    const evaluated = number(summary.evaluated);
    const unmatched = number(summary.unmatched);
    const formulaWarnings = number(summary.formula_warnings);
    const notEvaluated = number(summary.not_evaluated);

    if (!total) return {
      key: 'pvc-results', title: 'Resultados PVC', status: 'empty',
      detail: 'Todavía no se ha cargado la Base de resultados PVC de Artículo Académico.',
      tab: 'projects', required: true,
    };

    let status = 'correct';
    if (unmatched || formulaWarnings) status = 'review';
    else if (notEvaluated || evaluated < matched) status = 'incomplete';

    const pieces = [`${total} registros`, `${matched} conciliados`, `${evaluated} evaluados`];
    if (unmatched) pieces.push(`${unmatched} sin conciliar`);
    if (notEvaluated) pieces.push(`${notEvaluated} no evaluados`);
    if (formulaWarnings) pieces.push(`${formulaWarnings} alertas de fórmula`);

    return {
      key: 'pvc-results', title: 'Resultados PVC', status,
      detail: pieces.join(' · '), tab: 'projects', required: true,
    };
  }

  function uniqueStudentsFromNuclei(courses) {
    const seen = new Set();
    courses.forEach(course => {
      (course.students || []).forEach(student => {
        const key = clean(student.identification || student.cedula || student.email || student.full_name);
        if (key) seen.add(key.toUpperCase());
      });
    });
    return seen.size;
  }

  function nucleiStatus(result) {
    if (!result.ok) return { key: 'nuclei', title: 'Núcleos', status: 'review', detail: result.error, tab: 'nuclei', required: true };
    const courses = result.data?.courses || [];
    if (!courses.length) return { key: 'nuclei', title: 'Núcleos', status: 'empty', detail: 'Todavía no existen cursos cargados.', tab: 'nuclei', required: true };
    const students = uniqueStudentsFromNuclei(courses);
    const nucleusNumbers = new Set(courses.map(course => number(course.nucleus_number)).filter(value => value > 0));
    const missingGrades = courses.reduce((sum, course) => sum + (course.students || []).filter(student => student.final_grade === null || student.final_grade === undefined || student.final_grade === '').length, 0);
    return {
      key: 'nuclei', title: 'Núcleos', status: missingGrades ? 'review' : nucleusNumbers.size < 4 ? 'incomplete' : 'correct',
      detail: `${nucleusNumbers.size} núcleos · ${courses.length} cursos · ${students} estudiantes${missingGrades ? ` · ${missingGrades} sin nota` : ''}`,
      tab: 'nuclei', required: true,
    };
  }

  function complexiveStatus(report) {
    const careers = Array.isArray(report?.careers) ? report.careers : [];
    const nestedStudents = careers.flatMap(career => Array.isArray(career.students) ? career.students : []);
    const total = nestedStudents.length || number(report?.complexive_records);
    if (!total) return { key: 'complexive', title: 'Examen Complexivo', status: 'empty', detail: 'Todavía no existen resultados cargados.', tab: 'careers', required: true };
    const missingGrades = nestedStudents.filter(student => student.final_grade === null || student.final_grade === undefined || student.final_grade === '').length;
    return {
      key: 'complexive', title: 'Examen Complexivo', status: missingGrades ? 'review' : 'correct',
      detail: `${careers.length} carreras · ${total} estudiantes${missingGrades ? ` · ${missingGrades} sin nota final` : ''}`,
      tab: 'careers', required: true,
    };
  }

  function projectsStatus(result, scheduleResult) {
    if (!result.ok) return { key: 'thesis', title: 'Trabajo de Titulación', status: 'review', detail: result.error, tab: 'projects', required: true };
    const projects = result.data?.projects || [];
    const thesisSchedule = scheduleResult.ok ? (scheduleResult.data?.schedules?.thesis || []) : [];
    if (!projects.length) return {
      key: 'thesis', title: 'Trabajo de Titulación', status: thesisSchedule.length ? 'incomplete' : 'empty',
      detail: thesisSchedule.length ? `Cronograma correcto (${thesisSchedule.length} actividades), pero aún no hay resultados de estudiantes.` : 'Todavía no hay cronograma ni resultados registrados.',
      tab: 'projects', required: true,
    };
    const missingGrades = projects.filter(project => project.final_grade === null || project.final_grade === undefined || project.final_grade === '').length;
    return {
      key: 'thesis', title: 'Trabajo de Titulación', status: missingGrades ? 'review' : 'correct',
      detail: `${projects.length} estudiantes · ${number(result.data?.summary?.approved)} aprobados${missingGrades ? ` · ${missingGrades} sin nota final` : ''}`,
      tab: 'projects', required: true,
    };
  }

  function modalityStatus(result) {
    if (!result.ok) return { key: 'modality', title: 'Clasificación de modalidad', status: 'review', detail: result.error, tab: 'students', required: true };
    const summary = result.data?.summary || {};
    const students = number(summary.students);
    if (!students) return { key: 'modality', title: 'Clasificación de modalidad', status: 'empty', detail: 'No hay estudiantes para clasificar.', tab: 'students', required: true };
    const classified = number(summary.presencial) + number(summary.online);
    const review = number(summary.review);
    return {
      key: 'modality', title: 'Clasificación de modalidad', status: review || classified !== students ? 'review' : 'correct',
      detail: `${number(summary.presencial)} Presencial · ${number(summary.online)} Online${review ? ` · ${review} por revisar` : ''}`,
      tab: 'students', required: true,
    };
  }

  function firebaseStatus(results) {
    const sources = results.filter(result => result.ok)
      .flatMap(result => [result.data?.source, result.data?.schedule_meta?.source])
      .map(clean).filter(Boolean);
    const firebase = sources.some(source => /firebase/i.test(source));
    const failed = results.filter(result => !result.ok).length;
    return {
      key: 'firebase', title: 'Firebase',
      status: firebase && !failed ? 'correct' : failed ? 'review' : 'incomplete',
      detail: firebase ? (failed ? `Firebase conectado · ${failed} módulo(s) con error de lectura` : 'Firebase UTET conectado y utilizado como fuente del período.') : (failed ? `${failed} módulo(s) no pudieron confirmar la conexión.` : 'Los datos están disponibles, pero no se confirmó Firebase como fuente.'),
      tab: '', required: true,
    };
  }

  function pdfStatus(result, pvc) {
    if (!result.ok) return { key: 'pdfs', title: 'PDFs', status: 'pending', detail: 'El historial de PDFs todavía no está disponible.', action: 'pdfs', required: false };
    const items = Array.isArray(result.data?.generated_pdfs) ? result.data.generated_pdfs : [];
    if (!items.length) return { key: 'pdfs', title: 'PDFs', status: 'pending', detail: 'Todavía no se ha generado una versión del informe.', action: 'pdfs', required: false };
    const current = items.filter(item => clean(item.status).toLowerCase() === 'vigente');
    let correct = current.length > 0;
    if (!pvc) {
      const labels = current.map(item => clean(item.modality_label).toLowerCase());
      correct = labels.some(label => label.includes('presencial')) && labels.some(label => label.includes('online') || label.includes('línea'));
    }
    return {
      key: 'pdfs', title: 'PDFs', status: correct ? 'correct' : 'incomplete',
      detail: `${items.length} versiones · ${current.length} vigentes${!pvc && !correct ? ' · faltan ambas salidas vigentes' : ''}`,
      action: 'pdfs', required: false,
    };
  }

  function componentCard(component) {
    const meta = STATUS[component.status] || STATUS.review;
    const button = component.tab
      ? `<button type="button" class="button secondary small" data-health-tab="${esc(component.tab)}">Abrir</button>`
      : component.action === 'pdfs'
        ? '<button type="button" class="button secondary small" data-health-pdfs>Ver PDFs</button>'
        : '<button type="button" class="button secondary small" data-health-refresh>Actualizar</button>';
    return `
      <article class="health-card ${meta.className}">
        <div class="health-card-head"><h3>${esc(component.title)}</h3><span class="health-status">${esc(meta.label)}</span></div>
        <p>${esc(component.detail)}</p>
        <div class="health-card-action">${button}</div>
      </article>`;
  }

  function draw(container, report, components, syncedAt = '') {
    const required = components.filter(component => component.required !== false);
    const correct = required.filter(component => component.status === 'correct').length;
    const percentage = required.length ? Math.round((correct / required.length) * 100) : 100;
    const attention = required.filter(component => component.status !== 'correct');
    const allCorrect = attention.length === 0;
    const pvc = reportIsPvc(report);

    container.innerHTML = `
      <section class="health-overview">
        <div class="health-overview-copy">
          <span class="eyebrow">${pvc ? 'Control automático del PVC' : 'Control automático del período'}</span>
          <h2>${allCorrect ? 'Informe listo' : `${correct} de ${required.length} componentes correctos`}</h2>
          <p>${allCorrect ? 'Los componentes obligatorios están correctamente cargados.' : `Informtit detectó ${attention.length} componente(s) que requieren información o revisión.`}</p>
          ${syncedAt ? `<small>Última referencia de sincronización: ${esc(syncedAt)}</small>` : ''}
        </div>
        <div class="health-score"><strong>${percentage}%</strong><span>estado general</span></div>
      </section>
      <div class="health-progress" aria-label="${percentage}% completado"><span style="width:${percentage}%"></span></div>
      ${attention.length ? `<div class="health-attention"><strong>Requiere atención:</strong> ${attention.map(item => esc(item.title)).join(' · ')}</div>` : ''}
      <div class="health-grid">${components.map(componentCard).join('')}</div>`;

    container.querySelectorAll('[data-health-tab]').forEach(button => button.addEventListener('click', () => openTab(button.dataset.healthTab)));
    container.querySelectorAll('[data-health-refresh]').forEach(button => button.addEventListener('click', () => document.getElementById('refresh-btn')?.click()));
    container.querySelectorAll('[data-health-pdfs]').forEach(button => button.addEventListener('click', () => {
      if (typeof window.informtitOpenGeneratedPdfs === 'function') window.informtitOpenGeneratedPdfs();
      else document.getElementById('open-generated-pdfs')?.click();
    }));
  }

  async function loadHealth(report, container, force = false) {
    const token = ++requestToken;
    const reportId = Number(report?.id || 0);
    if (!reportId || !container) return;
    container.innerHTML = '<div class="panel"><div class="empty-mini">Analizando el estado completo del período...</div></div>';

    const pvc = reportIsPvc(report);
    const suffix = force ? `?health=${Date.now()}` : '';

    if (pvc) {
      const [roster, schedules, pvcResults, pdfs] = await Promise.all([
        safeApi(`/api/reports/${reportId}/roster${suffix}`),
        safeApi(`/api/reports/${reportId}/schedules${suffix}`),
        safeApi(`/api/reports/${reportId}/pvc/summary${suffix}`),
        safeApi(`/api/reports/${reportId}/generated-pdfs${suffix}`),
      ]);
      if (token !== requestToken || Number(state?.activeReport?.id || 0) !== reportId) return;
      const currentReport = state.activeReport || report;
      const components = [
        rosterStatus(roster),
        scheduleStatus(schedules, true),
        pvcResultsStatus(pvcResults),
        pdfStatus(pdfs, true),
      ];
      const syncedAt = clean(roster.data?.synced_at || schedules.data?.schedule_meta?.synced_at || pvcResults.data?.synced_at);
      draw(container, currentReport, components, syncedAt);
      return;
    }

    const [roster, students, schedules, nuclei, projects, pdfs] = await Promise.all([
      safeApi(`/api/reports/${reportId}/roster${suffix}`),
      safeApi(`/api/reports/${reportId}/students-domain${suffix}`),
      safeApi(`/api/reports/${reportId}/schedules${suffix}`),
      safeApi(`/api/reports/${reportId}/nuclei${suffix}`),
      safeApi(`/api/reports/${reportId}/projects${suffix}`),
      safeApi(`/api/reports/${reportId}/generated-pdfs${suffix}`),
    ]);
    if (token !== requestToken || Number(state?.activeReport?.id || 0) !== reportId) return;
    const currentReport = state.activeReport || report;
    const components = [
      rosterStatus(roster),
      scheduleStatus(schedules, false),
      nucleiStatus(nuclei),
      complexiveStatus(currentReport),
      projectsStatus(projects, schedules),
      modalityStatus(students),
      firebaseStatus([roster, students, schedules, nuclei, projects]),
      pdfStatus(pdfs, false),
    ];
    const syncedAt = clean(roster.data?.synced_at || students.data?.synced_at || schedules.data?.schedule_meta?.synced_at);
    draw(container, currentReport, components, syncedAt);
  }

  const style = document.createElement('style');
  style.textContent = `
    .health-overview { display:flex; justify-content:space-between; gap:24px; align-items:center; padding:24px; border:1px solid #e5e7eb; border-radius:16px; background:#fff; }
    .health-overview-copy h2 { margin:4px 0 6px; font-size:24px; }
    .health-overview-copy p { margin:0; color:#64748b; }
    .health-overview-copy small { display:block; margin-top:8px; color:#94a3b8; }
    .health-score { min-width:118px; text-align:center; padding:14px; border-radius:14px; background:#f8fafc; }
    .health-score strong { display:block; font-size:30px; line-height:1; }
    .health-score span { display:block; margin-top:5px; color:#64748b; font-size:12px; }
    .health-progress { height:8px; margin:14px 0 18px; overflow:hidden; border-radius:999px; background:#e5e7eb; }
    .health-progress span { display:block; height:100%; background:#16a34a; border-radius:inherit; transition:width .2s ease; }
    .health-attention { margin-bottom:16px; padding:11px 14px; border-radius:10px; background:#fff7ed; color:#9a3412; font-size:13px; }
    .health-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(245px,1fr)); gap:14px; }
    .health-card { min-height:150px; display:flex; flex-direction:column; padding:16px; border-radius:14px; border:1px solid #e5e7eb; background:#fff; }
    .health-card-head { display:flex; justify-content:space-between; gap:12px; align-items:flex-start; }
    .health-card h3 { margin:0; font-size:16px; }
    .health-card p { margin:12px 0 16px; color:#64748b; font-size:13px; line-height:1.45; }
    .health-card-action { margin-top:auto; }
    .health-status { flex:none; padding:4px 8px; border-radius:999px; font-size:11px; font-weight:800; }
    .health-correct { border-color:#bbf7d0; }
    .health-correct .health-status { background:#dcfce7; color:#166534; }
    .health-review { border-color:#fed7aa; }
    .health-review .health-status { background:#ffedd5; color:#9a3412; }
    .health-incomplete { border-color:#fde68a; }
    .health-incomplete .health-status { background:#fef3c7; color:#92400e; }
    .health-empty .health-status, .health-pending .health-status { background:#f1f5f9; color:#475569; }
    @media (max-width:720px) { .health-overview { align-items:flex-start; flex-direction:column; } .health-score { width:100%; } }
  `;
  document.head.appendChild(style);

  const previousRenderReport = renderReport;
  renderReport = function renderReportWithHealthDashboard() {
    previousRenderReport();
    const report = state?.activeReport;
    const reportId = Number(report?.id || 0);
    if (!reportId) return;
    const container = ensureStructure(reportId);
    if (container) void loadHealth(report, container);
  };

  document.addEventListener('informtit:pdf-generated', () => {
    const report = state?.activeReport;
    const container = document.getElementById('tab-summary');
    if (report?.id && container) void loadHealth(report, container, true);
  });
})();
