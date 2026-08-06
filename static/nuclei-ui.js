(() => {
  const previousRenderReport = renderReport;
  let currentAnalysis = null;

  function esc(value = '') {
    return typeof escapeHtml === 'function' ? escapeHtml(String(value)) : String(value);
  }

  function fmt(value) {
    if (value === null || value === undefined || value === '') return '—';
    return Number(value).toFixed(2).replace('.', ',');
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
      tab.innerHTML = `
        <div class="process-stack">
          <section class="panel">
            <div class="panel-head">
              <div>
                <h2>Notas de núcleos estructurantes</h2>
                <p>Pegue por separado las calificaciones de Moodle y los participantes del curso. Informtit identificará la carrera, el núcleo, el docente y el coordinador.</p>
              </div>
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
              <div><h2>Núcleos guardados</h2><p>Estos cursos se incorporarán al informe antes de los resultados del Examen Complexivo.</p></div>
            </div>
            <div class="nucleus-list">${data.courses.length ? data.courses.map(courseCard).join('') : '<div class="empty-mini">Todavía no se han cargado notas de núcleos.</div>'}</div>
          </section>
        </div>`;
      bindNucleiEvents(tab);
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
          <label>Docente detectado${teacherControl}</label>
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

  function courseCard(course) {
    const status = Number(course.failed_count || 0) === 0 ? 'Sin reprobados' : `${course.failed_count} reprobado(s)`;
    return `<article class="career-card nucleus-card">
      <div class="career-head">
        <div>
          <span class="badge">Núcleo ${course.nucleus_number}</span>
          <h3>${esc(course.career_name)}</h3>
          <p>Docente: ${esc(course.teacher_name || 'Pendiente de confirmar')} · Coordinador: ${esc(course.coordinator_name || 'No identificado')}</p>
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
    .nucleus-card + .nucleus-card { margin-top: 16px; }
    .nucleus-score-table { min-width: 980px; }
  `;
  document.head.appendChild(style);
})();
