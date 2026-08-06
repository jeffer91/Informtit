(() => {
  const originalRenderReport = renderReport;

  function localEscape(value = '') {
    return typeof escapeHtml === 'function' ? escapeHtml(value) : String(value);
  }

  function numberFormat(value) {
    if (value === null || value === undefined || value === '') return '—';
    return Number(value).toFixed(2).replace('.', ',');
  }

  function readAsDataURL(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = () => reject(new Error('No se pudo leer el archivo.'));
      reader.readAsDataURL(file);
    });
  }

  renderReport = function renderReportWithProcesses() {
    originalRenderReport();
    if (!state.activeReport) return;
    renderSchedulesModule();
    renderProjectsModule();
  };

  async function renderSchedulesModule() {
    const tab = document.querySelector('#tab-schedules');
    if (!tab) return;
    tab.innerHTML = '<div class="panel"><div class="empty-mini">Cargando cronogramas...</div></div>';
    try {
      const data = await api(`/api/reports/${state.activeReport.id}/schedules`);
      tab.innerHTML = `
        <div class="process-stack">
          ${scheduleCard('complexive', 'Cronograma 1: Núcleos y Examen Complexivo', data.schedules.complexive, false)}
          ${scheduleCard('thesis', 'Cronograma 2: Trabajo de Titulación', data.schedules.thesis, true)}
        </div>`;
      bindScheduleCard('complexive');
      bindScheduleCard('thesis');
    } catch (error) {
      tab.innerHTML = `<div class="panel"><div class="empty-mini">${localEscape(error.message)}</div></div>`;
    }
  }

  function scheduleCard(type, title, items, showPhase) {
    const accepted = '.xls,.html,.htm,.csv,.txt';
    return `
      <section class="panel schedule-card" data-schedule-card="${type}">
        <div class="panel-head">
          <div>
            <h2>${title}</h2>
            <p>${showPhase ? 'Organizado en inicio y planificación, desarrollo y tutorías, y defensa final.' : `Periodo: ${localEscape(state.activeReport.period)}`}</p>
          </div>
          <div class="process-actions">
            <button class="button secondary small" data-add-schedule="${type}">Agregar actividad</button>
            <button class="button secondary small" data-reset-schedule="${type}">Restaurar</button>
            <button class="button primary small" data-save-schedule="${type}">Guardar cronograma</button>
          </div>
        </div>
        <div class="schedule-import">
          <label class="file-button">Subir cronograma
            <input type="file" data-schedule-upload="${type}" accept="${accepted}">
          </label>
          <textarea data-schedule-paste="${type}" rows="3" placeholder="También puede pegar aquí la tabla con Actividad, Fecha de inicio y Fecha de fin."></textarea>
          <button class="button secondary small" data-parse-schedule="${type}">Analizar texto pegado</button>
        </div>
        <div class="student-table-wrap">
          <table class="student-table schedule-table" data-schedule-table="${type}">
            <thead><tr>${showPhase ? '<th>Fase</th>' : ''}<th>Actividad</th><th>Fecha de inicio</th><th>Fecha de fin</th><th></th></tr></thead>
            <tbody>${items.map(item => scheduleRow(item, showPhase)).join('')}</tbody>
          </table>
        </div>
      </section>`;
  }

  function scheduleRow(item = {}, showPhase = false) {
    return `<tr>
      ${showPhase ? `<td><input class="table-input phase-input" name="phase" value="${localEscape(item.phase || '')}" placeholder="Fase 1: Inicio y planificación"></td>` : ''}
      <td><input class="table-input" name="activity" value="${localEscape(item.activity || '')}" placeholder="Actividad"></td>
      <td><input class="table-input date-input" name="start_date" value="${localEscape(item.start_date || '')}" placeholder="dd/mm/aaaa"></td>
      <td><input class="table-input date-input" name="end_date" value="${localEscape(item.end_date || '')}" placeholder="dd/mm/aaaa"></td>
      <td><button class="button danger small" type="button" data-remove-schedule>Eliminar</button></td>
    </tr>`;
  }

  function bindScheduleCard(type) {
    const card = document.querySelector(`[data-schedule-card="${type}"]`);
    if (!card) return;
    const showPhase = type === 'thesis';

    card.addEventListener('click', async event => {
      const remove = event.target.closest('[data-remove-schedule]');
      if (remove) {
        remove.closest('tr').remove();
        return;
      }
      if (event.target.closest(`[data-add-schedule="${type}"]`)) {
        const tbody = card.querySelector('tbody');
        tbody.insertAdjacentHTML('beforeend', scheduleRow({}, showPhase));
        return;
      }
      if (event.target.closest(`[data-save-schedule="${type}"]`)) {
        await saveScheduleFromCard(type, card);
        return;
      }
      if (event.target.closest(`[data-reset-schedule="${type}"]`)) {
        if (!confirm('Se reemplazará este cronograma por el cronograma predeterminado.')) return;
        await api(`/api/reports/${state.activeReport.id}/schedules/${type}/reset`, { method: 'POST', body: '{}' });
        toast('Cronograma restaurado.');
        await renderSchedulesModule();
        return;
      }
      if (event.target.closest(`[data-parse-schedule="${type}"]`)) {
        const text = card.querySelector(`[data-schedule-paste="${type}"]`).value;
        if (!text.trim()) return toast('Pegue primero el cronograma.', true);
        await parseAndReplaceSchedule(type, { text });
      }
    });

    const upload = card.querySelector(`[data-schedule-upload="${type}"]`);
    upload.addEventListener('change', async () => {
      const file = upload.files[0];
      if (!file) return;
      try {
        const dataUrl = await readAsDataURL(file);
        await parseAndReplaceSchedule(type, { data_url: dataUrl, filename: file.name });
      } catch (error) {
        toast(error.message, true);
      } finally {
        upload.value = '';
      }
    });
  }

  function collectSchedule(card, type) {
    return [...card.querySelectorAll('tbody tr')].map(row => ({
      phase: type === 'thesis' ? row.querySelector('[name=phase]').value : '',
      activity: row.querySelector('[name=activity]').value,
      start_date: row.querySelector('[name=start_date]').value,
      end_date: row.querySelector('[name=end_date]').value,
    })).filter(item => item.activity.trim());
  }

  async function saveScheduleFromCard(type, card) {
    try {
      const entries = collectSchedule(card, type);
      const result = await api(`/api/reports/${state.activeReport.id}/schedules/${type}`, {
        method: 'PUT',
        body: JSON.stringify({ entries }),
      });
      toast(`${result.count} actividades guardadas.`);
      await renderSchedulesModule();
    } catch (error) {
      toast(error.message, true);
    }
  }

  async function parseAndReplaceSchedule(type, payload) {
    try {
      const parsed = await api(`/api/reports/${state.activeReport.id}/schedules/${type}/parse`, {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      await api(`/api/reports/${state.activeReport.id}/schedules/${type}`, {
        method: 'PUT',
        body: JSON.stringify({ entries: parsed.entries }),
      });
      toast(`${parsed.entries.length} actividades detectadas e importadas.`);
      await renderSchedulesModule();
    } catch (error) {
      toast(error.message, true);
    }
  }

  async function renderProjectsModule() {
    const tab = document.querySelector('#tab-projects');
    if (!tab) return;
    tab.innerHTML = '<div class="panel"><div class="empty-mini">Cargando trabajos de titulación...</div></div>';
    try {
      const [projectsData, rosterData] = await Promise.all([
        api(`/api/reports/${state.activeReport.id}/projects`),
        api(`/api/reports/${state.activeReport.id}/roster`),
      ]);
      const students = rosterData.students || [];
      const summary = projectsData.summary;
      tab.innerHTML = `
        <div class="process-stack">
          <section class="panel">
            <div class="panel-head">
              <div><h2>Trabajo de Titulación</h2><p>Esta sección es independiente del Examen Complexivo y conserva calificaciones de 0 a 10.</p></div>
            </div>
            <div class="summary-grid project-summary">
              ${summaryItem('Estudiantes', summary.total)}
              ${summaryItem('Aprobados', summary.approved)}
              ${summaryItem('Reprobados', summary.failed)}
              ${summaryItem('Promedio final', numberFormat(summary.average_final))}
            </div>
            <form id="project-import-form" class="project-import-form">
              <label>Estudiante de la base
                <select name="student_id" required>
                  <option value="">Seleccione un estudiante</option>
                  ${students.map(student => `<option value="${student.id}">${localEscape(student.identification || 'Sin cédula')} · ${localEscape(student.full_name)} · ${localEscape(student.career_name)}</option>`).join('')}
                </select>
              </label>
              <label>Información copiada del proyecto
                <textarea name="text" rows="15" required placeholder="Pegue aquí Información Proyecto, vocales, evaluación práctica, defensa y calificación final."></textarea>
              </label>
              <div class="form-actions"><button class="button primary">Analizar y guardar estudiante</button></div>
            </form>
          </section>
          <section class="panel">
            <div class="panel-head"><div><h2>Resultados de Trabajo de Titulación</h2><p>Trabajo escrito 60 % y defensa oral 40 %.</p></div></div>
            <div class="project-list">${projectsData.projects.length ? projectsData.projects.map(projectCard).join('') : '<div class="empty-mini">Todavía no existen estudiantes registrados en Trabajo de Titulación.</div>'}</div>
          </section>
        </div>`;

      document.querySelector('#project-import-form').addEventListener('submit', async event => {
        event.preventDefault();
        const form = event.currentTarget;
        try {
          const result = await api(`/api/reports/${state.activeReport.id}/projects/parse`, {
            method: 'POST',
            body: JSON.stringify({ student_id: Number(form.student_id.value), text: form.text.value }),
          });
          toast(`Trabajo de titulación guardado. Nota final: ${numberFormat(result.final_grade)}.`);
          await renderProjectsModule();
        } catch (error) {
          toast(error.message, true);
        }
      });

      tab.querySelectorAll('[data-delete-project]').forEach(button => {
        button.addEventListener('click', async () => {
          if (!confirm('¿Eliminar este resultado de Trabajo de Titulación?')) return;
          await api(`/api/reports/${state.activeReport.id}/projects/${button.dataset.deleteProject}`, {
            method: 'DELETE',
            body: '{}',
          });
          toast('Registro eliminado.');
          await renderProjectsModule();
        });
      });
    } catch (error) {
      tab.innerHTML = `<div class="panel"><div class="empty-mini">${localEscape(error.message)}</div></div>`;
    }
  }

  function summaryItem(label, value) {
    return `<div class="summary-item"><span>${label}</span><strong>${value}</strong></div>`;
  }

  function projectCard(project) {
    const practical = project.scores.filter(row => row.evaluation_type === 'practical');
    const defense = project.scores.filter(row => row.evaluation_type === 'defense');
    const approved = Number(project.final_grade || 0) >= 7;
    return `
      <article class="career-card project-card">
        <div class="career-head">
          <div>
            <span class="badge">${approved ? 'Aprobado' : 'Reprobado'}</span>
            <h3>${localEscape(project.full_name)}</h3>
            <p>${localEscape(project.identification)} · ${localEscape(project.career_name)}</p>
          </div>
          <button class="button danger small" data-delete-project="${project.id}">Eliminar</button>
        </div>
        <div class="summary-grid">
          ${summaryItem('Tutor', numberFormat(project.tutor_grade))}
          ${summaryItem('Lector', numberFormat(project.reader_grade))}
          ${summaryItem('Trabajo escrito', numberFormat(project.written_average))}
          ${summaryItem('Práctica', numberFormat(project.practical_average))}
          ${summaryItem('Defensa', numberFormat(project.defense_average))}
          ${summaryItem('Defensa oral', numberFormat(project.oral_average))}
          ${summaryItem('Calificación final', numberFormat(project.final_grade))}
        </div>
        <div class="project-meta"><strong>Acta:</strong> ${localEscape(project.act_number || '—')} · ${localEscape(project.act_date || '—')}</div>
        <div class="project-meta"><strong>Vocales:</strong> ${localEscape(project.vocal_1 || '—')} · ${localEscape(project.vocal_2 || '—')} · ${localEscape(project.vocal_3 || '—')}</div>
        <details>
          <summary>Ver evaluación práctica y defensa</summary>
          ${scoreTable('Evaluación práctica', practical, project)}
          ${scoreTable('Evaluación de la defensa', defense, project)}
        </details>
      </article>`;
  }

  function scoreTable(title, rows, project) {
    return `
      <h4>${title}</h4>
      <div class="student-table-wrap"><table class="student-table compact-table">
        <thead><tr><th>Criterio</th><th>Máximo</th><th>${localEscape(project.vocal_1 || 'Vocal 1')}</th><th>${localEscape(project.vocal_2 || 'Vocal 2')}</th><th>${localEscape(project.vocal_3 || 'Vocal 3')}</th></tr></thead>
        <tbody>${rows.map(row => `<tr><td>${localEscape(row.criterion)}</td><td>${numberFormat(row.max_score)}</td><td>${numberFormat(row.vocal_1)}</td><td>${numberFormat(row.vocal_2)}</td><td>${numberFormat(row.vocal_3)}</td></tr>`).join('')}</tbody>
      </table></div>`;
  }
})();
