(() => {
  window.INFORMTIT_MINIMAL_NUCLEI = true;

  const previousRenderReport = renderReport;
  let activeNucleiReportId = 0;
  let selectedCareer = '';
  let searchText = '';

  function esc(value = '') {
    return typeof escapeHtml === 'function'
      ? escapeHtml(String(value))
      : String(value).replace(/[&<>"']/g, character => ({
          '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;',
        })[character]);
  }

  function normalize(value = '') {
    return String(value)
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, ' ')
      .trim();
  }

  function compareText(left, right) {
    return String(left || '').localeCompare(String(right || ''), 'es', { sensitivity: 'base' });
  }

  function fmt(value) {
    if (value === null || value === undefined || value === '') return '—';
    const number = Number(value);
    return Number.isFinite(number) ? number.toFixed(2).replace('.', ',') : '—';
  }

  function unique(values) {
    return [...new Set(values.map(value => String(value || '').trim()).filter(Boolean))].sort(compareText);
  }

  function courseAverage(course) {
    const value = Number(course?.course_average);
    return Number.isFinite(value) ? value : null;
  }

  function statusCounts(course) {
    const students = course?.students || [];
    const approved = students.filter(student => normalize(student.final_status) === 'aprobado').length;
    const failed = students.filter(student => normalize(student.final_status) === 'reprobado').length;
    const pending = students.length - approved - failed;
    return { approved, failed, pending };
  }

  renderReport = function renderReportWithExcelNuclei() {
    previousRenderReport();
    if (state.activeReport?.id) renderNucleiModule();
  };

  async function renderNucleiModule() {
    const tab = document.querySelector('#tab-nuclei');
    const reportId = Number(state.activeReport?.id || 0);
    if (!tab || !reportId) return;

    if (activeNucleiReportId !== reportId) {
      activeNucleiReportId = reportId;
      selectedCareer = '';
      searchText = '';
    }

    tab.dataset.nucleiReportId = String(reportId);
    bindDelegatedEvents(tab);
    tab.innerHTML = '<div class="panel"><div class="empty-mini">Cargando Núcleos...</div></div>';

    try {
      const data = await api(`/api/reports/${reportId}/nuclei`);
      if (Number(state.activeReport?.id || 0) !== reportId) return;
      const courses = data?.courses || [];
      normalizeSelection(courses);
      tab.innerHTML = markup(courses, data?.excel_import || null);
      tab.dataset.nucleiReportId = String(reportId);
      applyFilters(tab);
    } catch (error) {
      tab.innerHTML = `<div class="panel"><div class="empty-mini">${esc(error.message)}</div></div>`;
    }
  }

  function normalizeSelection(courses) {
    const careers = unique(courses.map(course => course.career_name));
    if (selectedCareer && !careers.some(career => normalize(career) === normalize(selectedCareer))) {
      selectedCareer = '';
    }
  }

  function markup(courses, excelImport) {
    return `
      <div class="process-stack excel-nuclei" data-minimal-nuclei>
        <section class="panel excel-nuclei-upload">
          <div class="panel-head">
            <div>
              <h2>Núcleos</h2>
              <p>Suba el Excel consolidado de Núcleos. Cada nueva carga reemplaza completamente la información anterior de este módulo.</p>
            </div>
          </div>
          <form id="nuclei-excel-form" class="nuclei-excel-form">
            <label class="nuclei-file-field">Archivo Excel (.xlsx)
              <input type="file" name="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" required>
              <small>Columnas requeridas: nombre_carrera, nombre_profesor, nombre_estudiante, materia, nota_final, estado y trabajoTitulacion.</small>
            </label>
            <button class="button primary" type="submit">Subir Excel y reemplazar Núcleos</button>
          </form>
          ${importSummaryMarkup(excelImport)}
        </section>

        <section class="panel excel-nuclei-results">
          <div class="panel-head">
            <div>
              <h2>Información importada</h2>
              <p>Los datos se muestran tal como llegan en el Excel. El campo estado del archivo es el resultado académico oficial del registro.</p>
            </div>
          </div>
          ${coursesMarkup(courses)}
        </section>
      </div>`;
  }

  function importSummaryMarkup(summary) {
    if (!summary) {
      return '<div class="empty-mini nuclei-import-empty">Todavía no se ha cargado el Excel consolidado de Núcleos.</div>';
    }
    return `<div class="nuclei-import-summary">
      <div><strong>${Number(summary.students || 0)}</strong><span>Estudiantes</span></div>
      <div><strong>${Number(summary.careers || 0)}</strong><span>Carreras</span></div>
      <div><strong>${Number(summary.imported_rows || 0)}</strong><span>Registros importados</span></div>
      <div><strong>${Number(summary.courses || 0)}</strong><span>Materias / grupos</span></div>
      <div><strong>${Number(summary.duplicate_rows || 0)}</strong><span>Duplicados omitidos</span></div>
      <div class="nuclei-import-file"><strong>${esc(summary.filename || 'Excel de Núcleos')}</strong><span>Último archivo cargado</span></div>
    </div>`;
  }

  function coursesMarkup(courses) {
    if (!courses.length) {
      return '<div class="empty-mini">Suba el Excel para cargar la información de Núcleos.</div>';
    }
    const careers = unique(courses.map(course => course.career_name));
    const totalRecords = courses.reduce((sum, course) => sum + Number((course.students || []).length), 0);
    return `
      <div class="nuclei-result-bar">
        <div class="nuclei-result-count">${courses.length} materia${courses.length === 1 ? '' : 's'} / grupo${courses.length === 1 ? '' : 's'} · ${totalRecords} registros</div>
        <div class="nuclei-result-filters">
          <label>Carrera
            <select data-nuclei-career-filter>
              <option value="">Todas</option>
              ${careers.map(career => `<option value="${esc(career)}" ${normalize(career) === normalize(selectedCareer) ? 'selected' : ''}>${esc(career)}</option>`).join('')}
            </select>
          </label>
          <label>Buscar
            <input data-nuclei-search value="${esc(searchText)}" placeholder="Materia, docente o estudiante">
          </label>
        </div>
      </div>
      <div class="nuclei-course-list">
        ${courses
          .slice()
          .sort((left, right) => compareText(left.career_name, right.career_name) || Number(left.nucleus_number || 0) - Number(right.nucleus_number || 0) || compareText(left.course_title, right.course_title) || compareText(left.teacher_name, right.teacher_name))
          .map(courseMarkup)
          .join('')}
      </div>`;
  }

  function courseMarkup(course) {
    const students = course.students || [];
    const counts = statusCounts(course);
    const title = course.course_title || `Núcleo ${Number(course.nucleus_number || 0)}`;
    const detailId = `excel-nucleus-${Number(course.id)}`;
    const searchable = normalize([
      course.career_name,
      title,
      course.teacher_name,
      ...students.map(student => student.full_name),
    ].join(' '));
    return `<article class="nuclei-course-row" data-excel-nucleus-course data-career="${esc(course.career_name || '')}" data-search="${esc(searchable)}">
      <div class="nuclei-course-main">
        <div class="nuclei-course-title">
          <strong>${esc(course.career_name || 'Sin carrera')}</strong>
          <span>${esc(title)}</span>
          <small>${esc(course.teacher_name || 'Docente no registrado')}</small>
        </div>
        <div class="nuclei-course-stats">
          <span>${students.length} estudiante${students.length === 1 ? '' : 's'}</span>
          <span>Promedio ${fmt(courseAverage(course))}</span>
          <span class="nuclei-status-ok">${counts.approved} APR</span>
          ${counts.failed ? `<span class="nuclei-status-fail">${counts.failed} REP</span>` : ''}
          ${counts.pending ? `<span class="nuclei-status-pending">${counts.pending} sin evaluación</span>` : ''}
        </div>
        <button class="button secondary small" type="button" data-toggle-nuclei-course="${detailId}">Ver estudiantes</button>
      </div>
      <div class="nuclei-course-detail" id="${detailId}" hidden>
        ${studentsTable(students)}
      </div>
    </article>`;
  }

  function studentsTable(students) {
    return `<div class="student-table-wrap nuclei-student-table-wrap">
      <table class="student-table compact-table nuclei-student-table">
        <thead><tr><th>Estudiante</th><th>Nota final</th><th>Estado</th></tr></thead>
        <tbody>${students.map(student => `<tr>
          <td>${esc(student.full_name || '—')}</td>
          <td><strong>${fmt(student.final_grade)}</strong></td>
          <td>${esc(student.final_status || 'No evaluado')}</td>
        </tr>`).join('')}</tbody>
      </table>
    </div>`;
  }

  function bindDelegatedEvents(tab) {
    if (tab.dataset.nucleiDelegatedBound === '1') return;
    tab.dataset.nucleiDelegatedBound = '1';
    tab.addEventListener('click', handleTabClick);
    tab.addEventListener('change', handleTabChange);
    tab.addEventListener('input', handleTabInput);
    tab.addEventListener('submit', handleTabSubmit);
  }

  function reportIdForTab(tab) {
    return Number(tab?.dataset.nucleiReportId || state.activeReport?.id || 0);
  }

  async function handleTabSubmit(event) {
    const form = event.target.closest('#nuclei-excel-form');
    if (!form) return;
    event.preventDefault();
    const tab = event.currentTarget;
    const reportId = reportIdForTab(tab);
    if (!reportId) return;

    const file = form.elements.file?.files?.[0];
    if (!file) {
      toast('Seleccione el Excel de Núcleos.', true);
      return;
    }
    if (!/\.xlsx$/i.test(file.name)) {
      toast('El archivo debe tener extensión .xlsx.', true);
      return;
    }
    if (!confirm('Esta carga reemplazará toda la información actual del módulo Núcleos. ¿Continuar?')) return;

    const submit = form.querySelector('button[type="submit"]');
    if (submit?.disabled) return;
    if (submit) {
      submit.disabled = true;
      submit.textContent = 'Importando...';
    }

    try {
      const dataUrl = await readFileAsDataUrl(file);
      const result = await api(`/api/reports/${reportId}/nuclei/import-excel`, {
        method: 'POST',
        body: JSON.stringify({ filename: file.name, data_url: dataUrl }),
      });
      const summary = result.summary || {};
      toast(`Excel cargado: ${Number(summary.imported_rows || 0)} registros y ${Number(summary.students || 0)} estudiantes.`);
      selectedCareer = '';
      searchText = '';
      await renderNucleiModule();
    } catch (error) {
      toast(error.message, true);
      if (submit && document.contains(submit)) {
        submit.disabled = false;
        submit.textContent = 'Subir Excel y reemplazar Núcleos';
      }
    }
  }

  function handleTabClick(event) {
    const button = event.target.closest('[data-toggle-nuclei-course]');
    if (!button) return;
    const tab = event.currentTarget;
    const detail = tab.querySelector(`#${CSS.escape(button.dataset.toggleNucleiCourse)}`);
    if (!detail) return;
    detail.hidden = !detail.hidden;
    button.textContent = detail.hidden ? 'Ver estudiantes' : 'Ocultar estudiantes';
  }

  function handleTabChange(event) {
    if (!event.target.matches('[data-nuclei-career-filter]')) return;
    selectedCareer = event.target.value;
    applyFilters(event.currentTarget);
  }

  function handleTabInput(event) {
    if (!event.target.matches('[data-nuclei-search]')) return;
    searchText = event.target.value;
    applyFilters(event.currentTarget);
  }

  function applyFilters(tab) {
    const career = tab.querySelector('[data-nuclei-career-filter]')?.value || selectedCareer;
    const query = normalize(tab.querySelector('[data-nuclei-search]')?.value || searchText);
    selectedCareer = career;
    searchText = tab.querySelector('[data-nuclei-search]')?.value || searchText;
    tab.querySelectorAll('[data-excel-nucleus-course]').forEach(card => {
      const sameCareer = !career || normalize(card.dataset.career) === normalize(career);
      const matchesSearch = !query || String(card.dataset.search || '').includes(query);
      card.hidden = !(sameCareer && matchesSearch);
    });
  }

  function readFileAsDataUrl(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = () => reject(new Error('No se pudo leer el archivo seleccionado.'));
      reader.readAsDataURL(file);
    });
  }

  const style = document.createElement('style');
  style.textContent = `
    .excel-nuclei { gap: 14px; }
    .excel-nuclei-upload .panel-head p, .excel-nuclei-results .panel-head p { margin: 4px 0 0; color: #64748b; max-width: 920px; }
    .nuclei-excel-form { display: grid; grid-template-columns: minmax(280px, 1fr) auto; gap: 14px; align-items: end; margin-top: 12px; }
    .nuclei-file-field { display: grid; gap: 7px; }
    .nuclei-file-field input { min-height: 42px; }
    .nuclei-file-field small { color: #64748b; font-size: 11px; }
    .nuclei-import-empty { margin-top: 14px; }
    .nuclei-import-summary { display: grid; grid-template-columns: repeat(5, minmax(120px, 1fr)) minmax(220px, 1.4fr); gap: 9px; margin-top: 14px; }
    .nuclei-import-summary > div { padding: 11px 12px; border: 1px solid #e2e8f0; border-radius: 12px; background: #f8fafc; display: grid; gap: 2px; }
    .nuclei-import-summary strong { color: #173b57; font-size: 16px; }
    .nuclei-import-summary span { color: #64748b; font-size: 11px; }
    .nuclei-import-file strong { font-size: 12px; overflow-wrap: anywhere; }
    .nuclei-result-bar { display: grid; gap: 12px; margin: 10px 0 14px; }
    .nuclei-result-count { color: #64748b; font-size: 12px; font-weight: 700; }
    .nuclei-result-filters { display: grid; grid-template-columns: minmax(260px, .8fr) minmax(280px, 1fr); gap: 12px; }
    .nuclei-course-list { display: grid; gap: 8px; }
    .nuclei-course-row { border: 1px solid #e2e8f0; border-radius: 13px; background: white; overflow: hidden; }
    .nuclei-course-row[hidden], .nuclei-course-detail[hidden] { display: none !important; }
    .nuclei-course-main { display: grid; grid-template-columns: minmax(320px, 1.4fr) minmax(300px, 1fr) auto; gap: 14px; align-items: center; padding: 13px 15px; }
    .nuclei-course-title { display: grid; gap: 3px; }
    .nuclei-course-title strong { color: #173b57; }
    .nuclei-course-title span { color: #334155; font-size: 13px; font-weight: 700; }
    .nuclei-course-title small { color: #64748b; font-size: 12px; }
    .nuclei-course-stats { display: flex; flex-wrap: wrap; gap: 8px 12px; }
    .nuclei-course-stats span { color: #64748b; font-size: 12px; }
    .nuclei-status-ok { color: #166534 !important; font-weight: 800; }
    .nuclei-status-fail { color: #991b1b !important; font-weight: 800; }
    .nuclei-status-pending { color: #92400e !important; font-weight: 800; }
    .nuclei-course-detail { padding: 0 15px 15px; border-top: 1px solid #edf2f7; }
    .nuclei-student-table-wrap { max-height: 390px; overflow: auto; margin-top: 12px; }
    .nuclei-student-table { min-width: 640px; }
    @media (max-width: 1100px) {
      .nuclei-import-summary { grid-template-columns: repeat(3, 1fr); }
      .nuclei-course-main { grid-template-columns: 1fr; }
    }
    @media (max-width: 760px) {
      .nuclei-excel-form, .nuclei-result-filters, .nuclei-import-summary { grid-template-columns: 1fr; }
    }
  `;
  document.head.appendChild(style);
})();
