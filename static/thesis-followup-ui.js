(() => {
  const previousRenderReport = renderReport;
  let scheduled = 0;

  function esc(value = '') {
    return typeof escapeHtml === 'function'
      ? escapeHtml(String(value))
      : String(value).replace(/[&<>"']/g, character => ({
          '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;',
        })[character]);
  }

  renderReport = function renderReportWithThesisFollowup() {
    previousRenderReport();
    scheduleEnhancement();
  };

  function scheduleEnhancement() {
    const token = ++scheduled;
    setTimeout(() => {
      if (token === scheduled) enhanceProjects();
    }, 120);
  }

  function field(label, name, value = '', placeholder = '') {
    return `<label>${label}<input name="${name}" value="${esc(value || '')}" placeholder="${esc(placeholder)}"></label>`;
  }

  function selectField(label, name, value, options) {
    return `<label>${label}<select name="${name}"><option value="">Sin información</option>${options.map(option => `<option value="${esc(option)}" ${option === (value || '') ? 'selected' : ''}>${esc(option)}</option>`).join('')}</select></label>`;
  }

  function followupMarkup(project) {
    return `<details class="project-followup" data-project-followup="${project.id}">
      <summary>Seguimiento académico y documental</summary>
      <form class="project-followup-form" data-project-followup-form="${project.id}">
        <div class="form-grid">
          ${selectField('Modalidad', 'project_modality', project.project_modality, ['Proyecto de Titulación', 'Artículo Académico', 'Otra'])}
          ${field('Tema aprobado', 'topic', project.topic, 'Título o tema del trabajo')}
          ${field('Tutor asignado', 'tutor_name', project.tutor_name, 'Nombre del tutor')}
          ${selectField('Primer borrador', 'draft_1_status', project.draft_1_status, ['Entregado', 'Revisado', 'Pendiente', 'No presentado'])}
          ${selectField('Segundo borrador', 'draft_2_status', project.draft_2_status, ['Entregado', 'Revisado', 'Pendiente', 'No presentado'])}
          ${selectField('Aprobación del tutor', 'tutor_approval', project.tutor_approval, ['Aprobado', 'Con observaciones', 'No aprobado', 'Pendiente'])}
          ${field('Resultado antiplagio', 'plagiarism_result', project.plagiarism_result, 'Ej.: 8 % de similitud / aprobado')}
          ${selectField('Habilitación para defensa', 'defense_eligible', project.defense_eligible, ['Habilitado', 'No habilitado', 'Pendiente'])}
          ${selectField('Defensa supletoria', 'supplementary_defense', project.supplementary_defense, ['No requerida', 'Programada', 'Rendida', 'Aprobada', 'Reprobada'])}
          ${selectField('Estado del proceso', 'process_status', project.process_status, ['Aprobado', 'Reprobado', 'Retirado', 'No presentado', 'En proceso'])}
        </div>
        <div class="form-actions"><button class="button primary small" type="submit">Guardar seguimiento</button></div>
      </form>
    </details>`;
  }

  async function enhanceProjects() {
    const reportId = Number(state.activeReport?.id || 0);
    const tab = document.querySelector('#tab-projects');
    if (!reportId || !tab || !tab.querySelector('.project-list')) return;
    try {
      const data = await api(`/api/reports/${reportId}/projects`);
      if (Number(state.activeReport?.id || 0) !== reportId) return;
      for (const project of data.projects || []) {
        const deleteButton = tab.querySelector(`[data-delete-project="${project.id}"]`);
        const card = deleteButton?.closest('.project-card');
        if (!card || card.querySelector(`[data-project-followup="${project.id}"]`)) continue;
        card.insertAdjacentHTML('beforeend', followupMarkup(project));
        const form = card.querySelector(`[data-project-followup-form="${project.id}"]`);
        form.addEventListener('submit', async event => {
          event.preventDefault();
          const payload = Object.fromEntries(new FormData(form).entries());
          try {
            await api(`/api/reports/${reportId}/projects/${project.id}/followup`, {
              method: 'PUT',
              body: JSON.stringify(payload),
            });
            toast('Seguimiento del Trabajo de Titulación guardado.');
          } catch (error) {
            toast(error.message, true);
          }
        });
      }
    } catch (_error) {
      // La carga principal del Trabajo de Titulación continúa disponible.
    }
  }

  const style = document.createElement('style');
  style.textContent = `
    .project-followup { margin-top: 16px; border-top: 1px solid #dbe3ec; padding-top: 12px; }
    .project-followup summary { cursor: pointer; font-weight: 700; }
    .project-followup-form { margin-top: 14px; }
  `;
  document.head.appendChild(style);

  new MutationObserver(scheduleEnhancement).observe(document.body, { childList: true, subtree: true });
  document.addEventListener('click', event => {
    if (event.target.closest('[data-tab="projects"]')) scheduleEnhancement();
  });
  scheduleEnhancement();
})();
