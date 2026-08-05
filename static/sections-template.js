// Informtit 0.6: las secciones institucionales son plantillas reutilizables.
(function () {
  const modeInfo = {
    fixed: {
      label: 'Plantilla institucional',
      className: 'fixed',
      description: 'Se conserva entre períodos y solo se modifica cuando cambia la normativa o el proceso.',
    },
    periodic: {
      label: 'Actualización por período',
      className: 'periodic',
      description: 'Mantiene la estructura y permite ajustar fechas, responsables o actividades.',
    },
    generated: {
      label: 'Contenido variable',
      className: 'generated',
      description: 'Se completa con los resultados del período y debe revisarse antes de exportar.',
    },
  };

  function sectionMode(section) {
    return modeInfo[section.section_mode] || modeInfo.fixed;
  }

  function renderTemplateSection(section) {
    const mode = sectionMode(section);
    const locked = mode.className === 'fixed' && !section.customized;
    const customizedBadge = section.customized
      ? '<span class="template-badge custom">Personalizada</span>'
      : '';

    return `
      <article class="template-section-card is-${mode.className}" data-template-section="${section.id}">
        <div class="template-section-head">
          <div>
            <div class="template-section-meta">
              <h3>${escapeHtml(section.title)}</h3>
              <span class="template-badge ${mode.className}">${mode.label}</span>
              ${customizedBadge}
            </div>
            <p>${escapeHtml(mode.description)}</p>
          </div>
        </div>

        <div class="template-help">${escapeHtml(section.help_text || mode.description)}</div>

        ${mode.className === 'generated' ? `
          <div class="template-warning">
            Este texto es una base genérica. La versión definitiva debe generarse con los datos del informe y revisarse antes de exportar.
          </div>` : ''}

        ${mode.className === 'fixed' && !section.customized ? `
          <div class="template-info">
            El período y la modalidad se actualizan automáticamente desde los datos generales del informe.
          </div>` : ''}

        <label>Contenido de la sección
          <textarea name="content" ${locked ? 'readonly' : ''}>${escapeHtml(section.content || '')}</textarea>
        </label>

        <div class="template-actions">
          <label class="template-visible">
            <input type="checkbox" name="visible" ${section.visible ? 'checked' : ''}>
            Incluir en el informe
          </label>

          ${locked ? `
            <button type="button" class="button secondary small" data-customize-section="${section.id}">
              Editar excepcionalmente
            </button>` : `
            <button type="button" class="button primary small" data-save-template-section="${section.id}">
              Guardar cambios
            </button>`}

          ${section.customized ? `
            <button type="button" class="button secondary small" data-restore-template="${section.id}">
              Restaurar plantilla
            </button>` : ''}
        </div>
      </article>`;
  }

  renderSectionsTab = function () {
    const sections = state.activeReport?.sections || [];
    const tab = $('#tab-sections');
    if (!tab) return;

    tab.innerHTML = `
      <div class="panel">
        <div class="section-template-toolbar">
          <div>
            <h2>Secciones del informe</h2>
            <p>Informtit reutiliza contenido institucional genérico. El período y la modalidad se reemplazan automáticamente; solo se modifica lo que realmente haya cambiado.</p>
          </div>
          <div class="section-mode-summary">
            <span class="section-mode-chip fixed">Plantilla fija</span>
            <span class="section-mode-chip periodic">Por período</span>
            <span class="section-mode-chip generated">Con resultados</span>
          </div>
        </div>

        <div class="section-list">
          ${sections.map(renderTemplateSection).join('')}
        </div>
      </div>`;

    $$('[data-customize-section]', tab).forEach(button => {
      button.onclick = () => {
        const card = button.closest('[data-template-section]');
        const textarea = $('[name="content"]', card);
        textarea.readOnly = false;
        textarea.focus();
        button.outerHTML = `
          <button type="button" class="button primary small" data-save-template-section="${button.dataset.customizeSection}">
            Guardar personalización
          </button>`;
        bindSaveButtons(tab);
      };
    });

    bindSaveButtons(tab);

    $$('[data-restore-template]', tab).forEach(button => {
      button.onclick = async () => {
        const reportId = state.activeReport.id;
        await api(`/api/reports/${reportId}/sections/${button.dataset.restoreTemplate}`, {
          method: 'PUT',
          body: JSON.stringify({ restore_template: true }),
        });
        toast('Plantilla institucional restaurada.');
        await openReport(reportId);
      };
    });

    $$('[name="visible"]', tab).forEach(input => {
      input.onchange = async () => {
        const card = input.closest('[data-template-section]');
        await api(`/api/reports/${state.activeReport.id}/sections/${card.dataset.templateSection}`, {
          method: 'PUT',
          body: JSON.stringify({ visible: input.checked }),
        });
        toast(input.checked ? 'Sección incluida.' : 'Sección ocultada.');
      };
    });
  };

  function bindSaveButtons(root) {
    $$('[data-save-template-section]', root).forEach(button => {
      if (button.dataset.bound === '1') return;
      button.dataset.bound = '1';
      button.onclick = async () => {
        const card = button.closest('[data-template-section]');
        const content = $('[name="content"]', card).value.trim();
        if (!content) {
          toast('La sección no puede guardarse vacía. Puede ocultarla si no corresponde.', true);
          return;
        }
        button.disabled = true;
        try {
          await api(`/api/reports/${state.activeReport.id}/sections/${button.dataset.saveTemplateSection}`, {
            method: 'PUT',
            body: JSON.stringify({
              content,
              visible: $('[name="visible"]', card).checked,
            }),
          });
          toast('Sección guardada.');
          await openReport(state.activeReport.id);
        } catch (error) {
          toast(error.message, true);
        } finally {
          button.disabled = false;
        }
      };
    });
  }
})();
