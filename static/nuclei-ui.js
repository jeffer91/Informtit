(() => {
  window.INFORMTIT_MINIMAL_NUCLEI = true;

  const previousRenderReport = renderReport;
  const PAGE_SIZE = 15;
  let currentAnalysis = null;
  let lastNuclei = { courses: [] };
  let lastEligibility = { rows: [], summary: {}, unmatched: [], grade_conflicts: [], prerequisite_conflicts: [] };
  let importOpen = false;
  let matrixOpen = false;
  let matrixCareer = '';
  let matrixQuery = '';
  let matrixPage = 1;
  let selectedCourseCareer = '';
  let selectedCourseCampus = '';

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

  function canonicalName(value = '') {
    return normalize(value).split(' ').filter(Boolean).sort().join(' ');
  }

  function compareText(left, right) {
    return String(left || '').localeCompare(String(right || ''), 'es', { sensitivity: 'base' });
  }

  function fmt(value) {
    if (value === null || value === undefined || value === '') return '—';
    const number = Number(value);
    if (!Number.isFinite(number)) return '—';
    return number.toFixed(2).replace('.', ',');
  }

  function unique(values) {
    return [...new Set(values.map(value => String(value || '').trim()).filter(Boolean))].sort(compareText);
  }

  function eligibleRows(data = lastEligibility) {
    return (data.rows || []).filter(row => row.option === 'Examen Complexivo' && row.eligible_for_nuclei);
  }

  function buildEligibleIndex(data = lastEligibility) {
    const rows = eligibleRows(data);
    const byEmail = new Map();
    const byNameCareer = new Map();
    rows.forEach(row => {
      const email = String(row.email || '').trim().toLowerCase();
      if (email) byEmail.set(email, row);
      const name = canonicalName(row.full_name);
      const career = normalize(row.career_name);
      if (name) byNameCareer.set(`${career}|${name}`, row);
    });
    return { rows, byEmail, byNameCareer };
  }

  function campusCompatible(row, course) {
    const studentCampus = normalize(row?.campus);
    const courseCampus = normalize(course?.campus);
    return !studentCampus || !courseCampus || studentCampus === courseCampus;
  }

  function eligibleRowForStudent(student, course, index) {
    const email = String(student?.email || '').trim().toLowerCase();
    if (email) {
      const row = index.byEmail.get(email);
      if (row && campusCompatible(row, course)) return row;
    }
    const key = `${normalize(course?.career_name)}|${canonicalName(student?.full_name)}`;
    const row = index.byNameCareer.get(key);
    return row && campusCompatible(row, course) ? row : null;
  }

  function visibleCourseStudents(course, data = lastEligibility) {
    const index = buildEligibleIndex(data);
    return (course.students || []).filter(student => eligibleRowForStudent(student, course, index));
  }

  function courseAverage(students) {
    const values = students
      .map(student => student.final_grade)
      .filter(value => value !== null && value !== undefined && Number.isFinite(Number(value)))
      .map(Number);
    if (!values.length) return null;
    return values.reduce((sum, value) => sum + value, 0) / values.length;
  }

  function statusClass(status = '') {
    const key = normalize(status);
    if (key.includes('habilitado para complexivo')) return 'minimal-status ok';
    if (key.includes('reprobado') || key.includes('no habilitado') || key.includes('conflicto')) return 'minimal-status fail';
    return 'minimal-status pending';
  }

  renderReport = function renderReportWithMinimalNuclei() {
    previousRenderReport();
    if (state.activeReport?.id) renderNucleiModule();
  };

  async function renderNucleiModule() {
    const tab = document.querySelector('#tab-nuclei');
    const reportId = Number(state.activeReport?.id || 0);
    if (!tab || !reportId) return;

    tab.innerHTML = '<div class="panel"><div class="empty-mini">Cargando Núcleos...</div></div>';
    currentAnalysis = null;

    try {
      const [nuclei, eligibility] = await Promise.all([
        api(`/api/reports/${reportId}/nuclei`),
        api(`/api/reports/${reportId}/nuclei/eligibility`),
      ]);
      if (Number(state.activeReport?.id || 0) !== reportId) return;
      lastNuclei = nuclei || { courses: [] };
      lastEligibility = eligibility || lastEligibility;
      normalizeSelections();
      tab.innerHTML = minimalMarkup(lastNuclei, lastEligibility);
      bindEvents(tab, reportId);
      refreshCourseFilters(tab);
      refreshMatrix(tab);
    } catch (error) {
      tab.innerHTML = `<div class="panel"><div class="empty-mini">${esc(error.message)}</div></div>`;
    }
  }

  function normalizeSelections() {
    const courses = lastNuclei.courses || [];
    const courseCareers = unique(courses.map(course => course.career_name || 'Sin carrera'));
    if (!courseCareers.some(career => normalize(career) === normalize(selectedCourseCareer))) {
      selectedCourseCareer = courseCareers[0] || '';
    }

    const rows = eligibleRows();
    const matrixCareers = unique(rows.map(row => row.career_name));
    if (!matrixCareers.some(career => normalize(career) === normalize(matrixCareer))) {
      matrixCareer = matrixCareers[0] || '';
      matrixPage = 1;
      matrixQuery = '';
    }
  }

  function minimalMarkup(nuclei, eligibility) {
    const summary = eligibility.summary || {};
    const approvedForNuclei = Number(summary.eligible_for_nuclei || 0);
    return `
      <div class="process-stack minimal-nuclei" data-minimal-nuclei>
        <section class="panel minimal-nuclei-header">
          <div class="panel-head minimal-main-head">
            <div>
              <h2>Núcleos</h2>
              <p><strong>${approvedForNuclei}</strong> estudiantes aprobaron los ocho requisitos previos y son los únicos que se muestran para cargar y revisar notas.</p>
            </div>
            <button class="button primary" type="button" data-toggle-nucleus-import>${importOpen ? 'Cerrar carga' : '+ Cargar núcleo'}</button>
          </div>
        </section>

        ${importMarkup()}

        <section class="panel minimal-courses-panel">
          <div class="panel-head">
            <div><h2>Cursos cargados</h2><p>Carrera, sede, núcleo, docente y resultado. Las notas individuales permanecen ocultas hasta abrir el curso.</p></div>
          </div>
          ${coursesMarkup(nuclei.courses || [])}
        </section>

        ${habilitationMarkup(eligibility)}
        ${issuesMarkup(eligibility)}
      </div>`;
  }

  function importMarkup() {
    return `<section class="panel minimal-import-panel" data-nucleus-import-panel ${importOpen ? '' : 'hidden'}>
      <div class="panel-head">
        <div><h2>Cargar núcleo</h2><p>Pegue calificaciones y participantes de Moodle. Informtit mostrará únicamente estudiantes habilitados por requisitos.</p></div>
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
    const campuses = unique(courses.map(course => course.campus));
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
    const students = visibleCourseStudents(course);
    const excluded = Math.max(0, Number((course.students || []).length) - students.length);
    const approved = students.filter(student => Number(student.final_grade) >= 7).length;
    const failed = students.filter(student => student.final_grade !== null && student.final_grade !== undefined && Number(student.final_grade) < 7).length;
    const average = courseAverage(students);
    const campus = String(course.campus || '').trim() || 'Sede no indicada';
    const stateText = failed ? `${failed} reprobado${failed === 1 ? '' : 's'}` : (students.length ? 'Sin reprobados' : 'Sin habilitados');
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
          <span class="${failed ? 'minimal-result-fail' : 'minimal-result-ok'}">${stateText}</span>
        </div>
        <div class="minimal-course-actions">
          <button class="button secondary small" type="button" data-toggle-course="${detailsId}">Ver</button>
          <button class="button danger small" type="button" data-delete-nucleus="${Number(course.id)}">Eliminar</button>
        </div>
      </div>
      <div class="minimal-course-detail" id="${detailsId}" hidden>
        <div class="minimal-course-meta">
          ${course.module_code ? `<span>Mod ${esc(course.module_code)}</span>` : ''}
          ${course.group_code ? `<span>${esc(course.group_code)}</span>` : ''}
          ${course.schedule ? `<span>${esc(course.schedule)}</span>` : ''}
          <span>${approved} aprobado${approved === 1 ? '' : 's'}</span>
        </div>
        ${excluded ? `<div class="minimal-inline-warning">${excluded} registro${excluded === 1 ? '' : 's'} de Moodle no se muestran porque no están habilitados para Núcleos o no coinciden con la base.</div>` : ''}
        ${students.length ? studentsTable(course, students) : '<div class="empty-mini">No hay estudiantes habilitados para mostrar en este curso.</div>'}
      </div>
    </article>`;
  }

  function studentsTable(course, students) {
    const assessments = course.assessments || [];
    return `<div class="student-table-wrap minimal-course-table-wrap">
      <table class="student-table compact-table minimal-course-table">
        <thead><tr><th>Estudiante</th><th>Correo</th>${assessments.map(name => `<th>${esc(name)}</th>`).join('')}<th>Total</th></tr></thead>
        <tbody>${students.map(student => `<tr>
          <td>${esc(student.full_name)}</td>
          <td>${esc(student.email || '—')}</td>
          ${(student.scores || []).map(score => `<td>${fmt(score.grade)}</td>`).join('')}
          <td><strong>${fmt(student.final_grade)}</strong></td>
        </tr>`).join('')}</tbody>
      </table>
    </div>`;
  }

  function habilitationMarkup(data) {
    const summary = data.summary || {};
    return `<section class="panel minimal-eligibility-panel">
      <div class="panel-head">
        <div><h2>Habilitación para Complexivo</h2><p>La matriz contiene únicamente estudiantes que aprobaron los ocho requisitos previos.</p></div>
        <button class="button secondary" type="button" data-toggle-minimal-matrix>${matrixOpen ? 'Ocultar matriz' : 'Ver matriz'}</button>
      </div>
      <div class="minimal-summary-grid">
        ${metric('Ingresaron a Núcleos', summary.eligible_for_nuclei || 0)}
        ${metric('Habilitados Complexivo', summary.eligible_for_complexive || 0)}
        ${metric('Núcleos reprobados', summary.not_habilitated || 0)}
        ${metric('Núcleos pendientes', summary.pending || 0)}
      </div>
      <div class="minimal-matrix" data-minimal-matrix ${matrixOpen ? '' : 'hidden'}>
        ${matrixControlsMarkup()}
        <div class="student-table-wrap">
          <table class="student-table compact-table minimal-matrix-table">
            <thead><tr><th>Cédula</th><th>Estudiante</th><th>Sede</th><th>N1</th><th>N2</th><th>N3</th><th>N4</th><th>Estado</th></tr></thead>
            <tbody data-minimal-matrix-body></tbody>
          </table>
        </div>
      </div>
    </section>`;
  }

  function metric(label, value) {
    return `<div class="minimal-metric"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`;
  }

  function matrixControlsMarkup() {
    const rows = eligibleRows();
    const careers = unique(rows.map(row => row.career_name));
    const selected = careers.find(career => normalize(career) === normalize(matrixCareer)) || careers[0] || '';
    matrixCareer = selected;
    return `<div class="minimal-matrix-controls">
      <label>Carrera
        <select data-minimal-matrix-career>
          ${careers.map(career => `<option value="${esc(career)}" ${normalize(career) === normalize(selected) ? 'selected' : ''}>${esc(career)}</option>`).join('')}
        </select>
      </label>
      <label>Buscar
        <input type="search" data-minimal-matrix-search value="${esc(matrixQuery)}" placeholder="Cédula o nombre" autocomplete="off">
      </label>
      <div class="minimal-page-controls">
        <button class="button secondary small" type="button" data-minimal-page-prev>←</button>
        <span data-minimal-page-counter></span>
        <button class="button secondary small" type="button" data-minimal-page-next>→</button>
      </div>
    </div>`;
  }

  function issuesMarkup(data) {
    const unmatched = data.unmatched || [];
    const gradeConflicts = data.grade_conflicts || [];
    const prerequisiteConflicts = data.prerequisite_conflicts || [];
    const total = unmatched.length + gradeConflicts.length + prerequisiteConflicts.length;
    if (!total) return '';
    return `<section class="panel minimal-issues-panel">
      <div class="minimal-alert-line">
        <div><strong>${total} novedad${total === 1 ? '' : 'es'} requieren revisión</strong><span>Solo se muestran porque existe algo que corregir.</span></div>
        <button class="button secondary small" type="button" data-toggle-minimal-issues>Revisar</button>
      </div>
      <div class="minimal-issues-detail" data-minimal-issues-detail hidden>
        ${prerequisiteConflicts.length ? prerequisiteIssues(prerequisiteConflicts) : ''}
        ${unmatched.length ? unmatchedIssues(unmatched) : ''}
        ${gradeConflicts.length ? conflictIssues(gradeConflicts, data.rows || []) : ''}
      </div>
    </section>`;
  }

  function prerequisiteIssues(rows) {
    return `<details open><summary>${rows.length} estudiante${rows.length === 1 ? '' : 's'} con nota de Núcleo sin requisitos completos</summary>
      <div class="student-table-wrap"><table class="student-table compact-table"><thead><tr><th>Estudiante</th><th>Carrera</th><th>Sede</th><th>Requisitos pendientes</th></tr></thead>
      <tbody>${rows.map(row => `<tr><td>${esc(row.full_name)}</td><td>${esc(row.career_name)}</td><td>${esc(row.campus || '—')}</td><td>${esc((row.missing_requirements || []).join(', '))}</td></tr>`).join('')}</tbody></table></div>
    </details>`;
  }

  function unmatchedIssues(rows) {
    return `<details><summary>${rows.length} calificación${rows.length === 1 ? '' : 'es'} sin coincidencia con la base</summary>
      <div class="student-table-wrap"><table class="student-table compact-table"><thead><tr><th>Estudiante</th><th>Correo</th><th>Carrera</th><th>Sede</th><th>Núcleo</th><th>Motivo</th></tr></thead>
      <tbody>${rows.map(row => `<tr><td>${esc(row.full_name)}</td><td>${esc(row.email || '—')}</td><td>${esc(row.career_name || '—')}</td><td>${esc(row.campus || '—')}</td><td>${Number(row.nucleus_number || 0)}</td><td>${esc(row.reason || 'Sin coincidencia')}</td></tr>`).join('')}</tbody></table></div>
    </details>`;
  }

  function conflictIssues(conflicts, allRows) {
    const byId = new Map(allRows.map(row => [Number(row.student_id), row]));
    return `<details><summary>${conflicts.length} conflicto${conflicts.length === 1 ? '' : 's'} de notas</summary>
      <div class="student-table-wrap"><table class="student-table compact-table"><thead><tr><th>Estudiante</th><th>Carrera</th><th>Núcleo</th><th>Notas encontradas</th></tr></thead>
      <tbody>${conflicts.map(item => {
        const row = byId.get(Number(item.student_id)) || {};
        return `<tr><td>${esc(row.full_name || '—')}</td><td>${esc(row.career_name || '—')}</td><td>${Number(item.nucleus_number || 0)}</td><td>${esc((item.grades || []).map(fmt).join(' / '))}</td></tr>`;
      }).join('')}</tbody></table></div>
    </details>`;
  }

  function bindEvents(tab, reportId) {
    tab.addEventListener('click', async event => {
      const toggleImport = event.target.closest('[data-toggle-nucleus-import]');
      if (toggleImport) {
        importOpen = !importOpen;
        const panel = tab.querySelector('[data-nucleus-import-panel]');
        if (panel) panel.hidden = !importOpen;
        toggleImport.textContent = importOpen ? 'Cerrar carga' : '+ Cargar núcleo';
        if (importOpen) panel?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        return;
      }

      if (event.target.closest('[data-cancel-nucleus-import]')) {
        importOpen = false;
        currentAnalysis = null;
        tab.querySelector('[data-nucleus-import-panel]')?.setAttribute('hidden', '');
        const toggle = tab.querySelector('[data-toggle-nucleus-import]');
        if (toggle) toggle.textContent = '+ Cargar núcleo';
        return;
      }

      const toggleCourse = event.target.closest('[data-toggle-course]');
      if (toggleCourse) {
        const detail = document.getElementById(toggleCourse.dataset.toggleCourse);
        if (detail) {
          detail.hidden = !detail.hidden;
          toggleCourse.textContent = detail.hidden ? 'Ver' : 'Ocultar';
        }
        return;
      }

      const remove = event.target.closest('[data-delete-nucleus]');
      if (remove) {
        if (!confirm('¿Eliminar este curso de Núcleos y todas sus notas?')) return;
        try {
          await api(`/api/reports/${reportId}/nuclei/${remove.dataset.deleteNucleus}`, { method: 'DELETE', body: '{}' });
          toast('Curso de Núcleos eliminado.');
          await renderNucleiModule();
        } catch (error) {
          toast(error.message, true);
        }
        return;
      }

      const save = event.target.closest('[data-save-nucleus]');
      if (save && currentAnalysis) {
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
          toast(`Núcleo ${result.analysis.nucleus_number} guardado.`);
          await renderNucleiModule();
        } catch (error) {
          toast(error.message, true);
        }
        return;
      }

      if (event.target.closest('[data-toggle-minimal-matrix]')) {
        matrixOpen = !matrixOpen;
        const matrix = tab.querySelector('[data-minimal-matrix]');
        if (matrix) matrix.hidden = !matrixOpen;
        event.target.closest('[data-toggle-minimal-matrix]').textContent = matrixOpen ? 'Ocultar matriz' : 'Ver matriz';
        if (matrixOpen) refreshMatrix(tab);
        return;
      }

      if (event.target.closest('[data-minimal-page-prev]')) {
        matrixPage = Math.max(1, matrixPage - 1);
        refreshMatrix(tab);
        return;
      }

      if (event.target.closest('[data-minimal-page-next]')) {
        matrixPage += 1;
        refreshMatrix(tab);
        return;
      }

      if (event.target.closest('[data-toggle-minimal-issues]')) {
        const detail = tab.querySelector('[data-minimal-issues-detail]');
        if (detail) {
          detail.hidden = !detail.hidden;
          event.target.closest('[data-toggle-minimal-issues]').textContent = detail.hidden ? 'Revisar' : 'Ocultar';
        }
      }
    });

    const form = tab.querySelector('#nucleus-import-form');
    form?.addEventListener('submit', async event => {
      event.preventDefault();
      const payload = {
        grades_text: form.grades_text.value,
        participants_text: form.participants_text.value,
        career_name: form.career_name.value.trim(),
        nucleus_number: form.nucleus_number.value ? Number(form.nucleus_number.value) : null,
      };
      try {
        const result = await api(`/api/reports/${reportId}/nuclei/analyze`, { method: 'POST', body: JSON.stringify(payload) });
        currentAnalysis = { ...payload, ...result.analysis };
        renderPreview(result.analysis, tab);
      } catch (error) {
        toast(error.message, true);
      }
    });

    tab.addEventListener('change', event => {
      if (event.target.matches('[data-course-career-filter]')) {
        selectedCourseCareer = event.target.value;
        selectedCourseCampus = '';
        const campus = tab.querySelector('[data-course-campus-filter]');
        if (campus) campus.value = '';
        refreshCourseFilters(tab);
      } else if (event.target.matches('[data-course-campus-filter]')) {
        selectedCourseCampus = event.target.value;
        refreshCourseFilters(tab);
      } else if (event.target.matches('[data-minimal-matrix-career]')) {
        matrixCareer = event.target.value;
        matrixQuery = '';
        matrixPage = 1;
        const search = tab.querySelector('[data-minimal-matrix-search]');
        if (search) search.value = '';
        refreshMatrix(tab);
      }
    });

    tab.addEventListener('input', event => {
      if (!event.target.matches('[data-minimal-matrix-search]')) return;
      matrixQuery = event.target.value;
      matrixPage = 1;
      refreshMatrix(tab);
    });
  }

  function renderPreview(analysis, tab) {
    const preview = tab.querySelector('#nucleus-preview');
    if (!preview) return;
    const index = buildEligibleIndex();
    const visible = (analysis.students || []).filter(student => eligibleRowForStudent(student, analysis, index));
    const excluded = Math.max(0, Number((analysis.students || []).length) - visible.length);
    const candidates = analysis.teacher_candidates || [];
    const teacherControl = analysis.teacher_name
      ? `<input name="nucleus_teacher" value="${esc(analysis.teacher_name)}">`
      : candidates.length
        ? `<select name="nucleus_teacher" required><option value="">Seleccione el docente</option>${candidates.map(name => `<option value="${esc(name)}">${esc(name)}</option>`).join('')}</select>`
        : '<input name="nucleus_teacher" placeholder="Nombre del docente">';
    const campus = analysis.campus || 'Sede no indicada';
    preview.innerHTML = `<div class="minimal-preview">
      <div class="minimal-preview-head">
        <div><strong>${esc(analysis.career_name)} · ${esc(campus)} · Núcleo ${Number(analysis.nucleus_number || 0)}</strong><span>${visible.length} estudiante${visible.length === 1 ? '' : 's'} habilitado${visible.length === 1 ? '' : 's'} para mostrar</span></div>
        <button class="button primary" type="button" data-save-nucleus>Guardar núcleo</button>
      </div>
      <label class="minimal-teacher-field">Docente${teacherControl}</label>
      ${excluded ? `<div class="minimal-inline-warning">${excluded} registro${excluded === 1 ? '' : 's'} del texto pegado no se mostrarán ni contarán para habilitación porque no cumplen requisitos o no coinciden con la base.</div>` : ''}
      ${visible.length ? studentsTable(analysis, visible) : '<div class="empty-mini">No se encontraron estudiantes habilitados para Núcleos dentro de este curso.</div>'}
    </div>`;
  }

  function refreshCourseFilters(tab) {
    const cards = [...tab.querySelectorAll('[data-minimal-course]')];
    if (!cards.length) return;
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

  function refreshMatrix(tab) {
    const matrix = tab.querySelector('[data-minimal-matrix]');
    if (!matrix || matrix.hidden) return;
    const body = matrix.querySelector('[data-minimal-matrix-body]');
    const counter = matrix.querySelector('[data-minimal-page-counter]');
    const previous = matrix.querySelector('[data-minimal-page-prev]');
    const next = matrix.querySelector('[data-minimal-page-next]');
    const careerSelect = matrix.querySelector('[data-minimal-matrix-career]');
    if (!body || !counter || !previous || !next || !careerSelect) return;

    const careers = unique(eligibleRows().map(row => row.career_name));
    const resolved = careers.find(career => normalize(career) === normalize(matrixCareer)) || careers[0] || '';
    matrixCareer = resolved;
    careerSelect.value = resolved;
    const query = normalize(matrixQuery);
    const rows = eligibleRows().filter(row =>
      normalize(row.career_name) === normalize(resolved)
      && (!query || normalize(`${row.identification} ${row.full_name}`).includes(query))
    );
    const pageCount = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
    matrixPage = Math.min(Math.max(matrixPage, 1), pageCount);
    const start = (matrixPage - 1) * PAGE_SIZE;
    const pageRows = rows.slice(start, start + PAGE_SIZE);

    body.innerHTML = pageRows.length ? pageRows.map(row => `<tr>
      <td>${esc(row.identification || '—')}</td>
      <td>${esc(row.full_name)}</td>
      <td>${esc(row.campus || '—')}</td>
      <td>${fmt(row.nucleus_1)}</td>
      <td>${fmt(row.nucleus_2)}</td>
      <td>${fmt(row.nucleus_3)}</td>
      <td>${fmt(row.nucleus_4)}</td>
      <td><span class="${statusClass(row.stage_status || row.status)}">${esc(row.stage_status || row.status)}</span></td>
    </tr>`).join('') : '<tr><td colspan="8" class="empty-mini">Sin estudiantes que coincidan.</td></tr>';

    counter.textContent = rows.length ? `${matrixPage}/${pageCount} · ${start + 1}-${Math.min(start + PAGE_SIZE, rows.length)} de ${rows.length}` : '0 estudiantes';
    previous.disabled = matrixPage <= 1 || !rows.length;
    next.disabled = matrixPage >= pageCount || !rows.length;
  }

  const style = document.createElement('style');
  style.textContent = `
    #tab-nuclei [data-eligibility-panel],
    #tab-nuclei [data-nuclei-catalog="active-careers"],
    #tab-nuclei .teacher-load-panel,
    #tab-nuclei [data-nuclei-crosscheck],
    #tab-nuclei [data-workflow-flow],
    #tab-nuclei [data-workflow-blocked] { display: none !important; }
    .minimal-nuclei { gap: 14px; }
    .minimal-main-head { align-items: center; }
    .minimal-main-head p { margin: 4px 0 0; color: #64748b; }
    .minimal-import-panel[hidden], .minimal-matrix[hidden], .minimal-course-row[hidden], .minimal-course-detail[hidden], .minimal-issues-detail[hidden] { display: none !important; }
    .minimal-import-form { display: grid; gap: 14px; }
    .minimal-paste-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
    .minimal-paste-grid textarea { min-height: 230px; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; }
    .minimal-manual-options { padding: 10px 12px; border: 1px solid #e2e8f0; border-radius: 12px; background: #f8fafc; }
    .minimal-manual-options summary { cursor: pointer; font-weight: 700; color: #475569; }
    .minimal-manual-options .form-grid { margin-top: 12px; }
    .minimal-course-filters, .minimal-matrix-controls { display: grid; grid-template-columns: minmax(220px, 1fr) minmax(180px, .7fr); gap: 12px; margin: 10px 0 14px; }
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
    .minimal-summary-grid { display: grid; grid-template-columns: repeat(4, minmax(150px, 1fr)); gap: 10px; }
    .minimal-metric { padding: 12px 14px; border: 1px solid #e2e8f0; border-radius: 12px; background: #f8fafc; }
    .minimal-metric span { display: block; color: #64748b; font-size: 12px; }
    .minimal-metric strong { display: block; margin-top: 4px; font-size: 20px; color: #173b57; }
    .minimal-matrix { margin-top: 14px; }
    .minimal-matrix-controls { grid-template-columns: minmax(240px, 1fr) minmax(260px, 1fr) auto; align-items: end; }
    .minimal-page-controls { display: flex; align-items: center; gap: 8px; min-height: 42px; }
    .minimal-page-controls span { min-width: 120px; text-align: center; color: #64748b; font-size: 12px; font-weight: 700; }
    .minimal-matrix-table { min-width: 900px; }
    .minimal-status { display: inline-flex; padding: 4px 8px; border-radius: 999px; font-size: 11px; font-weight: 800; white-space: nowrap; }
    .minimal-status.ok { background: #dcfce7; color: #166534; }
    .minimal-status.fail { background: #fee2e2; color: #991b1b; }
    .minimal-status.pending { background: #fef3c7; color: #92400e; }
    .minimal-inline-warning { margin: 10px 0; padding: 10px 12px; border-radius: 10px; background: #fff7ed; color: #9a4b0b; font-size: 12px; }
    .minimal-preview { margin-top: 16px; padding: 14px; border: 1px solid #cbd5e1; border-radius: 13px; background: #f8fafc; }
    .minimal-preview-head { display: flex; justify-content: space-between; align-items: center; gap: 14px; }
    .minimal-preview-head > div { display: grid; gap: 3px; }
    .minimal-preview-head span { color: #64748b; font-size: 12px; }
    .minimal-teacher-field { display: block; max-width: 520px; margin: 12px 0; }
    .minimal-alert-line { display: flex; justify-content: space-between; gap: 18px; align-items: center; padding: 2px; }
    .minimal-alert-line > div { display: grid; gap: 3px; }
    .minimal-alert-line strong { color: #9a3412; }
    .minimal-alert-line span { color: #64748b; font-size: 12px; }
    .minimal-issues-panel { border-left: 4px solid #f59e0b; }
    .minimal-issues-detail { margin-top: 14px; display: grid; gap: 10px; }
    .minimal-issues-detail details { padding: 10px 12px; border: 1px solid #e2e8f0; border-radius: 10px; }
    .minimal-issues-detail summary { cursor: pointer; font-weight: 700; }
    @media (max-width: 1000px) {
      .minimal-course-main { grid-template-columns: 1fr; }
      .minimal-course-actions { justify-content: flex-start; }
      .minimal-summary-grid { grid-template-columns: repeat(2, 1fr); }
      .minimal-paste-grid, .minimal-course-filters, .minimal-matrix-controls { grid-template-columns: 1fr; }
    }
    @media (max-width: 620px) {
      .minimal-summary-grid { grid-template-columns: 1fr; }
      .minimal-preview-head, .minimal-alert-line { align-items: stretch; flex-direction: column; }
    }
  `;
  document.head.appendChild(style);
})();
