(() => {
  const previousRenderReport = renderReport;

  function esc(value = '') {
    return typeof escapeHtml === 'function'
      ? escapeHtml(String(value))
      : String(value).replace(/[&<>"']/g, character => ({
          '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;',
        })[character]);
  }

  function numberFormat(value) {
    if (value === null || value === undefined || value === '') return '—';
    const number = Number(value);
    return Number.isFinite(number) ? number.toFixed(2).replace('.', ',') : '—';
  }

  function summaryItem(label, value) {
    return `<div class="summary-item"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`;
  }

  function readAsDataURL(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = () => reject(new Error('No se pudo leer el archivo.'));
      reader.readAsDataURL(file);
    });
  }

  renderReport = function renderReportWithIndependentProcesses() {
    previousRenderReport();
    if (!state.activeReport?.id) return;
    renderSchedulesModule();
    renderProjectsModule();
  };

  async function renderSchedulesModule() {
    const tab = document.querySelector('#tab-schedules');
    const reportId = Number(state.activeReport?.id || 0);
    if (!tab || !reportId) return;
    tab.innerHTML = '<div class="panel"><div class="empty-mini">Cargando cronogramas...</div></div>';
    try {
      const data = await api(`/api/reports/${reportId}/schedules`);
      if (Number(state.activeReport?.id || 0) !== reportId) return;
      tab.innerHTML = `
        <div class="process-stack">
          ${scheduleCard('complexive', 'Cronograma de Núcleos y Examen Complexivo', data.schedules.complexive || [], false)}
          ${scheduleCard('thesis', 'Cronograma de Trabajo de Titulación', data.schedules.thesis || [], true)}
        </div>`;
      bindScheduleCard('complexive', reportId);
      bindScheduleCard('thesis', reportId);
    } catch (error) {
      tab.innerHTML = `<div class="panel"><div class="empty-mini">${esc(error.message)}</div></div>`;
    }
  }

  function scheduleCard(type, title, items, showPhase) {
    return `
      <section class="panel schedule-card" data-schedule-card="${type}">
        <div class="panel-head">
          <div><h2>${title}</h2><p>Este cronograma pertenece únicamente a este componente del informe.</p></div>
          <div class="process-actions">
            <button class="button secondary small" type="button" data-add-schedule="${type}">Agregar actividad</button>
            <button class="button secondary small" type="button" data-reset-schedule="${type}">Restaurar</button>
            <button class="button primary small" type="button" data-save-schedule="${type}">Guardar cronograma</button>
          </div>
        </div>
        <div class="schedule-import">
          <label class="file-button">Subir cronograma
            <input type="file" data-schedule-upload="${type}" accept=".xls,.html,.htm,.csv,.txt">
          </label>
          <textarea data-schedule-paste="${type}" rows="4" placeholder="Pegue aquí Actividad, Fecha de inicio y Fecha de fin."></textarea>
          <button class="button secondary small" type="button" data-parse-schedule="${type}">Analizar texto pegado</button>
        </div>
        <div class="student-table-wrap">
          <table class="student-table schedule-table" data-schedule-table="${type}">
            <thead><tr>${showPhase ? '<th>Fase</th>' : ''}<th>Actividad</th><th>Fecha inicio</th><th>Fecha fin</th><th></th></tr></thead>
            <tbody>${items.map(item => scheduleRow(item, showPhase)).join('')}</tbody>
          </table>
        </div>
      </section>`;
  }

  function scheduleRow(item = {}, showPhase = false) {
    return `<tr>
      ${showPhase ? `<td><input class="table-input phase-input" name="phase" value="${esc(item.phase || '')}" placeholder="Fase"></td>` : ''}
      <td><input class="table-input" name="activity" value="${esc(item.activity || '')}" placeholder="Actividad"></td>
      <td><input class="table-input date-input" name="start_date" value="${esc(item.start_date || '')}" placeholder="dd/mm/aaaa"></td>
      <td><input class="table-input date-input" name="end_date" value="${esc(item.end_date || '')}" placeholder="dd/mm/aaaa"></td>
      <td><button class="button danger small" type="button" data-remove-schedule>Eliminar</button></td>
    </tr>`;
  }

  function collectSchedule(card, type) {
    return [...card.querySelectorAll('tbody tr')]
      .map(row => ({
        phase: type === 'thesis' ? row.querySelector('[name="phase"]')?.value || '' : '',
        activity: row.querySelector('[name="activity"]')?.value || '',
        start_date: row.querySelector('[name="start_date"]')?.value || '',
        end_date: row.querySelector('[name="end_date"]')?.value || '',
        executed_date: row.querySelector('[name="executed_date"]')?.value || '',
        execution_status: row.querySelector('[name="execution_status"]')?.value || '',
        compliance_percentage: row.querySelector('[name="compliance_percentage"]')?.value || '',
        evidence: row.querySelector('[name="evidence"]')?.value || '',
        observation: row.querySelector('[name="observation"]')?.value || '',
      }))
      .filter(item => item.activity.trim());
  }

  function bindScheduleCard(type, reportId) {
    const card = document.querySelector(`[data-schedule-card="${type}"]`);
    if (!card) return;
    const showPhase = type === 'thesis';
    card.addEventListener('click', async event => {
      const remove = event.target.closest('[data-remove-schedule]');
      if (remove) {
        remove.closest('tr')?.remove();
        return;
      }
      if (event.target.closest(`[data-add-schedule="${type}"]`)) {
        card.querySelector('tbody')?.insertAdjacentHTML('beforeend', scheduleRow({}, showPhase));
        return;
      }
      if (event.target.closest(`[data-save-schedule="${type}"]`)) {
        try {
          const entries = collectSchedule(card, type);
          const result = await api(`/api/reports/${reportId}/schedules/${type}`, {
            method: 'PUT',
            body: JSON.stringify({ entries }),
          });
          toast(`${result.count} actividades guardadas.`);
          await renderSchedulesModule();
        } catch (error) {
          toast(error.message, true);
        }
        return;
      }
      if (event.target.closest(`[data-reset-schedule="${type}"]`)) {
        if (!confirm('Se restaurará el cronograma predeterminado de este módulo.')) return;
        try {
          await api(`/api/reports/${reportId}/schedules/${type}/reset`, { method: 'POST', body: '{}' });
          toast('Cronograma restaurado.');
          await renderSchedulesModule();
        } catch (error) {
          toast(error.message, true);
        }
        return;
      }
      if (event.target.closest(`[data-parse-schedule="${type}"]`)) {
        const text = card.querySelector(`[data-schedule-paste="${type}"]`)?.value || '';
        if (!text.trim()) return toast('Pegue primero el cronograma.', true);
        await parseAndReplaceSchedule(type, reportId, { text });
      }
    });

    const upload = card.querySelector(`[data-schedule-upload="${type}"]`);
    upload?.addEventListener('change', async () => {
      const file = upload.files?.[0];
      if (!file) return;
      try {
        const dataUrl = await readAsDataURL(file);
        await parseAndReplaceSchedule(type, reportId, { data_url: dataUrl, filename: file.name });
      } catch (error) {
        toast(error.message, true);
      } finally {
        upload.value = '';
      }
    });
  }

  async function parseAndReplaceSchedule(type, reportId, payload) {
    try {
      const parsed = await api(`/api/reports/${reportId}/schedules/${type}/parse`, {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      await api(`/api/reports/${reportId}/schedules/${type}`, {
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
    const reportId = Number(state.activeReport?.id || 0);
    if (!tab || !reportId) return;
    tab.innerHTML = '<div class="panel"><div class="empty-mini">Cargando Trabajo de Titulación...</div></div>';
    try {
      const data = await api(`/api/reports/${reportId}/projects`);
      if (Number(state.activeReport?.id || 0) !== reportId) return;
      const summary = data.summary || {};
      tab.innerHTML = `
        <div class="process-stack independent-thesis">
          <section class="panel">
            <div class="panel-head">
              <div>
                <h2>Trabajo de Titulación</h2>
                <p>Módulo independiente. Sus estudiantes se registran aquí y no se toman de Requisitos, Núcleos ni Examen Complexivo.</p>
              </div>
            </div>
            <div class="summary-grid project-summary">
              ${summaryItem('Registrados', summary.total || 0)}
              ${summaryItem('Aprobados', summary.approved || 0)}
              ${summaryItem('Reprobados', summary.failed || 0)}
              ${summaryItem('Promedio final', numberFormat(summary.average_final))}
            </div>
            <form id="project-import-form" class="project-import-form">
              <div class="form-grid three">
                <label>Cédula<input name="identification" required placeholder="Número de identificación"></label>
                <label>Estudiante<input name="full_name" required placeholder="Apellidos y nombres"></label>
                <label>Carrera<input name="career_name" required placeholder="Carrera"></label>
              </div>
              <label>Información copiada del Trabajo de Titulación
                <textarea name="text" rows="15" required placeholder="Pegue aquí calificaciones, vocales, evaluación práctica, defensa y calificación final."></textarea>
              </label>
              <div class="form-actions"><button class="button primary">Analizar y guardar</button></div>
            </form>
          </section>
          <section class="panel">
            <div class="panel-head"><div><h2>Resultados de Trabajo de Titulación</h2><p>Los registros de esta sección son propios del módulo.</p></div></div>
            <div class="project-list">${(data.projects || []).length ? data.projects.map(projectCard).join('') : '<div class="empty-mini">Todavía no existen estudiantes registrados en Trabajo de Titulación.</div>'}</div>
          </section>
        </div>`;

      tab.querySelector('#project-import-form')?.addEventListener('submit', async event => {
        event.preventDefault();
        const form = event.currentTarget;
        try {
          const payload = Object.fromEntries(new FormData(form).entries());
          const result = await api(`/api/reports/${reportId}/projects/parse`, {
            method: 'POST',
            body: JSON.stringify(payload),
          });
          toast(`Trabajo de Titulación guardado. Nota final: ${numberFormat(result.final_grade)}.`);
          await renderProjectsModule();
        } catch (error) {
          toast(error.message, true);
        }
      });

      tab.querySelectorAll('[data-delete-project]').forEach(button => {
        button.addEventListener('click', async () => {
          if (!confirm('¿Eliminar este registro de Trabajo de Titulación?')) return;
          try {
            await api(`/api/reports/${reportId}/projects/${button.dataset.deleteProject}`, {
              method: 'DELETE',
              body: '{}',
            });
            toast('Registro eliminado.');
            await renderProjectsModule();
          } catch (error) {
            toast(error.message, true);
          }
        });
      });
    } catch (error) {
      tab.innerHTML = `<div class="panel"><div class="empty-mini">${esc(error.message)}</div></div>`;
    }
  }

  function projectCard(project) {
    const practical = (project.scores || []).filter(row => row.evaluation_type === 'practical');
    const defense = (project.scores || []).filter(row => row.evaluation_type === 'defense');
    const approved = project.final_grade !== null && project.final_grade !== undefined && Number(project.final_grade) >= 7;
    const status = project.final_grade === null || project.final_grade === undefined ? 'Sin nota final' : approved ? 'Aprobado' : 'Reprobado';
    return `
      <article class="career-card project-card">
        <div class="career-head">
          <div>
            <span class="badge">${esc(status)}</span>
            <h3>${esc(project.full_name)}</h3>
            <p>${esc(project.identification || 'Sin cédula')} · ${esc(project.career_name || 'Sin carrera')}</p>
          </div>
          <button class="button danger small" type="button" data-delete-project="${Number(project.id)}">Eliminar</button>
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
        <div class="project-meta"><strong>Acta:</strong> ${esc(project.act_number || '—')} · ${esc(project.act_date || '—')}</div>
        <div class="project-meta"><strong>Vocales:</strong> ${esc(project.vocal_1 || '—')} · ${esc(project.vocal_2 || '—')} · ${esc(project.vocal_3 || '—')}</div>
        <details>
          <summary>Ver evaluación práctica y defensa</summary>
          ${scoreTable('Evaluación práctica', practical, project)}
          ${scoreTable('Evaluación de la defensa', defense, project)}
        </details>
      </article>`;
  }

  function scoreTable(title, rows, project) {
    return `
      <h4>${esc(title)}</h4>
      <div class="student-table-wrap"><table class="student-table compact-table">
        <thead><tr><th>Criterio</th><th>Máximo</th><th>${esc(project.vocal_1 || 'Vocal 1')}</th><th>${esc(project.vocal_2 || 'Vocal 2')}</th><th>${esc(project.vocal_3 || 'Vocal 3')}</th></tr></thead>
        <tbody>${rows.map(row => `<tr><td>${esc(row.criterion)}</td><td>${numberFormat(row.max_score)}</td><td>${numberFormat(row.vocal_1)}</td><td>${numberFormat(row.vocal_2)}</td><td>${numberFormat(row.vocal_3)}</td></tr>`).join('')}</tbody>
      </table></div>`;
  }
})();
