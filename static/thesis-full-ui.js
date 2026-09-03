(() => {
  const previousRenderReport = renderReport;
  let rendering = false;
  let renderQueued = false;
  let previewProjects = [];

  function esc(value = '') {
    return typeof escapeHtml === 'function'
      ? escapeHtml(String(value))
      : String(value).replace(/[&<>"']/g, character => ({
          '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;',
        })[character]);
  }

  function fmt(value) {
    if (value === null || value === undefined || value === '') return '—';
    const number = Number(value);
    return Number.isFinite(number) ? number.toFixed(2).replace('.', ',') : '—';
  }

  function normalize(value = '') {
    return String(value).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
  }

  function summaryItem(label, value) {
    return `<div class="summary-item"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`;
  }

  function queueRender() {
    if (renderQueued || rendering || !state.activeReport?.id) return;
    renderQueued = true;
    requestAnimationFrame(async () => {
      renderQueued = false;
      await renderThesisModule();
    });
  }

  renderReport = function renderReportWithFullThesis() {
    previousRenderReport();
    queueRender();
  };

  async function renderThesisModule() {
    const tab = document.querySelector('#tab-projects');
    const reportId = Number(state.activeReport?.id || 0);
    if (!tab || !reportId || rendering) return;
    rendering = true;
    try {
      const data = await api(`/api/reports/${reportId}/projects`);
      if (Number(state.activeReport?.id || 0) !== reportId) return;
      const projects = data.projects || [];
      const finals = projects.map(project => Number(project.final_grade)).filter(Number.isFinite);
      const approved = projects.filter(project => normalize(project.final_status || '') === 'aprobado' || (project.final_grade != null && Number(project.final_grade) >= 7)).length;
      const failed = projects.filter(project => normalize(project.final_status || '') === 'reprobado' || (project.final_grade != null && Number(project.final_grade) < 7)).length;
      const incomplete = Math.max(0, projects.length - approved - failed);
      const average = finals.length ? finals.reduce((sum, value) => sum + value, 0) / finals.length : null;

      tab.innerHTML = `
        <div class="process-stack thesis-full-module" data-thesis-full>
          <section class="panel">
            <div class="panel-head">
              <div>
                <h2>Trabajo de Titulación</h2>
                <p>Pegue el bloque completo del sistema académico. Primero se analiza; después puede revisar y corregir cada dato antes de guardarlo.</p>
              </div>
            </div>
            <div class="summary-grid project-summary">
              ${summaryItem('Registrados', projects.length)}
              ${summaryItem('Aprobados', approved)}
              ${summaryItem('Reprobados', failed)}
              ${summaryItem('Incompletos', incomplete)}
              ${summaryItem('Promedio final', fmt(average))}
            </div>
            <form id="thesis-analysis-form" class="project-import-form">
              <label>Información completa del Trabajo de Titulación
                <textarea name="text" rows="20" required placeholder="Pegue desde Nombres / Cédula / Código de Carrera / Carrera hasta CALIFICACIÓN FINAL DEL PROYECTO DE TITULACIÓN."></textarea>
              </label>
              <div class="form-actions">
                <button class="button primary" type="submit">Analizar información</button>
              </div>
            </form>
            <div id="thesis-preview"></div>
          </section>

          <section class="panel">
            <div class="panel-head"><div><h2>Registros guardados</h2><p>Los resultados se recalculan con 60 % de trabajo escrito y 40 % de defensa oral.</p></div></div>
            <div class="project-list">${projects.length ? projects.map(projectCard).join('') : '<div class="empty-mini">Todavía no existen estudiantes registrados en Trabajo de Titulación.</div>'}</div>
          </section>
        </div>`;

      bindAnalysis(reportId, tab);
      bindStoredActions(reportId, tab);
    } catch (error) {
      tab.innerHTML = `<div class="panel"><div class="empty-mini">${esc(error.message)}</div></div>`;
    } finally {
      rendering = false;
    }
  }

  function bindAnalysis(reportId, tab) {
    const form = tab.querySelector('#thesis-analysis-form');
    form?.addEventListener('submit', async event => {
      event.preventDefault();
      const submit = form.querySelector('button[type="submit"]');
      if (submit?.disabled) return;
      if (submit) submit.disabled = true;
      try {
        const text = form.elements.text.value;
        const result = await api(`/api/reports/${reportId}/projects/analyze`, {
          method: 'POST',
          body: JSON.stringify({ text }),
        });
        previewProjects = result.projects || [];
        renderPreview(tab, previewProjects);
        if (result.has_errors) toast('Se detectaron errores que deben corregirse antes de guardar.', true);
        else if (result.has_warnings) toast('Análisis completado con advertencias para revisar.');
        else toast('Información interpretada correctamente. Revise la vista previa.');
      } catch (error) {
        toast(error.message, true);
      } finally {
        if (submit && document.contains(submit)) submit.disabled = false;
      }
    });
  }

  function renderPreview(tab, projects) {
    const host = tab.querySelector('#thesis-preview');
    if (!host) return;
    if (!projects.length) {
      host.innerHTML = '<div class="empty-mini">No se detectaron registros.</div>';
      return;
    }
    host.innerHTML = `
      <div class="thesis-preview-wrap">
        <div class="thesis-preview-title"><h3>Vista previa y validación</h3><p>Todo campo puede corregirse antes de guardarlo.</p></div>
        ${projects.map((project, index) => previewCard(project, index)).join('')}
        <div class="form-actions thesis-save-actions">
          <button class="button primary" type="button" data-save-thesis-preview>Guardar ${projects.length === 1 ? 'registro' : `${projects.length} registros`}</button>
        </div>
      </div>`;
    host.querySelector('[data-save-thesis-preview]')?.addEventListener('click', async event => {
      const button = event.currentTarget;
      if (button.disabled) return;
      button.disabled = true;
      try {
        const payload = { projects: collectPreview(host) };
        const reportId = Number(state.activeReport?.id || 0);
        const result = await api(`/api/reports/${reportId}/projects/save`, {
          method: 'POST',
          body: JSON.stringify(payload),
        });
        toast(`${result.count} registro${result.count === 1 ? '' : 's'} de Trabajo de Titulación guardado${result.count === 1 ? '' : 's'}.`);
        previewProjects = [];
        await renderThesisModule();
      } catch (error) {
        toast(error.message, true);
        if (document.contains(button)) button.disabled = false;
      }
    });
  }

  function inputField(label, name, value, type = 'text', extra = '') {
    return `<label>${esc(label)}<input name="${esc(name)}" type="${esc(type)}" value="${esc(value ?? '')}" ${extra}></label>`;
  }

  function previewCard(project, index) {
    const validation = project.validation || {};
    return `<article class="thesis-preview-card" data-thesis-preview-card="${index}">
      <div class="thesis-preview-head">
        <div><strong>${esc(project.full_name || 'Estudiante por confirmar')}</strong><span>${esc(project.identification || 'Sin identificación')}</span></div>
        <span class="badge ${normalize(project.final_status) === 'aprobado' ? 'success' : normalize(project.final_status) === 'reprobado' ? 'danger' : ''}">${esc(project.final_status || 'INCOMPLETO')}</span>
      </div>
      <div class="form-grid four thesis-core-fields">
        ${inputField('Cédula', 'identification', project.identification)}
        ${inputField('Nombre del estudiante', 'full_name', project.full_name)}
        ${inputField('Código de carrera', 'career_code', project.career_code)}
        ${inputField('Carrera', 'career_name', project.career_name)}
        ${inputField('Número de acta', 'act_number', project.act_number)}
        ${inputField('Fecha del acta', 'act_date', project.act_date)}
        ${inputField('Modalidad', 'modality', project.modality)}
        ${inputField('Título del proyecto', 'project_title', project.project_title)}
        ${inputField('Nombre del tutor', 'tutor_name', project.tutor_name)}
        ${inputField('Nombre del lector', 'reader_name', project.reader_name)}
        ${inputField('Calificación tutor', 'tutor_grade', project.tutor_grade, 'number', 'min="0" max="10" step="0.01"')}
        ${inputField('Calificación lector', 'reader_grade', project.reader_grade, 'number', 'min="0" max="10" step="0.01"')}
        ${inputField('Primer vocal', 'vocal_1', project.vocal_1)}
        ${inputField('Segundo vocal', 'vocal_2', project.vocal_2)}
        ${inputField('Tercer vocal', 'vocal_3', project.vocal_3)}
      </div>
      ${scoreEditor('Evaluación práctica', 'practical', project.practical_scores || [])}
      ${scoreEditor('Evaluación de la defensa', 'defense', project.defense_scores || [])}
      <div class="summary-grid thesis-calculated">
        ${summaryItem('Trabajo escrito calculado', fmt(project.written_average))}
        ${summaryItem('Promedio práctica', fmt(project.practical_average))}
        ${summaryItem('Promedio defensa', fmt(project.defense_average))}
        ${summaryItem('Promedio oral', fmt(project.oral_average))}
        ${summaryItem('Calificación final', fmt(project.final_grade))}
        ${summaryItem('Estado', project.final_status || 'INCOMPLETO')}
      </div>
      ${project.lowest_parameter ? `<p class="thesis-lowest"><strong>Menor desempeño relativo:</strong> ${esc(project.lowest_parameter)} (${esc(project.lowest_component)}).</p>` : ''}
      ${validationMarkup(validation)}
      <input type="hidden" name="raw_text" value="${esc(project.raw_text || '')}">
      <input type="hidden" name="source_values" value="${esc(JSON.stringify(project.source_values || {}))}">
    </article>`;
  }

  function scoreEditor(title, type, rows) {
    return `<div class="thesis-score-editor" data-score-type="${type}">
      <h4>${esc(title)}</h4>
      <div class="student-table-wrap"><table class="student-table compact-table">
        <thead><tr><th>Parámetro</th><th>Máximo</th><th>Primer vocal</th><th>Segundo vocal</th><th>Tercer vocal</th></tr></thead>
        <tbody>${rows.map((row, index) => `<tr data-score-row="${index}">
          <td><input class="table-input" name="criterion" value="${esc(row.criterion || '')}"></td>
          <td><input class="table-input" name="max_score" type="number" step="0.01" min="0" value="${esc(row.max_score ?? '')}"></td>
          <td><input class="table-input" name="vocal_1" type="number" step="0.01" min="0" value="${esc(row.vocal_1 ?? '')}"></td>
          <td><input class="table-input" name="vocal_2" type="number" step="0.01" min="0" value="${esc(row.vocal_2 ?? '')}"></td>
          <td><input class="table-input" name="vocal_3" type="number" step="0.01" min="0" value="${esc(row.vocal_3 ?? '')}"></td>
        </tr>`).join('')}</tbody>
      </table></div>
    </div>`;
  }

  function validationMarkup(validation) {
    const groups = [
      ['error', 'Errores', validation.errors || []],
      ['warning', 'Advertencias', validation.warnings || []],
      ['info', 'Información', validation.info || []],
    ].filter(([, , items]) => items.length);
    if (!groups.length) return '<div class="thesis-validation ok"><strong>Validación:</strong> sin novedades.</div>';
    return `<div class="thesis-validation">${groups.map(([kind, title, items]) => `<div class="validation-${kind}"><strong>${title}</strong><ul>${items.map(item => `<li>${esc(item)}</li>`).join('')}</ul></div>`).join('')}</div>`;
  }

  function collectPreview(host) {
    return [...host.querySelectorAll('[data-thesis-preview-card]')].map(card => {
      const value = name => card.querySelector(`.thesis-core-fields [name="${name}"]`)?.value || '';
      const scores = type => [...card.querySelectorAll(`[data-score-type="${type}"] [data-score-row]`)].map(row => ({
        criterion: row.querySelector('[name="criterion"]')?.value || '',
        max_score: row.querySelector('[name="max_score"]')?.value || '',
        vocal_1: row.querySelector('[name="vocal_1"]')?.value || '',
        vocal_2: row.querySelector('[name="vocal_2"]')?.value || '',
        vocal_3: row.querySelector('[name="vocal_3"]')?.value || '',
      }));
      let sourceValues = {};
      try { sourceValues = JSON.parse(card.querySelector('[name="source_values"]')?.value || '{}'); } catch (_) {}
      return {
        identification: value('identification'),
        full_name: value('full_name'),
        career_code: value('career_code'),
        career_name: value('career_name'),
        act_number: value('act_number'),
        act_date: value('act_date'),
        modality: value('modality'),
        project_title: value('project_title'),
        tutor_name: value('tutor_name'),
        reader_name: value('reader_name'),
        tutor_grade: value('tutor_grade'),
        reader_grade: value('reader_grade'),
        vocal_1: value('vocal_1'),
        vocal_2: value('vocal_2'),
        vocal_3: value('vocal_3'),
        practical_scores: scores('practical'),
        defense_scores: scores('defense'),
        raw_text: card.querySelector('[name="raw_text"]')?.value || '',
        source_values: sourceValues,
      };
    });
  }

  function bindStoredActions(reportId, tab) {
    tab.querySelectorAll('[data-delete-project]').forEach(button => {
      button.addEventListener('click', async () => {
        if (!confirm('¿Eliminar este registro de Trabajo de Titulación?')) return;
        try {
          await api(`/api/reports/${reportId}/projects/${button.dataset.deleteProject}`, { method: 'DELETE', body: '{}' });
          toast('Registro eliminado.');
          await renderThesisModule();
        } catch (error) {
          toast(error.message, true);
        }
      });
    });
  }

  function projectCard(project) {
    const practical = (project.scores || []).filter(row => row.evaluation_type === 'practical');
    const defense = (project.scores || []).filter(row => row.evaluation_type === 'defense');
    const status = project.final_status || (project.final_grade == null ? 'INCOMPLETO' : Number(project.final_grade) >= 7 ? 'APROBADO' : 'REPROBADO');
    return `<article class="career-card project-card thesis-stored-card">
      <div class="career-head">
        <div><span class="badge">${esc(status)}</span><h3>${esc(project.full_name)}</h3><p>${esc(project.identification || 'Sin cédula')} · ${esc(project.career_name || 'Sin carrera')}</p></div>
        <button class="button danger small" type="button" data-delete-project="${Number(project.id)}">Eliminar</button>
      </div>
      <div class="summary-grid">
        ${summaryItem('Trabajo escrito', fmt(project.written_average))}
        ${summaryItem('Práctica', fmt(project.practical_average))}
        ${summaryItem('Defensa', fmt(project.defense_average))}
        ${summaryItem('Promedio oral', fmt(project.oral_average))}
        ${summaryItem('Calificación final', fmt(project.final_grade))}
      </div>
      <div class="project-meta"><strong>Acta:</strong> ${esc(project.act_number || '—')} · ${esc(project.act_date || '—')} · <strong>Código:</strong> ${esc(project.career_code || '—')}</div>
      <div class="project-meta"><strong>Vocales:</strong> ${esc(project.vocal_1 || '—')} · ${esc(project.vocal_2 || '—')} · ${esc(project.vocal_3 || '—')}</div>
      ${project.lowest_parameter ? `<div class="project-meta"><strong>Menor desempeño relativo:</strong> ${esc(project.lowest_parameter)} (${esc(project.lowest_component || '')})</div>` : ''}
      <details><summary>Ver rúbricas de evaluación</summary>${scoreTable('Evaluación práctica', practical, project)}${scoreTable('Evaluación de la defensa', defense, project)}</details>
    </article>`;
  }

  function scoreTable(title, rows, project) {
    return `<h4>${esc(title)}</h4><div class="student-table-wrap"><table class="student-table compact-table">
      <thead><tr><th>Criterio</th><th>Máximo</th><th>${esc(project.vocal_1 || 'Vocal 1')}</th><th>${esc(project.vocal_2 || 'Vocal 2')}</th><th>${esc(project.vocal_3 || 'Vocal 3')}</th></tr></thead>
      <tbody>${rows.map(row => `<tr><td>${esc(row.criterion)}</td><td>${fmt(row.max_score)}</td><td>${fmt(row.vocal_1)}</td><td>${fmt(row.vocal_2)}</td><td>${fmt(row.vocal_3)}</td></tr>`).join('')}</tbody>
    </table></div>`;
  }

  const observer = new MutationObserver(() => {
    const tab = document.querySelector('#tab-projects');
    if (!state.activeReport?.id || !tab || rendering) return;
    if (!tab.querySelector('[data-thesis-full]')) queueRender();
  });
  observer.observe(document.body, { childList: true, subtree: true });

  const style = document.createElement('style');
  style.textContent = `
    .thesis-full-module { gap: 14px; }
    .thesis-preview-wrap { margin-top: 18px; display: grid; gap: 14px; }
    .thesis-preview-title p { margin: 2px 0 0; color: #64748b; }
    .thesis-preview-card { border: 1px solid #cbd5e1; border-radius: 14px; padding: 15px; background: #f8fafc; display: grid; gap: 14px; }
    .thesis-preview-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
    .thesis-preview-head > div { display: grid; gap: 2px; }
    .thesis-preview-head span { color: #64748b; font-size: 12px; }
    .form-grid.four { grid-template-columns: repeat(4, minmax(0, 1fr)); }
    .thesis-score-editor h4 { margin: 2px 0 8px; color: #173b57; }
    .thesis-score-editor .table-input { min-width: 84px; }
    .thesis-score-editor td:first-child .table-input { min-width: 210px; }
    .thesis-validation { display: grid; gap: 8px; }
    .thesis-validation > div { border-radius: 10px; padding: 9px 11px; }
    .thesis-validation ul { margin: 5px 0 0 18px; }
    .validation-error { background: #fef2f2; color: #991b1b; }
    .validation-warning { background: #fff7ed; color: #9a3412; }
    .validation-info { background: #eff6ff; color: #1e40af; }
    .thesis-validation.ok { background: #f0fdf4; color: #166534; border-radius: 10px; padding: 9px 11px; }
    .thesis-lowest { margin: 0; color: #475569; }
    .thesis-save-actions { justify-content: flex-end; }
    @media (max-width: 1150px) { .form-grid.four { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
    @media (max-width: 680px) { .form-grid.four { grid-template-columns: 1fr; } .thesis-preview-head { align-items: flex-start; flex-direction: column; } }
  `;
  document.head.appendChild(style);
})();
