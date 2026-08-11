(() => {
  let scanQueued = false;

  function esc(value = '') {
    return String(value).replace(/[&<>"']/g, character => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;',
    })[character]);
  }

  function courseIdFromCard(card) {
    const remove = card?.querySelector('[data-delete-nucleus]');
    return Number(remove?.dataset.deleteNucleus || 0);
  }

  function courseValues(card) {
    const careerRaw = String(card?.dataset.career || '').trim();
    const campus = String(card?.dataset.campus || '').trim();
    const subtitle = card?.querySelector('.minimal-course-title span')?.textContent?.trim() || '';
    const match = subtitle.match(/^Núcleo\s+(\d+)\s*·\s*(.*)$/i);
    const nucleusNumber = match ? Number(match[1]) : 1;
    const teacherRaw = match ? match[2].trim() : '';
    return {
      careerName: /^sin carrera$/i.test(careerRaw) ? '' : careerRaw,
      campus,
      nucleusNumber,
      teacherName: /^docente pendiente$/i.test(teacherRaw) ? '' : teacherRaw,
    };
  }

  function editorMarkup(card) {
    const id = courseIdFromCard(card);
    const values = courseValues(card);
    return `
      <form class="nucleus-course-editor" data-edit-nucleus-form data-course-id="${id}">
        <div class="nucleus-course-editor-head">
          <div>
            <strong>Corregir datos del curso</strong>
            <span>La edición no modifica estudiantes ni calificaciones.</span>
          </div>
        </div>
        <div class="nucleus-course-editor-grid">
          <label>Carrera
            <input name="career_name" required value="${esc(values.careerName)}" placeholder="Ej.: Enfermería" list="nuclei-career-suggestions">
          </label>
          <label>Núcleo
            <input name="nucleus_number" required type="number" min="1" max="20" value="${values.nucleusNumber}">
          </label>
          <label>Sede
            <input name="campus" value="${esc(values.campus)}" placeholder="Ej.: Sur, Quito, Manta">
          </label>
          <label>Docente
            <input name="teacher_name" value="${esc(values.teacherName)}" placeholder="Nombre del docente">
          </label>
        </div>
        <div class="nucleus-course-editor-actions">
          <button class="button primary small" type="submit">Guardar cambios</button>
          <button class="button secondary small" type="button" data-cancel-course-edit>Cancelar</button>
        </div>
      </form>`;
  }

  function ensureCareerSuggestions() {
    if (document.querySelector('#nuclei-career-suggestions')) return;
    const list = document.createElement('datalist');
    list.id = 'nuclei-career-suggestions';
    [
      'Administración',
      'Contabilidad',
      'Desarrollo de Software',
      'Educación Inicial',
      'Educación Básica',
      'Enfermería',
      'Estética Integral',
      'Gestión del Talento Humano',
      'Marketing Digital y Comercio Electrónico',
      'Redes y Telecomunicaciones',
      'Mecánica Automotriz',
    ].forEach(name => {
      const option = document.createElement('option');
      option.value = name;
      list.appendChild(option);
    });
    document.body.appendChild(list);
  }

  function ensureEditButtons() {
    ensureCareerSuggestions();
    document.querySelectorAll('#tab-nuclei [data-minimal-course]').forEach(card => {
      const actions = card.querySelector('.minimal-course-actions');
      if (!actions || actions.querySelector('[data-edit-nucleus]')) return;
      const courseId = courseIdFromCard(card);
      if (!courseId) return;
      const button = document.createElement('button');
      button.className = 'button secondary small';
      button.type = 'button';
      button.dataset.editNucleus = String(courseId);
      button.textContent = 'Editar';
      const remove = actions.querySelector('[data-delete-nucleus]');
      actions.insertBefore(button, remove || null);
    });
  }

  function scheduleScan() {
    if (scanQueued) return;
    scanQueued = true;
    requestAnimationFrame(() => {
      scanQueued = false;
      ensureEditButtons();
    });
  }

  document.addEventListener('click', event => {
    const edit = event.target.closest('#tab-nuclei [data-edit-nucleus]');
    if (edit) {
      event.preventDefault();
      const card = edit.closest('[data-minimal-course]');
      if (!card) return;
      document.querySelectorAll('#tab-nuclei [data-edit-nucleus-form]').forEach(form => {
        if (!card.contains(form)) form.remove();
      });
      const existing = card.querySelector('[data-edit-nucleus-form]');
      if (existing) {
        existing.remove();
        edit.textContent = 'Editar';
        return;
      }
      card.querySelector('.minimal-course-main')?.insertAdjacentHTML('afterend', editorMarkup(card));
      edit.textContent = 'Cerrar edición';
      card.querySelector('[name="career_name"]')?.focus();
      return;
    }

    const cancel = event.target.closest('#tab-nuclei [data-cancel-course-edit]');
    if (cancel) {
      event.preventDefault();
      const card = cancel.closest('[data-minimal-course]');
      card?.querySelector('[data-edit-nucleus-form]')?.remove();
      const edit = card?.querySelector('[data-edit-nucleus]');
      if (edit) edit.textContent = 'Editar';
    }
  });

  document.addEventListener('submit', async event => {
    const form = event.target.closest('#tab-nuclei [data-edit-nucleus-form]');
    if (!form) return;
    event.preventDefault();

    const tab = form.closest('#tab-nuclei');
    const reportId = Number(tab?.dataset.nucleiReportId || state.activeReport?.id || 0);
    const courseId = Number(form.dataset.courseId || 0);
    if (!reportId || !courseId) {
      toast('No se pudo identificar el curso a corregir.', true);
      return;
    }

    const submit = form.querySelector('button[type="submit"]');
    if (submit?.disabled) return;
    if (submit) submit.disabled = true;

    const payload = {
      career_name: form.elements.career_name.value.trim(),
      nucleus_number: Number(form.elements.nucleus_number.value),
      campus: form.elements.campus.value.trim(),
      teacher_name: form.elements.teacher_name.value.trim(),
    };

    try {
      await api(`/api/reports/${reportId}/nuclei/${courseId}`, {
        method: 'PUT',
        body: JSON.stringify(payload),
      });
      toast('Datos del curso corregidos. Las notas se conservaron.');
      renderReport();
    } catch (error) {
      toast(error.message, true);
      if (submit && document.contains(submit)) submit.disabled = false;
    }
  });

  const style = document.createElement('style');
  style.textContent = `
    .nucleus-course-editor {
      padding: 14px 15px 15px;
      border-top: 1px solid #e2e8f0;
      background: #f8fafc;
    }
    .nucleus-course-editor-head { margin-bottom: 12px; }
    .nucleus-course-editor-head > div { display: grid; gap: 2px; }
    .nucleus-course-editor-head strong { color: #173b57; }
    .nucleus-course-editor-head span { color: #64748b; font-size: 12px; }
    .nucleus-course-editor-grid {
      display: grid;
      grid-template-columns: minmax(220px, 1.4fr) minmax(110px, .45fr) minmax(180px, .8fr) minmax(220px, 1fr);
      gap: 12px;
    }
    .nucleus-course-editor-actions { display: flex; gap: 8px; margin-top: 12px; }
    @media (max-width: 1000px) {
      .nucleus-course-editor-grid { grid-template-columns: 1fr 1fr; }
    }
    @media (max-width: 650px) {
      .nucleus-course-editor-grid { grid-template-columns: 1fr; }
    }
  `;
  document.head.appendChild(style);

  new MutationObserver(records => {
    if (records.some(record => record.addedNodes.length)) scheduleScan();
  }).observe(document.body, { childList: true, subtree: true });

  scheduleScan();
})();
