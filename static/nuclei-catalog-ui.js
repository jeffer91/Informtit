(() => {
  const CATALOGS = [
    ['Administración', ['Gestión estratégica', 'Gestión de procesos y calidad', 'Gestión financiera', 'Gestión comercial']],
    ['Contabilidad', ['Contabilidad financiera', 'Contabilidad de costos', 'Tributación', 'Gestión financiera']],
    ['Desarrollo de Software', ['Programación orientada a objetos', 'Implementación y gestión de base de datos', 'Desarrollo de aplicaciones móviles', 'Aplicaciones web']],
    ['Educación Inicial', ['Desarrollo integral', 'Gerencia pedagógica', 'Planificación curricular', 'Habilidades neurolingüísticas']],
    ['Educación Básica', ['Psicología y neuroeducación en el entorno educativo', 'Fundamentos teórico-prácticos de la educación', 'Planificación y diseño curricular', 'Aprendizaje y enseñanza en Educación Básica']],
    ['Enfermería', ['Enfermería en promoción y prevención de la salud', 'Práctica clínica en enfermería', 'Enfermería técnica y comunitaria', 'Enfermería para el cuidado integral de pacientes']],
    ['Estética Integral', ['Química cosmética y ciencias dermatocosméticas', 'Fundamentos del diagnóstico y tratamientos estéticos', 'Abordaje integral en terapias faciales y estéticas', 'Terapias corporales integrales y prácticas sostenibles']],
    ['Gestión del Talento Humano', ['Administración de la compensación y beneficios laborales', 'Atracción y gestión del talento humano', 'Salud y bienestar de talento humano', 'Evaluación organizacional']],
    ['Marketing Digital y Comercio Electrónico', ['Bases del marketing', 'El consumidor', 'Comunicación', 'Acción del marketing']],
    ['Redes y Telecomunicaciones', ['Sistemas de transmisión de datos', 'Redes LAN y WAN', 'Sistemas operativos y servidores', 'Administración, seguridad y auditoría de redes']],
  ].map(([career, guides]) => ({
    career,
    nuclei: guides.map((guide, index) => ({ number: index + 1, guide })),
  }));

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

  function activeCatalogs() {
    const names = (state.activeReport?.careers || []).map(career => normalize(career.name));
    return CATALOGS.filter(catalog => {
      const key = normalize(catalog.career);
      return names.some(name => name === key || name.includes(key) || key.includes(name));
    });
  }

  function careerMarkup(catalog) {
    return `<article class="career-card nuclei-catalog-card">
      <div class="career-head">
        <div>
          <span class="badge">4 núcleos</span>
          <h3>${escapeLocal(catalog.career)}</h3>
          <p>Vista previa de la estructura que se incorporará al informe.</p>
        </div>
      </div>
      <div class="nuclei-cycle-preview">
        ${catalog.nuclei.map(nucleus => `<div class="nucleus-cycle-node">
          <strong>Núcleo ${nucleus.number}</strong>
          <span>${escapeLocal(nucleus.guide)}</span>
        </div>`).join('')}
      </div>
    </article>`;
  }

  function signatureFor(catalogs) {
    return catalogs.map(catalog => normalize(catalog.career)).join('|');
  }

  function catalogMarkup(catalogs, signature) {
    return `<section class="panel nuclei-catalog-panel" data-nuclei-catalog="active-careers" data-catalog-signature="${escapeLocal(signature)}">
      <div class="panel-head">
        <div>
          <h2>Contenido académico de los núcleos</h2>
          <p>Se muestran únicamente las carreras importadas en el informe activo. El Word y PDF generan un gráfico uniforme para cada carrera.</p>
        </div>
      </div>
      <div class="nuclei-catalog-list">${catalogs.map(careerMarkup).join('')}</div>
    </section>`;
  }

  function renderCatalog() {
    const tab = document.querySelector('#tab-nuclei');
    if (!tab || !state.activeReport?.id) return;
    const existing = tab.querySelector('[data-nuclei-catalog="active-careers"]');
    const catalogs = activeCatalogs();
    if (!catalogs.length) {
      existing?.remove();
      return;
    }
    const signature = signatureFor(catalogs);
    if (existing?.dataset.catalogSignature === signature) return;
    const markup = catalogMarkup(catalogs, signature);
    if (existing) {
      existing.outerHTML = markup;
      return;
    }
    const stack = tab.querySelector('.process-stack');
    if (stack) stack.insertAdjacentHTML('beforeend', markup);
  }

  const style = document.createElement('style');
  style.textContent = `
    .nuclei-catalog-panel { margin-top: 18px; }
    .nuclei-catalog-list { display: grid; gap: 16px; }
    .nuclei-cycle-preview {
      display: grid;
      grid-template-columns: repeat(2, minmax(220px, 1fr));
      gap: 14px;
      margin-top: 18px;
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
      padding: 16px 20px;
      text-align: center;
      border: 1px solid #c98a32;
      border-radius: 24px;
      background: #f7d49d;
    }
    .nucleus-cycle-node span { font-size: 13px; line-height: 1.35; overflow-wrap: anywhere; }
    @media (max-width: 900px) { .nuclei-cycle-preview { grid-template-columns: 1fr; } }
  `;
  document.head.appendChild(style);

  new MutationObserver(renderCatalog).observe(document.body, { childList: true, subtree: true });
  document.addEventListener('click', event => {
    if (event.target.closest('[data-tab="nuclei"]')) setTimeout(renderCatalog, 0);
  });
  renderCatalog();
})();
