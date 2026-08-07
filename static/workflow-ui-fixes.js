(() => {
  let scheduled = false;

  function setText(node, value) {
    if (node && node.textContent !== value) node.textContent = value;
  }

  function patchWorkflowUi() {
    const panel = document.querySelector('[data-eligibility-panel]');
    if (panel) {
      const description = panel.querySelector('.panel-head p');
      setText(
        description,
        'Primero se validan los ocho requisitos previos para ingresar a Núcleos. Después, únicamente quienes aprueban los cuatro núcleos con mínimo 7,00 quedan habilitados para rendir el Examen Complexivo.',
      );

      const resultHeading = [...panel.querySelectorAll('h3')]
        .find(node => node.textContent.trim() === 'Resultado por carrera');
      const resultTable = resultHeading?.nextElementSibling?.querySelector('table');
      if (resultTable) {
        const headers = resultTable.querySelectorAll('thead th');
        setText(headers[1], 'Ingresaron a Núcleos');
        setText(headers[2], 'Habilitados Complexivo');
        setText(headers[3], 'Núcleos reprobados');
        setText(headers[4], 'Núcleos pendientes');
      }

      const steps = panel.querySelectorAll('.workflow-steps article');
      if (steps[2]) {
        setText(steps[2].querySelector('strong'), 'Aprobación Complexivo/Proyecto');
      }
    }

    const warning = document.querySelector('[data-complexive-eligibility-warning]');
    if (warning?.classList.contains('has-conflicts')) {
      const paragraph = warning.querySelector('.panel-head p');
      const match = paragraph?.textContent.match(/\d+/);
      const count = match ? match[0] : '';
      setText(
        paragraph,
        `Se encontraron ${count || 'uno o más'} registro(s) con notas de Complexivo sin completar la secuencia obligatoria de ocho requisitos previos y cuatro núcleos aprobados.`,
      );
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

  new MutationObserver(records => {
    const relevant = records.some(record => [...record.addedNodes].some(node => {
      if (!(node instanceof Element)) return false;
      return node.matches?.('[data-eligibility-panel], [data-complexive-eligibility-warning], .workflow-flow')
        || Boolean(node.querySelector?.('[data-eligibility-panel], [data-complexive-eligibility-warning], .workflow-flow'));
    }));
    if (relevant) schedule();
  }).observe(document.body, { childList: true, subtree: true });

  document.addEventListener('click', event => {
    if (event.target.closest('[data-tab="nuclei"], [data-tab="careers"]')) {
      setTimeout(schedule, 80);
    }
  });
  schedule();
})();
