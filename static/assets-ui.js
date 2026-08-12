// Informtit 0.9: recursos visuales del PDF.
(function () {
  const PDF_SLOTS = [
    {
      section: 'logo_institucional',
      title: '1. Logo institucional ITSQMET',
      description: 'Obligatorio. Se utiliza en el encabezado institucional del PDF.',
      source: 'ITSQMET',
      required: true,
    },
    {
      section: 'infografia_complexivo',
      title: '2. Infografía del proceso de Examen Complexivo',
      description: 'Opcional. Súbala únicamente si existe una versión institucional vigente y aporta valor al informe.',
      source: 'ITSQMET',
      required: false,
    },
  ];

  // Se conservan como reservadas para que archivos antiguos no reaparezcan como evidencias.
  const LEGACY_IGNORED = new Set([
    'firma_elaborado',
    'firma_revisado',
    'firma_aprobado',
    'diagrama_nucleos',
  ]);

  function findImage(section) {
    const images = state.activeReport?.images || [];
    const matches = images.filter(image => image.section === section && !image.career_id);
    return matches.length ? matches[matches.length - 1] : null;
  }

  function slotCard(slot) {
    const image = findImage(slot.section);
    const stateLabel = image ? 'Cargada' : (slot.required ? 'Pendiente obligatoria' : 'Opcional');
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

    const requiredSlots = PDF_SLOTS.filter(slot => slot.required);
    const loadedRequired = requiredSlots.filter(slot => findImage(slot.section)).length;
    const extras = (state.activeReport?.images || []).filter(image =>
      !PDF_SLOTS.some(slot => slot.section === image.section) &&
      !LEGACY_IGNORED.has(image.section)
    );

    tab.innerHTML = `
      <div class="panel">
        <div class="panel-head asset-panel-head">
          <div>
            <h2>Imágenes del PDF</h2>
            <p>Solo se solicitan recursos que no puede generar automáticamente el informe. No se suben firmas, QR, gráficos, Ishikawa ni diagramas de Núcleos.</p>
          </div>
          <div class="asset-progress"><strong>${loadedRequired} de ${requiredSlots.length}</strong><span>imagen obligatoria cargada</span></div>
        </div>

        <div class="asset-section">
          <h3>Recursos institucionales</h3>
          <div class="asset-list">${PDF_SLOTS.map(slot => slotCard(slot)).join('')}</div>
        </div>

        <div class="asset-section">
          <div class="panel-head compact">
            <div>
              <h3>Evidencias adicionales</h3>
              <p>Opcional. Use únicamente fotografías o evidencias institucionales que aporten información que no esté ya representada en tablas, gráficos o anexos automáticos.</p>
            </div>
            <button type="button" class="button secondary" id="add-extra-image">Agregar evidencia</button>
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
              </article>`).join('') : '<div class="empty-mini">No existen evidencias adicionales.</div>'}
          </div>
        </div>
      </div>`;

    $$('[data-upload-asset]', tab).forEach(button => {
      button.onclick = () => openAssetDialog({
        section: button.dataset.uploadAsset,
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

  function openAssetDialog({ section = 'evidencia_general', title = '', description = '', source = '', replaceId = null } = {}) {
    const form = $('#image-form');
    form.reset();
    form.career_id.innerHTML = '<option value="">Imagen general</option>';
    form.career_id.value = '';
    form.section.value = section;
    form.title.value = title;
    form.description.value = description;
    form.source.value = source;
    ensureReplacementField(form).value = replaceId ?? '';
    $('#image-dialog').showModal();
  }

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
        career_id: null,
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