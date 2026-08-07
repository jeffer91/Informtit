(() => {
  window.INFORMTIT_MINIMAL_NUCLEI = true;

  const previousRenderReport = renderReport;
  let currentAnalysis = null;
  let importOpen = false;
  let selectedCourseCareer = '';
  let selectedCourseCampus = '';
  let activeNucleiReportId = 0;

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

  function assessmentName(value) {
    if (typeof value === 'string') return value;
    return value?.name || value?.assessment_name || 'Actividad';
  }

  function courseAverage(students) {
    const values = (students || [])
      .map(student => student.final_grade)
      .filter(value => value !== null && value !== undefined && Number.isFinite(Number(value)))
      .map(Number);
    if (!values.length) return null;
    return values.reduce((sum, value) => sum + value, 0) / values.length;
  }

  renderReport = function renderReportWithIndependentNuclei() {
    previousRenderReport();
    if (state.activeReport?.id) renderNucleiModule();
  };

  async function renderNucleiModule() {
    const tab = document.querySelector('#tab-nuclei');
    const reportId = Number(state.activeReport?.id || 0);
    if (!tab || !reportId) return;

    if (activeNucleiReportId !== reportId) {
      activeNucleiReportId = reportId;
      importOpen = false;
      currentAnalysis = null;
      selectedCourseCareer = '';
      selectedCourseCampus = '';
    }

    tab.dataset.nucleiReportId = String(reportId);
    bindDelegatedEvents(tab);
    tab.innerHTML = '<div class="panel"><div class="empty-mini">Cargando Núcleos...</div></div>';
    currentAnalysis = null;

    try {
      const nuclei = await api(`/api/reports/${reportId}/nuclei`);
      if (Number(state.activeReport?.id || 0) !== reportId) return;
      const courses = nuclei?.courses || [];
      normalizeSelections(courses);
      tab.innerHTML = minimalMarkup(courses);
      tab.dataset.nucleiReportId = String(reportId);
      bindImportForm(tab);
      refreshCourseFilters(tab);
    } catch (error) {
      tab.innerHTML = `<div class="panel"><div class="empty-mini">${esc(error.message)}</div></div>`;
    }
  }

  function normalizeSelections(courses) {
    const careers = unique(courses.map(course => course.career_name || 'Sin carrera'));
    if (!careers.some(career => normalize(career) === normalize(selectedCourseCareer))) {
      selectedCourseCareer = careers[0] || '';
      selectedCourseCampus = '';
    }
  }

  function minimalMarkup(courses) {
    const totalStudents = courses.reduce((sum, course) => sum + Number((course.students || []).length), 0);
    return `
      <div class="process-stack minimal-nuclei" data-minimal-nuclei>
        <section class="panel minimal-nuclei-header">
          <div class="panel-head minimal-main-head">
            <div>
              <h2>Núcleos</h2>
              <p>Módulo independiente. Registra únicamente la información cargada desde Moodle; no se compara ni se condiciona por Requisitos, Examen Complexivo o Trabajo de Titulación.</p>
            </div>
            <button class="button primary" type="button" data-toggle-nucleus-import aria-expanded="${importOpen ? 'true' : 'false'}">${importOpen ? 'Cerrar carga' : '+ Cargar núcleo'}</button>
          </div>
          ${courses.length ? `<div class="minimal-module-summary"><span>${courses.length} curso${courses.length === 1 ? '' : 's'} cargado${courses.length === 1 ? '' : 's'}</span><span>${totalStudents} registro${totalStudents === 1 ? '' : 's'} de estudiante en total</span></div>` : ''}
        </section>

        ${importMarkup()}

        <section class="panel minimal-courses-panel">
          <div class="panel-head">
            <div><h2>Cursos cargados</h2><p>Cada curso conserva sus propios participantes, notas, docente y sede. Las notas se muestran solo al abrir el curso.</p></div>
          </div>
          ${coursesMarkup(courses)}
        </section>
      </div>`;
  }

  function importMarkup() {
    return `<section class="panel minimal-import-panel" data-nucleus-import-panel ${importOpen ? '' : 'hidden'}>
      <div class="panel-head">
        <div><h2>Cargar núcleo</h2><p>Pegue las calificaciones y los participantes del curso Moodle. Todos los estudiantes detectados en esta carga se registran dentro de este módulo.</p></div>
      </div>
      <form id="nucleus-import-form" class="minimal-import-form">
        <div class="minimal-paste-grid">
          <label>Calificaciones Moodle
            <textarea name="grades_text" rows="12" required placeholder="Pegue aquí el libro de calificaciones del núcleo."></textarea>
          </label>
          <label>Participantes Moodle
            <textarea name="participants_text" rows="12" placeholder="Pegue aquí la lista de participantes para detectar al docente."></textarea>
          </label>
        </div>
        <details class="minimal-manual-options">
          <summary>Opciones manuales</summary>
          <div class="form-grid">
            <label>Carrera, solo si no se detecta
              <input name="career_name" placeholder="Ej.: Enfermería">
            </label>
            <label>Número de núcleo, solo si no se detecta
              <input name="nucleus_number" type="number" min="1" max="20" placeholder="1">
            </label>
          </div>
        </details>
        <div class="form-actions">
          <button class="button primary" type="submit">Analizar</button>
          <button class="button secondary" type="button" data-cancel-nucleus-import>Cancelar</button>
        </div>
      </form>
      <div id="nucleus-preview"></div>
    </section>`;
  }

  function coursesMarkup(courses) {
    if (!courses.length) return '<div class="empty-mini">Todavía no existen cursos de Núcleos cargados.</div>';
    const careers = unique(courses.map(course => course.career_name || 'Sin carrera'));
    const campuses = unique(
      courses
        .filter(course => !selectedCourseCareer || normalize(course.career_name || 'Sin carrera') === normalize(selectedCourseCareer))
        .map(course => course.campus)
    );
    return `
      <div class="minimal-course-filters">
        <label>Carrera
          <select data-course-career-filter>
            ${careers.map(career => `<option value="${esc(career)}" ${normalize(career) === normalize(selectedCourseCareer) ? 'selected' : ''}>${esc(career)}</option>`).join('')}
          </select>
        </label>
        <label>Sede
          <select data-course-campus-filter>
            <option value="">Todas</option>
            ${campuses.map(campus => `<option value="${esc(campus)}" ${normalize(campus) === normalize(selectedCourseCampus) ? 'selected' : ''}>${esc(campus)}</option>`).join('')}
          </select>
        </label>
      </div>
      <div class="minimal-course-list">
        ${courses
          .slice()
          .sort((left, right) => compareText(left.career_name, right.career_name) || compareText(left.campus, right.campus) || Number(left.nucleus_number) - Number(right.nucleus_number))
          .map(courseRowMarkup)
          .join('')}
      </div>`;
  }

  function courseRowMarkup(course) {
    const students = course.students || [];
    const graded = students.filter(student => student.final_grade !== null && student.final_grade !== undefined && Number.isFinite(Number(student.final_grade)));
    const approved = graded.filter(student => Number(student.final_grade) >= 7).length;
    const failed = graded.filter(student => Number(student.final_grade) < 7).length;
    const pending = students.length - graded.length;
    const average = courseAverage(students);
    const campus = String(course.campus || '').trim() || 'Sede no indicada';
    const stateText = pending
      ? `${pending} sin nota`
      : failed
        ? `${failed} reprobado${failed === 1 ? '' : 's'}`
        : students.length
          ? 'Sin reprobados'
          : 'Sin estudiantes';
    const detailsId = `minimal-course-${Number(course.id)}`;
    return `<article class="minimal-course-row" data-minimal-course data-career="${esc(course.career_name || 'Sin carrera')}" data-campus="${esc(course.campus || '')}">
      <div class="minimal-course-main">
        <div class="minimal-course-title">
          <strong>${esc(course.career_name || 'Sin carrera')} · ${esc(campus)}</strong>
          <span>Núcleo ${Number(course.nucleus_number || 0)} · ${esc(course.teacher_name || 'Docente pendiente')}</span>
        </div>
        <div class="minimal-course-stats">
          <span>${students.length} estudiante${students.length === 1 ? '' : 's'}</span>
          <span>Promedio ${fmt(average)}</span>
          <span class="${failed || pending ? 'minimal-result-fail' : 'minimal-result-ok'}">${stateText}</span>
        </div>
        <div class="minimal-course-actions">
          <button class="button secondary small" type="button" data-toggle-course="${detailsId}">Ver</button>
          <button class="button danger small" type="button" data-delete-nucleus="${Number(course.id)}">Eliminar</button>
        </div>
      </div>
      <div class="minimal-course-detail" id="${detailsId}" hidden>
        <div class="minimal-course-meta">
          ${course.module_code ? `<span>Mod ${esc(course.module_code)}</span>` : ''}
          ${course.period_label ? `<span>${esc(course.period_label)}</span>` : ''}
          ${course.group_code ? `<span>${esc(course.group_code)}</span>` : ''}
          ${course.schedule ? `<span>${esc(course.schedule)}</span>` : ''}
          <span>${approved} aprobado${approved === 1 ? '' : 's'}</span>
          ${failed ? `<span>${failed} reprobado${failed === 1 ? '' : 's'}</span>` : ''}
        </div>
        ${students.length ? studentsTable(course, students) : '<div class="empty-mini">Este curso no contiene estudiantes registrados.</div>'}
      </div>
    </article>`;
  }

  function studentsTable(course, students) {
    const assessments = course.assessments || [];
    return `<div class="student-table-wrap minimal-course-table-wrap">
      <table class="student-table compact-table minimal-course-table">
        <thead><tr><th>Estudiante</th><th>Correo</th>${assessments.map(item => `<th>${esc(assessmentName(item))}</th>`).join('')}<th>Total</th><th>Estado</th></tr></thead>
        <tbody>${students.map(student => `<tr>
          <td>${esc(student.full_name)}</td>
          <td>${esc(student.email || '—')}</td>
          ${(student.scores || []).map(score => `<td>${fmt(score.grade)}</td>`).join('')}
          <td><strong>${fmt(student.final_grade)}</strong></td>
          <td>${esc(student.final_status || (student.final_grade == null ? 'Sin nota' : Number(student.final_grade) >= 7 ? 'Aprobado' : 'Reprobado'))}</td>
        </tr>`).join('')}</tbody>
      </table>
    </div>`;
  }

  function reportIdForTab(tab) {
    return Number(tab?.dataset.nucleiReportId || state.activeReport?.id || 0);
  }

  function setImportState(tab, open) {
    importOpen = Boolean(open);
    if (!importOpen) currentAnalysis = null;
    const panel = tab.querySelector('[data-nucleus-import-panel]');
    const toggle = tab.querySelector('[data-toggle-nucleus-import]');
    if (panel) {
      panel.hidden = !importOpen;
      if (importOpen) panel.removeAttribute('hidden');
      else panel.setAttribute('hidden', '');
    }
    if (toggle) {
      toggle.textContent = importOpen ? 'Cerrar carga' : '+ Cargar núcleo';
      toggle.setAttribute('aria-expanded', importOpen ? 'true' : 'false');
    }
    if (importOpen && panel) {
      requestAnimationFrame(() => {
        panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
        panel.querySelector('textarea[name="grades_text"]')?.focus({ preventScroll: true });
      });
    }
  }

  function bindDelegatedEvents(tab) {
    if (tab.dataset.nucleiDelegatedBound === '1') return;
    tab.dataset.nucleiDelegatedBound = '1';
    tab.addEventListener('click', handleTabClick);
    tab.addEventListener('change', handleTabChange);
  }

  async function handleTabClick(event) {
    const tab = event.currentTarget;
    const reportId = reportIdForTab(tab);
    if (!reportId) return;

    const toggleImport = event.target.closest('[data-toggle-nucleus-import]');
    if (toggleImport) {
      event.preventDefault();
      setImportState(tab, !importOpen);
      return;
    }

    if (event.target.closest('[data-cancel-nucleus-import]')) {
      event.preventDefault();
      setImportState(tab, false);
      return;
    }

    const toggleCourse = event.target.closest('[data-toggle-course]');
    if (toggleCourse) {
      const detail = tab.querySelector(`#${CSS.escape(toggleCourse.dataset.toggleCourse)}`);
      if (detail) {
        detail.hidden = !detail.hidden;
        toggleCourse.textContent = detail.hidden ? 'Ver' : 'Ocultar';
      }
      return;
    }

    const remove = event.target.closest('[data-delete-nucleus]');
    if (remove) {
      if (remove.disabled || !confirm('¿Eliminar este curso de Núcleos y todas sus notas?')) return;
      remove.disabled = true;
      try {
        await api(`/api/reports/${reportId}/nuclei/${remove.dataset.deleteNucleus}`, { method: 'DELETE', body: '{}' });
        toast('Curso de Núcleos eliminado.');
        await renderNucleiModule();
      } catch (error) {
        toast(error.message, true);
        if (document.contains(remove)) remove.disabled = false;
      }
      return;
    }

    const save = event.target.closest('[data-save-nucleus]');
    if (save) {
      if (save.disabled || !currentAnalysis) return;
      save.disabled = true;
      const teacher = tab.querySelector('[name="nucleus_teacher"]')?.value || currentAnalysis.teacher_name || '';
      try {
        const result = await api(`/api/reports/${reportId}/nuclei`, {
          method: 'POST',
          body: JSON.stringify({
            grades_text: currentAnalysis.grades_text,
            participants_text: currentAnalysis.participants_text,
            career_name: currentAnalysis.career_name,
            nucleus_number: currentAnalysis.nucleus_number,
            teacher_name: teacher,
          }),
        });
        selectedCourseCareer = result.analysis.career_name || selectedCourseCareer;
        selectedCourseCampus = result.analysis.campus || selectedCourseCampus;
        importOpen = false;
        currentAnalysis = null;
        toast(`Núcleo ${result.analysis.nucleus_number} guardado con ${result.analysis.students?.length || 0} estudiantes.`);
        await renderNucleiModule();
      } catch (error) {
        toast(error.message, true);
        if (document.contains(save)) save.disabled = false;
      }
    }
  }

  function handleTabChange(event) {
    const tab = event.currentTarget;
    if (event.target.matches('[data-course-career-filter]')) {
      selectedCourseCareer = event.target.value;
      selectedCourseCampus = '';
      rebuildCampusOptions(tab);
      refreshCourseFilters(tab);
    } else if (event.target.matches('[data-course-campus-filter]')) {
      selectedCourseCampus = event.target.value;
      refreshCourseFilters(tab);
    }
  }

  function bindImportForm(tab) {
    const form = tab.querySelector('#nucleus-import-form');
    if (!form || form.dataset.nucleiSubmitBound === '1') return;
    form.dataset.nucleiSubmitBound = '1';
    form.addEventListener('submit', async event => {
      event.preventDefault();
      const reportId = reportIdForTab(tab);
      if (!reportId) return;
      const submit = form.querySelector('button[type="submit"]');
      if (submit?.disabled) return;
      if (submit) submit.disabled = true;
      const payload = {
        grades_text: form.elements.grades_text.value,
        participants_text: form.elements.participants_text.value,
        career_name: form.elements.career_name.value.trim(),
        nucleus_number: form.elements.nucleus_number.value ? Number(form.elements.nucleus_number.value) : null,
      };
      try {
        const result = await api(`/api/reports/${reportId}/nuclei/analyze`, { method: 'POST', body: JSON.stringify(payload) });
        if (reportIdForTab(tab) !== reportId) return;
        currentAnalysis = { ...payload, ...result.analysis };
        renderPreview(result.analysis, tab);
      } catch (error) {
        toast(error.message, true);
      } finally {
        if (submit && document.contains(submit)) submit.disabled = false;
      }
    });
  }

  function renderPreview(analysis, tab) {
    const preview = tab.querySelector('#nucleus-preview');
    if (!preview) return;
    const students = analysis.students || [];
    const candidates = analysis.teacher_candidates || [];
    const teacherControl = analysis.teacher_name
      ? `<input name="nucleus_teacher" value="${esc(analysis.teacher_name)}">`
      : candidates.length
        ? `<select name="nucleus_teacher" required><option value="">Seleccione el docente</option>${candidates.map(name => `<option value="${esc(name)}">${esc(name)}</option>`).join('')}</select>`
        : '<input name="nucleus_teacher" placeholder="Nombre del docente">';
    const campus = analysis.campus || 'Sede no indicada';
    preview.innerHTML = `<div class="minimal-preview">
      <div class="minimal-preview-head">
        <div><strong>${esc(analysis.career_name)} · ${esc(campus)} · Núcleo ${Number(analysis.nucleus_number || 0)}</strong><span>${students.length} estudiante${students.length === 1 ? '' : 's'} detectado${students.length === 1 ? '' : 's'}; todos se guardarán en este módulo.</span></div>
        <button class="button primary" type="button" data-save-nucleus>Guardar núcleo</button>
      </div>
      <label class="minimal-teacher-field">Docente${teacherControl}</label>
      ${students.length ? studentsTable(analysis, students) : '<div class="empty-mini">No se detectaron estudiantes en las calificaciones pegadas.</div>'}
    </div>`;
  }

  function rebuildCampusOptions(tab) {
    const career = tab.querySelector('[data-course-career-filter]')?.value || selectedCourseCareer;
    const campusSelect = tab.querySelector('[data-course-campus-filter]');
    if (!campusSelect) return;
    const campuses = unique(
      [...tab.querySelectorAll('[data-minimal-course]')]
        .filter(card => !career || normalize(card.dataset.career) === normalize(career))
        .map(card => card.dataset.campus)
    );
    campusSelect.innerHTML = '<option value="">Todas</option>' + campuses.map(campus => `<option value="${esc(campus)}">${esc(campus)}</option>`).join('');
    campusSelect.value = '';
    selectedCourseCampus = '';
  }

  function refreshCourseFilters(tab) {
    const cards = [...tab.querySelectorAll('[data-minimal-course]')];
    const careerFilter = tab.querySelector('[data-course-career-filter]');
    const campusFilter = tab.querySelector('[data-course-campus-filter]');
    const career = careerFilter?.value || selectedCourseCareer;
    const campus = campusFilter?.value || selectedCourseCampus;
    selectedCourseCareer = career;
    selectedCourseCampus = campus;
    cards.forEach(card => {
      const sameCareer = !career || normalize(card.dataset.career) === normalize(career);
      const sameCampus = !campus || normalize(card.dataset.campus) === normalize(campus);
      card.hidden = !(sameCareer && sameCampus);
    });
  }

  const style = document.createElement('style');
  style.textContent = `
    .minimal-nuclei { gap: 14px; }
    .minimal-main-head { align-items: center; }
    .minimal-main-head p { margin: 4px 0 0; color: #64748b; max-width: 900px; }
    .minimal-module-summary { display: flex; gap: 18px; flex-wrap: wrap; margin-top: 8px; color: #64748b; font-size: 12px; font-weight: 700; }
    .minimal-import-panel[hidden], .minimal-course-row[hidden], .minimal-course-detail[hidden] { display: none !important; }
    .minimal-import-form { display: grid; gap: 14px; }
    .minimal-paste-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
    .minimal-paste-grid textarea { min-height: 230px; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; }
    .minimal-manual-options { padding: 10px 12px; border: 1px solid #e2e8f0; border-radius: 12px; background: #f8fafc; }
    .minimal-manual-options summary { cursor: pointer; font-weight: 700; color: #475569; }
    .minimal-manual-options .form-grid { margin-top: 12px; }
    .minimal-course-filters { display: grid; grid-template-columns: minmax(220px, 1fr) minmax(180px, .7fr); gap: 12px; margin: 10px 0 14px; }
    .minimal-course-list { display: grid; gap: 8px; }
    .minimal-course-row { border: 1px solid #e2e8f0; border-radius: 13px; background: white; overflow: hidden; }
    .minimal-course-main { display: grid; grid-template-columns: minmax(260px, 1.5fr) minmax(280px, 1fr) auto; gap: 16px; align-items: center; padding: 13px 15px; }
    .minimal-course-title { display: grid; gap: 3px; }
    .minimal-course-title strong { color: #173b57; }
    .minimal-course-title span, .minimal-course-stats span { color: #64748b; font-size: 13px; }
    .minimal-course-stats { display: flex; gap: 12px; flex-wrap: wrap; }
    .minimal-result-ok { color: #166534 !important; font-weight: 700; }
    .minimal-result-fail { color: #991b1b !important; font-weight: 700; }
    .minimal-course-actions { display: flex; gap: 7px; }
    .minimal-course-detail { padding: 0 15px 15px; border-top: 1px solid #edf2f7; }
    .minimal-course-meta { display: flex; flex-wrap: wrap; gap: 7px; padding: 12px 0; }
    .minimal-course-meta span { padding: 4px 8px; border-radius: 999px; background: #f1f5f9; color: #475569; font-size: 11px; font-weight: 700; }
    .minimal-course-table-wrap { max-height: 420px; overflow: auto; }
    .minimal-course-table { min-width: 900px; }
    .minimal-preview { margin-top: 16px; padding: 14px; border: 1px solid #cbd5e1; border-radius: 13px; background: #f8fafc; }
    .minimal-preview-head { display: flex; justify-content: space-between; align-items: center; gap: 14px; }
    .minimal-preview-head > div { display: grid; gap: 3px; }
    .minimal-preview-head span { color: #64748b; font-size: 12px; }
    .minimal-teacher-field { display: block; max-width: 520px; margin: 12px 0; }
    @media (max-width: 1000px) {
      .minimal-course-main { grid-template-columns: 1fr; }
      .minimal-course-actions { justify-content: flex-start; }
      .minimal-paste-grid, .minimal-course-filters { grid-template-columns: 1fr; }
    }
    @media (max-width: 620px) {
      .minimal-preview-head { align-items: stretch; flex-direction: column; }
    }
  `;
  document.head.appendChild(style);
})();