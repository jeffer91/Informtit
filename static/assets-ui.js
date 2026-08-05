// Informtit 0.8: banco guiado de imágenes según los informes institucionales anteriores.
(function () {
  const GENERAL_SLOTS = [
    {
      section: 'logo_institucional',
      title: '1. Logo institucional ITSQMET',
      description: 'Obligatorio. Se coloca en el encabezado de la portada y de todas las páginas.',
      source: 'ITSQMET',
      required: true,
    },
    {
      section: 'firma_elaborado',
      title: '2. Firma o QR de Elaborado por',
      description: 'Obligatorio. Se incorpora en el bloque inferior de la portada.',
      source: 'Firma electrónica institucional',
      required: true,
    },
    {
      section: 'firma_revisado',
      title: '3. Firma o QR de Revisado por',
      description: 'Obligatorio. Se incorpora en el bloque inferior de la portada.',
      source: 'Firma electrónica institucional',
      required: true,
    },
    {
      section: 'firma_aprobado',
      title: '4. Firma o QR de Aprobado por',
      description: 'Obligatorio. Se incorpora en el bloque inferior de la portada.',
      source: 'Firma electrónica institucional',
      required: true,
    },
    {
      section: 'infografia_complexivo',
      title: '5. Infografía del proceso de examen complexivo',
      description: 'Obligatoria para reproducir el apartado visual del proceso de titulación.',
      source: 'ITSQMET',
      required: true,
    },
  ];

  function findImage(section, careerId = null) {
    const images = state.activeReport?.images || [];
    const matches = images.filter(image =>
      image.section === section &&
      (careerId === null ? !image.career_id : Number(image.career_id) === Number(careerId))
    );
    return matches.length ? matches[matches.length - 1] : null;
  }

  function slotCard(slot, careerId = null) {
    const image = findImage(slot.section, careerId);
    const stateLabel = image ? 'Cargada' : (slot.required ? 'Pendiente obligatoria' : 'Pendiente');
    const stateClass = image ? 'ready' : 'pending';
    return `
      <article class="asset-slot ${stateClass}">
        <div class="asset-preview">
          ${image
            ? `<img src="/uploads/${image.filename}" alt="${escapeHtml(slot.title)}">`
            : '<div class="asset-placeholder">Sin imagen</div>'}
        </div>
        <div class="asset-slot-body">
          <div class="asset-slot-title">
            <h3>${escapeHtml(slot.title)}</h3>
            <span class="asset-state ${stateClass}">${stateLabel}</span>
          </div>
          <p>${escapeHtml(slot.description)}</p>
          <div class="asset-actions">
            <button type="button" class="button primary small"
              data-upload-asset="${escapeHtml(slot.section)}"
              data-career-id="${careerId ?? ''}"
              data-title="${escapeHtml(slot.title.replace(/^\d+\.\s*/, ''))}"
              data-description="${escapeHtml(slot.description)}"
              data-source="${escapeHtml(slot.source || '')}"
              data-replace-id="${image?.id || ''}">
              ${image ? 'Reemplazar' : 'Subir imagen'}
            </button>
            ${image ? `<button type="button" class="button danger small" data-delete-image="${image.id}">Eliminar</button>` : ''}
          </div>
        </div>
      </article>`;
  }

  renderImagesTab = function () {
    const tab = $('#tab-images');
    if (!tab) return;
    const careers = state.activeReport?.careers || [];
    const requiredTotal = GENERAL_SLOTS.length + careers.length;
    const loadedTotal = GENERAL_SLOTS.filter(slot => findImage(slot.section)).length +
      careers.filter(career => findImage('diagrama_nucleos', career.id)).length;

    const careerSlots = careers.map((career, index) => slotCard({
      section: 'diagrama_nucleos',
      title: `${GENERAL_SLOTS.length + index + 1}. Diagrama de núcleos - ${career.name}`,
      description: `Diagrama visual de los cuatro núcleos estructurantes de la carrera de ${career.name}.`,
      source: 'Elaboración institucional',
      required: true,
    }, career.id)).join('');

    const extras = (state.activeReport?.images || []).filter(image =>
      !GENERAL_SLOTS.some(slot => slot.section === image.section) &&
      image.section !== 'diagrama_nucleos'
    );

    tab.innerHTML = `
      <div class="panel">
        <div class="panel-head asset-panel-head">
          <div>
            <h2>Imágenes requeridas para el informe</h2>
            <p>La lista reproduce los elementos visuales utilizados en los informes institucionales anteriores. Debe comenzar con el logo.</p>
          </div>
          <div class="asset-progress"><strong>${loadedTotal} de ${requiredTotal}</strong><span>imágenes requeridas cargadas</span></div>
        </div>

        <div class="asset-section">
          <h3>Imágenes institucionales y de portada</h3>
          <div class="asset-list">${GENERAL_SLOTS.map(slot => slotCard(slot)).join('')}</div>
        </div>

        <div class="asset-section">
          <h3>Diagramas de núcleos por carrera</h3>
          <p>Los informes anteriores muestran un diagrama visual por cada carrera. Estos archivos se insertarán antes del contenido y resultados de la carrera correspondiente.</p>
          <div class="asset-list">${careerSlots || '<div class="empty-mini">Importe primero la base de estudiantes para generar la lista de carreras.</div>'}</div>
        </div>

        <div class="asset-section">
          <div class="panel-head compact">
            <div><h3>Imágenes adicionales</h3><p>Evidencias, fotografías, capturas u otros recursos que no formen parte de la plantilla obligatoria.</p></div>
            <button type="button" class="button secondary" id="add-extra-image">Agregar imagen adicional</button>
          </div>
          <div class="image-grid">
            ${extras.length ? extras.map(image => `
              <article class="image-card">
                <img src="/uploads/${image.filename}" alt="${escapeHtml(image.title || image.original_name)}">
                <div class="image-card-body">
                  <h4>${escapeHtml(image.title || image.original_name)}</h4>
                  <p>${escapeHtml(image.description || 'Sin descripción')}</p>
                  <button class="button danger small" data-delete-image="${image.id}">Eliminar</button>
                </div>
              </article>`).join('') : '<div class="empty-mini">No existen imágenes adicionales.</div>'}
          </div>
        </div>
      </div>`;

    $$('[data-upload-asset]', tab).forEach(button => {
      button.onclick = () => openAssetDialog({
        section: button.dataset.uploadAsset,
        careerId: button.dataset.careerId ? Number(button.dataset.careerId) : null,
        title: button.dataset.title,
        description: button.dataset.description,
        source: button.dataset.source,
        replaceId: button.dataset.replaceId ? Number(button.dataset.replaceId) : null,
      });
    });
    $$('[data-delete-image]', tab).forEach(button => button.onclick = () => deleteImage(Number(button.dataset.deleteImage)));
    $('#add-extra-image', tab).onclick = () => openAssetDialog({ section: 'evidencia_general' });
  };

  function ensureReplacementField(form) {
    let input = form.querySelector('[name="replace_image_id"]');
    if (!input) {
      input = document.createElement('input');
      input.type = 'hidden';
      input.name = 'replace_image_id';
      form.appendChild(input);
    }
    return input;
  }

  function openAssetDialog({ section = 'evidencia_general', careerId = null, title = '', description = '', source = '', replaceId = null } = {}) {
    const form = $('#image-form');
    form.reset();
    form.career_id.innerHTML = '<option value="">Imagen general</option>' +
      (state.activeReport.careers || []).map(c => `<option value="${c.id}">${escapeHtml(c.name)}</option>`).join('');
    form.career_id.value = careerId ?? '';
    form.section.value = section;
    form.title.value = title;
    form.description.value = description;
    form.source.value = source;
    ensureReplacementField(form).value = replaceId ?? '';
    $('#image-dialog').showModal();
  }

  // Intercepta el envío antiguo para permitir reemplazar una imagen del mismo espacio.
  $('#image-form').addEventListener('submit', async event => {
    event.preventDefault();
    event.stopImmediatePropagation();
    const form = event.currentTarget;
    const file = form.file.files[0];
    if (!file) {
      toast('Seleccione una imagen.', true);
      return;
    }
    const submit = form.querySelector('button[value="default"]');
    if (submit) submit.disabled = true;
    try {
      const dataURL = await fileToDataURL(file);
      const payload = {
        data_url: dataURL,
        original_name: file.name,
        title: form.title.value,
        description: form.description.value,
        source: form.source.value,
        career_id: form.career_id.value ? Number(form.career_id.value) : null,
        section: form.section.value || 'evidencia_general',
      };
      await api(`/api/reports/${state.activeReport.id}/images`, { method: 'POST', body: JSON.stringify(payload) });
      const replaceId = Number(ensureReplacementField(form).value || 0);
      if (replaceId) await api(`/api/images/${replaceId}`, { method: 'DELETE' });
      $('#image-dialog').close();
      toast(replaceId ? 'Imagen reemplazada.' : 'Imagen agregada.');
      await openReport(state.activeReport.id);
    } catch (error) {
      toast(error.message, true);
    } finally {
      if (submit) submit.disabled = false;
    }
  }, true);
})();
