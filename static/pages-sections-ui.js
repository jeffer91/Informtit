(() => {
  'use strict';

  if (!/(^|\.)github\.io$/i.test(window.location.hostname)) return;

  window.renderSectionsTab = function renderPagesSectionsState() {
    const tab = document.querySelector('#tab-sections');
    if (!tab) return;
    tab.innerHTML = `
      <section class="panel">
        <div class="panel-head">
          <div>
            <h2>Secciones documentales</h2>
            <p>La edición modular de secciones todavía no está habilitada en la versión productiva de GitHub Pages.</p>
          </div>
        </div>
        <div class="empty-mini">La información institucional se consolida actualmente desde los módulos de datos y el generador PDF. Este espacio queda reservado para el motor Documento → Secciones.</div>
      </section>`;
  };

  const imageCareerSelect = document.querySelector('#image-form [name="career_id"]');
  if (imageCareerSelect?.parentElement?.firstChild) {
    imageCareerSelect.parentElement.firstChild.textContent = 'Carrera';
  }
})();
