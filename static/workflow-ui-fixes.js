(() => {
  let scheduled = false;

  function patchWorkflowUi() {
    const panel = document.querySelector('[data-eligibility-panel]');
    if (panel) {
      const description = panel.querySelector('.panel-head p');
      if (description) {
        description.textContent = 'Primero se validan los ocho requisitos previos para ingresar a Núcleos. Después, únicamente quienes aprueban los cuatro núcleos con mínimo 7,00 quedan habilitados para rendir el Examen Complexivo.';
      }

      const resultHeading = [...panel.querySelectorAll('h3')]
        .find(node => node.textContent.trim() === 'Resultado por carrera');
      const resultTable = resultHeading?.nextElementSibling?.querySelector('table');
      if (resultTable) {
        const headers = resultTable.querySelectorAll('thead th');
        if (headers[1]) headers[1].textContent = 'Ingresaron a Núcleos';
        if (headers[2]) headers[2].textContent = 'Habilitados Complexivo';
        if (headers[3]) headers[3].textContent = 'Núcleos reprobados';
        if (headers[4]) headers[4].textContent = 'Núcleos pendientes';
      }

      const steps = panel.querySelectorAll('.workflow-steps article');
      if (steps[2]) {
        const title = steps[2].querySelector('strong');
        if (title) title.textContent = 'Aprobación Complexivo/Proyecto';
      }
    }

    const warning = document.querySelector('[data-complexive-eligibility-warning]');
    if (warning?.classList.contains('has-conflicts')) {
      const paragraph = warning.querySelector('.panel-head p');
      if (paragraph) {
        const match = paragraph.textContent.match(/\d+/);
        const count = match ? match[0] : '';
        paragraph.textContent = `Se encontraron ${count || 'uno o más'} registro(s) con notas de Complexivo sin completar la secuencia obligatoria de ocho requisitos previos y cuatro núcleos aprobados.`;
      }
    }
  }

  function schedule() {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => {
      scheduled = false;
      patchWorkflowUi();
    });
  }

  new MutationObserver(schedule).observe(document.body, { childList: true, subtree: true });
  document.addEventListener('click', event => {
    if (event.target.closest('[data-tab="nuclei"], [data-tab="careers"]')) {
      setTimeout(schedule, 80);
    }
  });
  schedule();
})();
