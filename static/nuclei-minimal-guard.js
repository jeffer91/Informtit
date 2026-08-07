(() => {
  let queued = false;

  function normalize(value = '') {
    return String(value)
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, ' ')
      .trim();
  }

  function currentMinimalRoot() {
    return document.querySelector('#tab-nuclei [data-minimal-nuclei]');
  }

  function removeLegacyNucleiLayers() {
    const tab = document.querySelector('#tab-nuclei');
    if (!tab) return;
    tab.querySelectorAll(
      '[data-eligibility-panel], [data-nuclei-catalog="active-careers"], [data-nuclei-crosscheck], [data-workflow-flow], [data-workflow-blocked], .teacher-load-panel'
    ).forEach(node => node.remove());
  }

  function keepMinimalRootIndependent() {
    const root = currentMinimalRoot();
    if (!root) return;
    root.classList.remove('process-stack');
  }

  function courseCards() {
    return [...document.querySelectorAll('#tab-nuclei [data-minimal-course]')];
  }

  function rebuildCampusFilter() {
    const tab = document.querySelector('#tab-nuclei');
    const careerSelect = tab?.querySelector('[data-course-career-filter]');
    const campusSelect = tab?.querySelector('[data-course-campus-filter]');
    if (!tab || !careerSelect || !campusSelect) return;

    const career = normalize(careerSelect.value);
    const campuses = [];
    const seen = new Set();
    courseCards().forEach(card => {
      if (career && normalize(card.dataset.career) !== career) return;
      const campus = String(card.dataset.campus || '').trim();
      const key = normalize(campus);
      if (!campus || seen.has(key)) return;
      seen.add(key);
      campuses.push(campus);
    });
    campuses.sort((left, right) => left.localeCompare(right, 'es', { sensitivity: 'base' }));

    const signature = `${career}|${campuses.join('|')}`;
    if (campusSelect.dataset.minimalCampusSignature === signature) return;

    const previousValue = campusSelect.value;
    campusSelect.innerHTML = '<option value="">Todas</option>' + campuses
      .map(campus => `<option value="${campus.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;')}">${campus.replace(/&/g, '&amp;').replace(/</g, '&lt;')}</option>`)
      .join('');
    campusSelect.dataset.minimalCampusSignature = signature;

    const valid = [...campusSelect.options].some(option => normalize(option.value) === normalize(previousValue));
    campusSelect.value = valid ? previousValue : '';
    // Sincroniza también el estado privado de nuclei-ui. Esto evita que una
    // sede seleccionada en una carrera anterior siga ocultando todos los cursos.
    campusSelect.dispatchEvent(new Event('change', { bubbles: true }));
  }

  function enforceMinimalView() {
    keepMinimalRootIndependent();
    removeLegacyNucleiLayers();
    rebuildCampusFilter();
  }

  function schedule() {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => {
      queued = false;
      enforceMinimalView();
    });
  }

  document.addEventListener('change', event => {
    if (event.target.matches('[data-course-career-filter]')) {
      setTimeout(rebuildCampusFilter, 0);
    }
  });

  new MutationObserver(records => {
    if (records.some(record => [...record.addedNodes].some(node => {
      if (!(node instanceof Element)) return false;
      return node.matches?.('[data-minimal-nuclei], [data-eligibility-panel], [data-workflow-flow], [data-nuclei-catalog="active-careers"]')
        || Boolean(node.querySelector?.('[data-minimal-nuclei], [data-eligibility-panel], [data-workflow-flow], [data-nuclei-catalog="active-careers"]'));
    }))) schedule();
  }).observe(document.body, { childList: true, subtree: true });

  document.addEventListener('click', event => {
    if (event.target.closest('[data-tab="nuclei"]')) setTimeout(schedule, 0);
  });

  schedule();
})();
