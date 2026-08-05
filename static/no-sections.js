// Las secciones institucionales se incorporan automáticamente al exportar.
renderSectionsTab = function () {};

const imageCareerSelect = document.querySelector('#image-form [name="career_id"]');
if (imageCareerSelect?.parentElement?.firstChild) {
  imageCareerSelect.parentElement.firstChild.textContent = 'Carrera';
}
