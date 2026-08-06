(() => {
  const previousRenderReport = renderReport;
  let currentAnalysis = null;
  let selectedSavedCareer = '';

  function esc(value = '') {
    return typeof escapeHtml === 'function' ? escapeHtml(String(value)) : String(value);
  }

  function fmt(value) {
    if (value === null || value === undefined || value === '') return '—';
    return Number(value).toFixed(2).replace('.', ',');
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

  renderReport = function renderReportWithNuclei() {
    previousRenderReport();
    if (state.activeReport) renderNucleiModule();
  };

  async function renderNucleiModule() {
    const tab = document.querySelector('#tab-nuclei');
    if (!tab || !state.activeReport?.id) return;
    currentAnalysis = null;
    tab.innerHTML = '<div class="panel"><div class="empty-mini">Cargando núcleos estructurantes...</div></div>';
    try {
      const data = await api(`/api/reports/${state.activeReport.id}/nuclei`);
      const courses = [...(data.courses || [])].sort((left, right) =>
        compareText(left.career_name, right.career_name)
        || Number(left.nucleus_number || 0) - Number(right.nucleus_number || 0)
      );
      tab.innerHTML = `
        <div class="process-stack">
          <section class="panel">
            <div class="panel-head">
              <div>
                <h2>Notas de núcleos estructurantes</h2>
                <p>Pegue por separado las calificaciones de Moodle y los participantes del curso. Informtit identificará la carrera, el núcleo, el docente y el coordinador.</p>
              </div>
            </div>
            <div class="nuclei-rule-note">
              <strong>Asignación docente:</strong> un mismo profesor puede impartir uno o varios núcleos. Cada curso se guarda de manera independiente por carrera y número de núcleo.
            </div>
            <form id="nucleus-import-form" class="nucleus-import-form">
              <div class="form-grid">
                <label>Carrera, solo si no aparece claramente en el título
                  <input name="career_name" placeholder="Ej.: Enfermería">
                </label>
                <label>Número de núcleo, solo si no aparece en el título
                  <input name="nucleus_number" type="number" min="1" max="20" placeholder="1">
                </label>
              </div>
              <label>Calificaciones del núcleo
                <textarea name="grades_text" rows="16" required placeholder="Pegue aquí el título del curso, estudiantes, actividades y Total del curso."></textarea>
              </label>
              <label>Participantes del curso
                <textarea name="participants_text" rows="12" placeholder="Pegue aquí Nombre, correo, Rol, Grupos, Último acceso y Estatus. Esta lista permite identificar al docente."></textarea>
              </label>
              <div class="form-actions">
                <button class="button primary" type="submit">Analizar información</button>
              </div>
            </form>
            <div id="nucleus-preview"></div>
          </section>
          <section class="panel">
            <div class="panel-head">
              <div><h2>Núcleos guardados</h2><p>Los cursos se organizan por carrera y se incorporarán al informe antes de los resultados del Examen Complexivo.</p></div>
            </div>
            ${savedCoursesMarkup(courses)}
          </section>
        </div>`;
      bindNucleiEvents(tab);
      bindSavedCareerBrowser(tab, courses);
    } catch (error) {
      tab.innerHTML = `<div class="panel"><div class="empty-mini">${esc(error.message)}</div></div>`;
    }
  }

  function bindNucleiEvents(tab) {
    const form = tab.querySelector('#nucleus-import-form');
    form?.addEventListener('submit', async event => {
      event.preventDefault();
      const payload = formPayload(form);
      try {
        const result = await api(`/api/reports/${state.activeReport.id}/nuclei/analyze`, {
          method: 'POST',
          body: JSON.stringify(payload),
        });
        currentAnalysis = { ...payload, ...result.analysis };
        renderPreview(result.analysis);
      } catch (error) {
        toast(error.message, true);
      }
    });

    tab.addEventListener('click', async event => {
      const save = event.target.closest('[data-save-nucleus]');
      if (save && currentAnalysis) {
        const teacher = document.querySelector('[name="nucleus_teacher"]')?.value || currentAnalysis.teacher_name || '';
        try {
          const result = await api(`/api/reports/${state.activeReport.id}/nuclei`, {
            method: 'POST',
            body: JSON.stringify({
              grades_text: currentAnalysis.grades_text,
              participants_text: currentAnalysis.participants_text,
              career_name: currentAnalysis.career_name,
              nucleus_number: currentAnalysis.nucleus_number,
              teacher_name: teacher,
            }),
          });
          selectedSavedCareer = result.analysis.career_name;
          toast(`Núcleo ${result.analysis.nucleus_number} de ${result.analysis.career_name} guardado.`);
          await renderNucleiModule();
        } catch (error) {
          toast(error.message, true);
        }
        return;
      }

      const remove = event.target.closest('[data-delete-nucleus]');
      if (remove) {
        if (!confirm('¿Eliminar este curso de núcleo y todas sus notas?')) return;
        try {
          await api(`/api/reports/${state.activeReport.id}/nuclei/${remove.dataset.deleteNucleus}`, {
            method: 'DELETE',
            body: '{}',
          });
          toast('Curso de núcleo eliminado.');
          await renderNucleiModule();
        } catch (error) {
          toast(error.message, true);
        }
      }
    });
  }

  function formPayload(form) {
    return {
      career_name: form.career_name.value.trim(),
      nucleus_number: form.nucleus_number.value ? Number(form.nucleus_number.value) : null,
      grades_text: form.grades_text.value,
      participants_text: form.participants_text.value,
    };
  }

  function renderPreview(analysis) {
    const preview = document.querySelector('#nucleus-preview');
    if (!preview) return;
    const candidates = analysis.teacher_candidates || [];
    const teacherControl = analysis.teacher_name
      ? `<input name="nucleus_teacher" value="${esc(analysis.teacher_name)}">`
      : candidates.length
        ? `<select name="nucleus_teacher" required><option value="">Seleccione el docente</option>${candidates.map(name => `<option value="${esc(name)}">${esc(name)}</option>`).join('')}</select>`
        : '<input name="nucleus_teacher" placeholder="Escriba el nombre del docente">';

    preview.innerHTML = `
      <section class="nucleus-preview-card">
        <div class="panel-head">
          <div>
            <span class="badge">Núcleo ${analysis.nucleus_number}</span>
            <h3>${esc(analysis.career_name)}</h3>
            <p>${esc(analysis.course_title)}</p>
          </div>
          <button class="button primary" type="button" data-save-nucleus>Guardar núcleo</button>
        </div>
        <div class="form-grid nucleus-responsibles">
          <label>Docente detectado${teacherControl}<small>Puede ser el mismo docente registrado en otros núcleos.</small></label>
          <label>Coordinador<input value="${esc(analysis.coordinator?.coordinator || '')}" readonly></label>
        </div>
        <div class="summary-grid">
          ${summaryItem('Participantes estudiantes', analysis.participant_students)}
          ${summaryItem('Con calificación', analysis.graded_students)}
          ${summaryItem('Coincidencias', analysis.matched_students)}
          ${summaryItem('Sin calificación', analysis.missing_grades)}
          ${summaryItem('Aprobados', analysis.approved_count)}
          ${summaryItem('Reprobados', analysis.failed_count)}
          ${summaryItem('Promedio', fmt(analysis.calculated_course_average))}
        </div>
        ${studentsTable(analysis)}
      </section>`;
  }

  function summaryItem(label, value) {
    return `<div class="summary-item"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`;
  }

  function studentsTable(course) {
    return `<div class="student-table-wrap">
      <table class="student-table compact-table nucleus-score-table">
        <thead><tr><th>Estudiante</th><th>Correo</th>${course.assessments.map(name => `<th>${esc(name)}</th>`).join('')}<th>Total</th><th>Estado</th></tr></thead>
        <tbody>${course.students.map(student => `<tr>
          <td>${esc(student.full_name)}</td><td>${esc(student.email)}</td>
          ${student.scores.map(score => `<td>${fmt(score.grade)}</td>`).join('')}
          <td><strong>${fmt(student.final_grade)}</strong></td><td>${esc(student.final_status)}</td>
        </tr>`).join('')}</tbody>
      </table>
    </div>`;
  }

  function teacherLoadMarkup(courses) {
    const grouped = new Map();
    courses.forEach(course => {
      const teacher = String(course.teacher_name || '').trim();
      if (!teacher) return;
      const key = normalize(teacher);
      if (!grouped.has(key)) grouped.set(key, { teacher, assignments: [] });
      grouped.get(key).assignments.push(course);
    });
    const teachers = [...grouped.values()].sort((left, right) => compareText(left.teacher, right.teacher));
    if (!teachers.length) return '';
    return `<div class="teacher-load-panel">
      <div class="teacher-load-head">
        <div><h3>Carga docente de núcleos</h3><p>Un docente puede aparecer en varios núcleos, incluso dentro de la misma carrera.</p></div>
        <span class="badge">${teachers.length} docente${teachers.length === 1 ? '' : 's'}</span>
      </div>
      <div class="teacher-load-grid">${teachers.map(item => `
        <article class="teacher-load-card">
          <strong>${esc(item.teacher)}</strong>
          <span>${item.assignments.length} núcleo${item.assignments.length === 1 ? '' : 's'} asignado${item.assignments.length === 1 ? '' : 's'}</span>
          <div class="teacher-assignment-list">${item.assignments
            .sort((left, right) => compareText(left.career_name, right.career_name) || Number(left.nucleus_number) - Number(right.nucleus_number))
            .map(course => `<span>${esc(course.career_name)} · Núcleo ${course.nucleus_number}</span>`)
            .join('')}</div>
        </article>`).join('')}</div>
    </div>`;
  }

  function savedCoursesMarkup(courses) {
    if (!courses.length) return '<div class="empty-mini">Todavía no se han cargado notas de núcleos.</div>';
    const careers = [...new Set(courses.map(course => course.career_name))].sort(compareText);
    if (!careers.some(career => normalize(career) === normalize(selectedSavedCareer))) {
      selectedSavedCareer = careers[0];
    }
    return `${teacherLoadMarkup(courses)}
      <div class="nuclei-career-browser" data-saved-career-browser>
        <div class="career-browser-toolbar">
          <button class="button secondary small" type="button" data-saved-career-prev aria-label="Carrera anterior">← Anterior</button>
          <label>Vista por carrera
            <select data-saved-career-select>${careers.map(career => `<option value="${esc(career)}" ${normalize(career) === normalize(selectedSavedCareer) ? 'selected' : ''}>${esc(career)}</option>`).join('')}</select>
          </label>
          <button class="button secondary small" type="button" data-saved-career-next aria-label="Carrera siguiente">Siguiente →</button>
          <span class="career-browser-counter" data-saved-career-counter></span>
        </div>
        <div class="nucleus-list">${courses.map(courseCard).join('')}</div>
      </div>`;
  }

  function bindSavedCareerBrowser(tab, courses) {
    const browser = tab.querySelector('[data-saved-career-browser]');
    if (!browser) return;
    const careers = [...new Set(courses.map(course => course.career_name))].sort(compareText);
    const select = browser.querySelector('[data-saved-career-select]');
    const previous = browser.querySelector('[data-saved-career-prev]');
    const next = browser.querySelector('[data-saved-career-next]');
    const counter = browser.querySelector('[data-saved-career-counter]');

    function renderCareer(career) {
      selectedSavedCareer = career;
      const selectedKey = normalize(career);
      const cards = [...browser.querySelectorAll('[data-nucleus-course-card]')];
      cards.forEach(card => {
        card.hidden = normalize(card.dataset.careerName) !== selectedKey;
      });
      const index = careers.findIndex(item => normalize(item) === selectedKey);
      const visible = cards.filter(card => !card.hidden).length;
      counter.textContent = `Carrera ${index + 1} de ${careers.length} · ${visible} núcleo${visible === 1 ? '' : 's'} cargado${visible === 1 ? '' : 's'}`;
      previous.disabled = index <= 0;
      next.disabled = index >= careers.length - 1;
      select.value = careers[index] || careers[0];
      window.dispatchEvent(new CustomEvent('informtit:nuclei-career-change', { detail: { career } }));
    }

    select.addEventListener('change', () => renderCareer(select.value));
    previous.addEventListener('click', () => {
      const index = careers.findIndex(item => normalize(item) === normalize(selectedSavedCareer));
      if (index > 0) renderCareer(careers[index - 1]);
    });
    next.addEventListener('click', () => {
      const index = careers.findIndex(item => normalize(item) === normalize(selectedSavedCareer));
      if (index < careers.length - 1) renderCareer(careers[index + 1]);
    });
    renderCareer(selectedSavedCareer);
  }

  function courseCard(course) {
    const status = Number(course.failed_count || 0) === 0 ? 'Sin reprobados' : `${course.failed_count} reprobado(s)`;
    return `<article class="career-card nucleus-card" data-nucleus-course-card data-career-name="${esc(course.career_name)}" data-teacher-name="${esc(course.teacher_name || '')}" data-nucleus-number="${course.nucleus_number}">
      <div class="career-head">
        <div>
          <div class="nucleus-card-badges"><span class="badge">Núcleo ${course.nucleus_number}</span><span class="badge teacher-badge">${esc(course.teacher_name || 'Docente pendiente')}</span></div>
          <h3>${esc(course.career_name)}</h3>
          <p><strong>Docente:</strong> ${esc(course.teacher_name || 'Pendiente de confirmar')}</p>
          <p><strong>Coordinador:</strong> ${esc(course.coordinator_name || 'No identificado')}</p>
        </div>
        <button class="button danger small" data-delete-nucleus="${course.id}">Eliminar</button>
      </div>
      <div class="summary-grid">
        ${summaryItem('Estudiantes', course.graded_students)}
        ${summaryItem('Promedio', fmt(course.course_average))}
        ${summaryItem('Aprobados', course.approved_count)}
        ${summaryItem('Resultado', status)}
      </div>
      <details><summary>Ver calificaciones</summary>${studentsTable(course)}</details>
    </article>`;
  }

  const style = document.createElement('style');
  style.textContent = `
    .nucleus-import-form textarea { min-height: 220px; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; }
    .nucleus-preview-card { margin-top: 20px; padding: 18px; border: 1px solid #cbd5e1; border-radius: 14px; background: #f8fafc; }
    .nucleus-responsibles { margin: 16px 0; }
    .nucleus-responsibles small { display: block; margin-top: 6px; color: #64748b; font-weight: 400; }
    .nucleus-card + .nucleus-card { margin-top: 16px; }
    .nucleus-score-table { min-width: 980px; }
    .nuclei-rule-note { margin: 14px 0 18px; padding: 13px 15px; border: 1px solid #bfdbfe; border-radius: 12px; background: #eff6ff; color: #1e3a5f; }
    .career-browser-toolbar { display: grid; grid-template-columns: auto minmax(260px, 1fr) auto auto; align-items: end; gap: 12px; margin: 18px 0; padding: 14px; border: 1px solid #dbe4ee; border-radius: 14px; background: #f8fafc; }
    .career-browser-toolbar label { margin: 0; }
    .career-browser-counter { align-self: center; color: #526575; font-size: 13px; font-weight: 700; white-space: nowrap; }
    .teacher-load-panel { margin: 4px 0 20px; padding: 16px; border: 1px solid #dbe4ee; border-radius: 16px; background: linear-gradient(135deg, #f8fafc, #eef5fb); }
    .teacher-load-head { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; margin-bottom: 14px; }
    .teacher-load-head h3 { margin: 0 0 4px; }
    .teacher-load-head p { margin: 0; color: #64748b; }
    .teacher-load-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; }
    .teacher-load-card { padding: 14px; border: 1px solid #d4e0eb; border-radius: 13px; background: white; }
    .teacher-load-card > span { display: block; margin-top: 4px; color: #64748b; font-size: 13px; }
    .teacher-assignment-list { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
    .teacher-assignment-list span, .teacher-badge { display: inline-flex; padding: 4px 8px; border-radius: 999px; background: #e7f1f8; color: #24557a; font-size: 11px; font-weight: 700; }
    .nucleus-card-badges { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 8px; }
    .nucleus-card .career-head p { margin: 3px 0; }
    [hidden] { display: none !important; }
    @media (max-width: 920px) {
      .career-browser-toolbar { grid-template-columns: 1fr 1fr; }
      .career-browser-toolbar label, .career-browser-counter { grid-column: 1 / -1; }
      .career-browser-counter { white-space: normal; }
    }
  `;
  document.head.appendChild(style);
})();
