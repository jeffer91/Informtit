// Las secciones institucionales se incorporan automáticamente al exportar.
renderSectionsTab = function () {};

const imageCareerSelect = document.querySelector('#image-form [name="career_id"]');
if (imageCareerSelect?.parentElement?.firstChild) {
  imageCareerSelect.parentElement.firstChild.textContent = 'Carrera';
}

(() => {
  const definitions = {
    complexive: {
      heading: 'Copiar y pegar cronograma de Núcleos y Examen Complexivo',
      help: 'Pegue únicamente las actividades de núcleos, examen complexivo y supletorio. Debe incluir actividad, fecha de inicio y fecha de fin.',
      placeholder: 'Actividad\tFecha de inicio\tFecha de fin\nNúcleo 1\t30/03/2026\t02/04/2026\nNúcleo 2\t06/04/2026\t09/04/2026\nExamen Complexivo\t20/04/2026\t24/04/2026',
      button: 'Analizar e importar cronograma de Complexivo',
      upload: 'Subir archivo de Complexivo',
    },
    thesis: {
      heading: 'Copiar y pegar cronograma de Trabajo de Titulación',
      help: 'Pegue las tres fases con sus actividades, fecha de inicio y fecha de fin. Informtit conservará cada fase por separado.',
      placeholder: 'Fase 1: Inicio y planificación\nActividad\tFecha de inicio\tFecha de fin\nInducción\t16/12/2025\t16/12/2025\n\nFase 2: Desarrollo y tutorías\nDesarrollo del trabajo\t11/02/2026\t28/02/2026',
      button: 'Analizar e importar cronograma de Trabajo de Titulación',
      upload: 'Subir archivo de Trabajo de Titulación',
    },
  };

  function enhanceCard(type) {
    const card = document.querySelector(`[data-schedule-card="${type}"]`);
    if (!card || card.dataset.copyLayoutReady === '1') return;

    const definition = definitions[type];
    const importBox = card.querySelector('.schedule-import');
    const textarea = card.querySelector(`[data-schedule-paste="${type}"]`);
    const parseButton = card.querySelector(`[data-parse-schedule="${type}"]`);
    const fileButton = card.querySelector('.file-button');

    if (!definition || !importBox || !textarea || !parseButton) return;

    card.dataset.copyLayoutReady = '1';
    importBox.classList.add('schedule-copy-section');

    const introduction = document.createElement('div');
    introduction.className = 'schedule-copy-introduction';
    introduction.innerHTML = `
      <h3>${definition.heading}</h3>
      <p>${definition.help}</p>
    `;
    importBox.prepend(introduction);

    textarea.rows = type === 'thesis' ? 14 : 10;
    textarea.placeholder = definition.placeholder;
    textarea.setAttribute('aria-label', definition.heading);
    parseButton.textContent = definition.button;

    if (fileButton) {
      const input = fileButton.querySelector('input');
      fileButton.childNodes.forEach(node => {
        if (node.nodeType === Node.TEXT_NODE) node.textContent = '';
      });
      fileButton.insertBefore(
        document.createTextNode(definition.upload),
        input || null,
      );
    }
  }

  function enhanceSchedules() {
    enhanceCard('complexive');
    enhanceCard('thesis');
  }

  const schedulesTab = document.querySelector('#tab-schedules');
  if (!schedulesTab) return;

  const style = document.createElement('style');
  style.textContent = `
    .schedule-copy-section {
      display: grid;
      grid-template-columns: 1fr;
      gap: 12px;
      padding: 18px;
      margin-bottom: 18px;
      border: 1px solid #c8d9eb;
      border-radius: 14px;
      background: #f7fbff;
    }
    .schedule-copy-introduction h3 {
      margin: 0 0 5px;
      font-size: 17px;
      color: #173f67;
    }
    .schedule-copy-introduction p {
      margin: 0;
      color: #64748b;
      line-height: 1.45;
    }
    .schedule-copy-section textarea {
      width: 100%;
      min-height: 190px;
      resize: vertical;
      font-family: Consolas, 'Courier New', monospace;
      line-height: 1.45;
    }
    .schedule-copy-section .file-button,
    .schedule-copy-section .button {
      width: fit-content;
    }
  `;
  document.head.appendChild(style);

  new MutationObserver(enhanceSchedules).observe(schedulesTab, {
    childList: true,
    subtree: true,
  });
  enhanceSchedules();
})();
