(() => {
  const previousRenderReport = renderReport;
  renderReport = function renderReportFinal() {
    previousRenderReport();

    const fixedFields = [
      'prepared_by', 'prepared_role',
      'reviewed_by', 'reviewed_role',
      'approved_by', 'approved_role',
    ];
    fixedFields.forEach(name => {
      const input = document.querySelector(`#general-form [name="${name}"]`);
      input?.closest('label')?.remove();
    });

    const careerHeading = document.querySelector('#tab-careers .panel-head h2');
    const careerDescription = document.querySelector('#tab-careers .panel-head p');
    if (careerHeading) careerHeading.textContent = 'Resultados del Examen Complexivo';
    if (careerDescription) careerDescription.textContent = 'Pegue las notas de Moodle y revise por separado los resultados ordinarios, supletorios y consolidados.';
  };
})();
