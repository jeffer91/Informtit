(() => {
  const CATALOG = {
    career: 'ESTÉTICA INTEGRAL',
    nuclei: [
      {
        number: 1,
        guide: 'QUÍMICA COSMETICA Y CIENCIAS DERMATOCOSMÉTICAS',
        subjects: ['QUIMÍCA COSMETICA', 'COSMIATRÍA', 'DERMOCOSMETICA'],
      },
      {
        number: 2,
        guide: 'FUNDAMENTOS DEL DIAGNOSTICO Y TRATAMIENTOS ESTÉTICO',
        subjects: ['CUIDADO DE LA PIEL', 'VALORACIÓN ESTÉTICA', 'APARATOLOGÍA EN ESTÉTICA'],
      },
      {
        number: 3,
        guide: 'ABORDAJE INTEGRAL EN TERAPIAS FACIALES Y ESTÉTICAS',
        subjects: ['TERAPIAS FACIALES', 'TERAPEUTICA EN ESTÉTICA', 'TERAPIAS ESTÉTICAS INTEGRALES'],
      },
      {
        number: 4,
        guide: 'TERAPIAS CORPORALES INTEGRALES Y PRACTICAS SOSTENIBLES',
        subjects: ['MASAJES Y TERAPIAS CORPORALES', 'TERAPIAS ALTERNATIVAS', 'TERAPIA Y MANEJO DE DESECHOS'],
      },
    ],
  };

  function normalize(value = '') {
    return String(value)
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, ' ')
      .trim();
  }

  function escapeLocal(value = '') {
    return typeof escapeHtml === 'function'
      ? escapeHtml(String(value))
      : String(value).replace(/[&<>"']/g, character => ({
          '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;',
        })[character]);
  }

  function hasEstheticsCareer() {
    return (state.activeReport?.careers || []).some(career =>
      normalize(career.name).includes('estetica integral')
    );
  }

  function catalogMarkup() {
    return `
      <section class="panel nuclei-catalog-panel" data-nuclei-catalog="estetica-integral">
        <div class="panel-head">
          <div>
            <h2>Contenido académico de los núcleos</h2>
            <p>Este contenido se incorporará al informe únicamente porque Estética Integral forma parte de la cohorte activa.</p>
          </div>
        </div>
        <article class="career-card nuclei-catalog-card">
          <div class="career-head">
            <div>
              <span class="badge">4 núcleos</span>
              <h3>${escapeLocal(CATALOG.career)}</h3>
              <p>Cada guía agrupa tres asignaturas de la carrera.</p>
            </div>
          </div>
          <div class="nuclei-cycle-preview">
            ${CATALOG.nuclei.map(nucleus => `
              <div class="nucleus-cycle-node">
                <strong>Núcleo ${nucleus.number}</strong>
                <span>${escapeLocal(nucleus.guide)}</span>
              </div>
            `).join('')}
          </div>
          <div class="nuclei-guide-grid">
            ${CATALOG.nuclei.map(nucleus => `
              <section class="nuclei-guide-card">
                <span class="badge">Núcleo ${nucleus.number}</span>
                <h4>${escapeLocal(nucleus.guide)}</h4>
                <ul>${nucleus.subjects.map(subject => `<li>${escapeLocal(subject)}</li>`).join('')}</ul>
              </section>
            `).join('')}
          </div>
        </article>
      </section>`;
  }

  function renderCatalog() {
    const tab = document.querySelector('#tab-nuclei');
    if (!tab || !state.activeReport?.id) return;
    const existing = tab.querySelector('[data-nuclei-catalog="estetica-integral"]');
    if (!hasEstheticsCareer()) {
      existing?.remove();
      return;
    }
    if (existing) return;
    const stack = tab.querySelector('.process-stack');
    if (stack) stack.insertAdjacentHTML('beforeend', catalogMarkup());
  }

  const style = document.createElement('style');
  style.textContent = `
    .nuclei-catalog-panel { margin-top: 18px; }
    .nuclei-cycle-preview {
      display: grid;
      grid-template-columns: repeat(2, minmax(220px, 1fr));
      gap: 14px;
      margin: 18px 0;
      padding: 18px;
      border: 1px dashed #d8a557;
      border-radius: 18px;
      background: #fffaf1;
    }
    .nucleus-cycle-node {
      min-height: 112px;
      display: flex;
      flex-direction: column;
      justify-content: center;
      gap: 7px;
      padding: 16px;
      text-align: center;
      border: 1px solid #c98a32;
      border-radius: 999px;
      background: #f7d49d;
    }
    .nucleus-cycle-node span { font-size: 13px; line-height: 1.35; }
    .nuclei-guide-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(240px, 1fr));
      gap: 14px;
    }
    .nuclei-guide-card {
      padding: 16px;
      border: 1px solid #dbe3ec;
      border-radius: 14px;
      background: #ffffff;
    }
    .nuclei-guide-card h4 { margin: 10px 0; line-height: 1.35; }
    .nuclei-guide-card ul { margin: 0; padding-left: 20px; }
    @media (max-width: 900px) {
      .nuclei-cycle-preview, .nuclei-guide-grid { grid-template-columns: 1fr; }
    }
  `;
  document.head.appendChild(style);

  new MutationObserver(renderCatalog).observe(document.body, { childList: true, subtree: true });
  document.addEventListener('click', event => {
    if (event.target.closest('[data-tab="nuclei"]')) setTimeout(renderCatalog, 0);
  });
  renderCatalog();
})();
