(() => {
  const PAGE_SIZE = 15;
  let selectedCareer = '';
  let enhancementQueued = false;
  const pagesByCareer = new Map();

  function normalize(value = '') {
    return String(value)
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, ' ')
      .trim();
  }

  function esc(value = '') {
    return typeof escapeHtml === 'function'
      ? escapeHtml(String(value))
      : String(value).replace(/[&<>"']/g, character => ({
          '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;',
        })[character]);
  }

  function compareText(left, right) {
    return String(left || '').localeCompare(String(right || ''), 'es', { sensitivity: 'base' });
  }

  function uniqueCareers(values) {
    const seen = new Map();
    values.forEach(value => {
      const clean = String(value || '').trim();
      const key = normalize(clean);
      if (key && !seen.has(key)) seen.set(key, clean);
    });
    return [...seen.values()].sort(compareText);
  }

  function resolveCareer(careers, requested = selectedCareer) {
    const requestedKey = normalize(requested);
    return careers.find(career => normalize(career) === requestedKey) || careers[0] || '';
  }

  function announceCareer(career, source = '') {
    if (!career) return;
    selectedCareer = career;
    window.dispatchEvent(new CustomEvent('informtit:nuclei-career-change', {
      detail: { career, source },
    }));
  }

  function optionsMarkup(careers, selected) {
    return careers.map(career => `<option value="${esc(career)}" ${normalize(career) === normalize(selected) ? 'selected' : ''}>${esc(career)}</option>`).join('');
  }

  function enhanceCatalog() {
    const panel = document.querySelector('[data-nuclei-catalog="active-careers"]');
    const list = panel?.querySelector('.nuclei-catalog-list');
    if (!panel || !list) return;
    const cards = [...list.querySelectorAll('.nuclei-catalog-card')];
    if (!cards.length) return;

    cards.forEach(card => {
      if (!card.dataset.catalogCareer) {
        card.dataset.catalogCareer = card.querySelector('h3')?.textContent?.trim() || '';
      }
    });
    const careers = uniqueCareers(cards.map(card => card.dataset.catalogCareer));
    const career = resolveCareer(careers);
    selectedCareer = career;

    let toolbar = panel.querySelector('[data-catalog-career-toolbar]');
    if (!toolbar) {
      toolbar = document.createElement('div');
      toolbar.className = 'career-page-toolbar catalog-career-toolbar';
      toolbar.dataset.catalogCareerToolbar = '1';
      list.before(toolbar);
    }
    toolbar.innerHTML = `
      <button class="button secondary small" type="button" data-catalog-career-prev>← Carrera</button>
      <label>Contenido de la carrera
        <select data-catalog-career-select>${optionsMarkup(careers, career)}</select>
      </label>
      <button class="button secondary small" type="button" data-catalog-career-next>Carrera →</button>
      <span class="career-page-counter" data-catalog-career-counter></span>`;

    const select = toolbar.querySelector('[data-catalog-career-select]');
    const previous = toolbar.querySelector('[data-catalog-career-prev]');
    const next = toolbar.querySelector('[data-catalog-career-next]');
    const counter = toolbar.querySelector('[data-catalog-career-counter]');

    function apply(nextCareer, notify = false) {
      const resolved = resolveCareer(careers, nextCareer);
      const key = normalize(resolved);
      cards.forEach(card => {
        card.hidden = normalize(card.dataset.catalogCareer) !== key;
      });
      const index = careers.findIndex(item => normalize(item) === key);
      select.value = resolved;
      previous.disabled = index <= 0;
      next.disabled = index >= careers.length - 1;
      counter.textContent = `Carrera ${index + 1} de ${careers.length}`;
      if (notify) announceCareer(resolved, 'catalog');
    }

    select.onchange = () => apply(select.value, true);
    previous.onclick = () => {
      const index = careers.findIndex(item => normalize(item) === normalize(select.value));
      if (index > 0) apply(careers[index - 1], true);
    };
    next.onclick = () => {
      const index = careers.findIndex(item => normalize(item) === normalize(select.value));
      if (index < careers.length - 1) apply(careers[index + 1], true);
    };
    panel._applyCatalogCareer = apply;
    apply(career);
  }

  function enhanceEligibility() {
    const panel = document.querySelector('[data-eligibility-panel]');
    const details = panel?.querySelector('.eligibility-details');
    const table = details?.querySelector('.eligibility-table');
    if (!panel || !details || !table) return;
    const rows = [...table.querySelectorAll('tbody tr')];
    if (!rows.length) return;

    rows.forEach(row => {
      const cells = row.querySelectorAll('td');
      row.dataset.eligibilityCareer = cells[2]?.textContent?.trim() || '';
      row.dataset.eligibilitySearch = `${cells[0]?.textContent || ''} ${cells[1]?.textContent || ''} ${cells[2]?.textContent || ''}`.toLowerCase();
    });
    const careers = uniqueCareers(rows.map(row => row.dataset.eligibilityCareer));
    const career = resolveCareer(careers);
    selectedCareer = career;

    const originalFilter = details.querySelector('.eligibility-filter');
    if (originalFilter) originalFilter.hidden = true;

    let toolbar = details.querySelector('[data-eligibility-career-toolbar]');
    if (!toolbar) {
      toolbar = document.createElement('div');
      toolbar.className = 'eligibility-career-browser';
      toolbar.dataset.eligibilityCareerToolbar = '1';
      const tableWrap = table.closest('.student-table-wrap');
      tableWrap.before(toolbar);
    }
    toolbar.innerHTML = `
      <div class="career-page-toolbar">
        <button class="button secondary small" type="button" data-eligibility-career-prev>← Carrera</button>
        <label>Carrera
          <select data-eligibility-career-select>${optionsMarkup(careers, career)}</select>
        </label>
        <button class="button secondary small" type="button" data-eligibility-career-next>Carrera →</button>
        <span class="career-page-counter" data-eligibility-career-counter></span>
      </div>
      <div class="student-page-toolbar">
        <label>Buscar en la carrera
          <input type="search" data-eligibility-career-search placeholder="Cédula o nombre del estudiante">
        </label>
        <button class="button secondary small" type="button" data-eligibility-page-prev>← Página</button>
        <span class="student-page-counter" data-eligibility-page-counter></span>
        <button class="button secondary small" type="button" data-eligibility-page-next>Página →</button>
      </div>`;

    const select = toolbar.querySelector('[data-eligibility-career-select]');
    const careerPrevious = toolbar.querySelector('[data-eligibility-career-prev]');
    const careerNext = toolbar.querySelector('[data-eligibility-career-next]');
    const careerCounter = toolbar.querySelector('[data-eligibility-career-counter]');
    const search = toolbar.querySelector('[data-eligibility-career-search]');
    const pagePrevious = toolbar.querySelector('[data-eligibility-page-prev]');
    const pageNext = toolbar.querySelector('[data-eligibility-page-next]');
    const pageCounter = toolbar.querySelector('[data-eligibility-page-counter]');
    const detailsSummary = details.querySelector('summary');

    function currentPageKey(currentCareer) {
      return normalize(currentCareer);
    }

    function apply(nextCareer, requestedPage = null, notify = false) {
      const resolved = resolveCareer(careers, nextCareer);
      const key = normalize(resolved);
      const query = search.value.trim().toLowerCase();
      const matching = rows.filter(row =>
        normalize(row.dataset.eligibilityCareer) === key
        && (!query || row.dataset.eligibilitySearch.includes(query))
      );
      const pageCount = Math.max(1, Math.ceil(matching.length / PAGE_SIZE));
      const pageKey = currentPageKey(resolved);
      const previousPage = pagesByCareer.get(pageKey) || 1;
      const page = Math.min(Math.max(requestedPage ?? previousPage, 1), pageCount);
      pagesByCareer.set(pageKey, page);
      const start = (page - 1) * PAGE_SIZE;
      const visible = new Set(matching.slice(start, start + PAGE_SIZE));
      rows.forEach(row => { row.hidden = !visible.has(row); });

      const careerIndex = careers.findIndex(item => normalize(item) === key);
      select.value = resolved;
      careerPrevious.disabled = careerIndex <= 0;
      careerNext.disabled = careerIndex >= careers.length - 1;
      pagePrevious.disabled = page <= 1;
      pageNext.disabled = page >= pageCount;
      careerCounter.textContent = `Carrera ${careerIndex + 1} de ${careers.length}`;
      pageCounter.textContent = matching.length
        ? `Página ${page} de ${pageCount} · ${start + 1}-${Math.min(start + PAGE_SIZE, matching.length)} de ${matching.length}`
        : 'Sin estudiantes que coincidan';
      detailsSummary.textContent = `Matriz individual — ${resolved} (${matching.length} estudiantes)`;
      table.classList.add('career-paged-table');
      if (notify) announceCareer(resolved, 'eligibility');
    }

    select.onchange = () => {
      search.value = '';
      apply(select.value, 1, true);
    };
    careerPrevious.onclick = () => {
      const index = careers.findIndex(item => normalize(item) === normalize(select.value));
      if (index > 0) {
        search.value = '';
        apply(careers[index - 1], 1, true);
      }
    };
    careerNext.onclick = () => {
      const index = careers.findIndex(item => normalize(item) === normalize(select.value));
      if (index < careers.length - 1) {
        search.value = '';
        apply(careers[index + 1], 1, true);
      }
    };
    search.oninput = () => apply(select.value, 1);
    pagePrevious.onclick = () => apply(select.value, (pagesByCareer.get(currentPageKey(select.value)) || 1) - 1);
    pageNext.onclick = () => apply(select.value, (pagesByCareer.get(currentPageKey(select.value)) || 1) + 1);

    panel.querySelectorAll('h3 + .student-table-wrap table tbody tr').forEach(summaryRow => {
      const summaryCareer = summaryRow.querySelector('td')?.textContent?.trim();
      if (!summaryCareer || summaryRow.dataset.careerShortcutBound === '1') return;
      summaryRow.dataset.careerShortcutBound = '1';
      summaryRow.classList.add('career-summary-shortcut');
      summaryRow.title = 'Abrir matriz de esta carrera';
      summaryRow.addEventListener('click', () => {
        details.open = true;
        search.value = '';
        apply(summaryCareer, 1, true);
        details.scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
    });

    panel._applyEligibilityCareer = nextCareer => {
      if (careers.some(item => normalize(item) === normalize(nextCareer))) {
        search.value = '';
        apply(nextCareer, 1);
      }
    };
    apply(career, 1);
  }

  function synchronizeCareer(event) {
    const career = event.detail?.career;
    if (!career) return;
    selectedCareer = career;
    const catalog = document.querySelector('[data-nuclei-catalog="active-careers"]');
    const eligibility = document.querySelector('[data-eligibility-panel]');
    catalog?._applyCatalogCareer?.(career);
    eligibility?._applyEligibilityCareer?.(career);

    const savedSelect = document.querySelector('[data-saved-career-select]');
    if (savedSelect && normalize(savedSelect.value) !== normalize(career)) {
      const option = [...savedSelect.options].find(item => normalize(item.value) === normalize(career));
      if (option) {
        savedSelect.value = option.value;
        savedSelect.dispatchEvent(new Event('change'));
      }
    }
  }

  function enhance() {
    enhanceCatalog();
    enhanceEligibility();
  }

  function scheduleEnhance() {
    if (enhancementQueued) return;
    enhancementQueued = true;
    requestAnimationFrame(() => {
      enhancementQueued = false;
      enhance();
    });
  }

  window.addEventListener('informtit:nuclei-career-change', synchronizeCareer);
  document.addEventListener('click', event => {
    if (event.target.closest('[data-tab="nuclei"]')) setTimeout(scheduleEnhance, 0);
  });
  new MutationObserver(scheduleEnhance).observe(document.body, { childList: true, subtree: true });
  scheduleEnhance();

  const style = document.createElement('style');
  style.textContent = `
    .career-page-toolbar {
      display: grid;
      grid-template-columns: auto minmax(260px, 1fr) auto auto;
      gap: 12px;
      align-items: end;
      padding: 14px;
      border: 1px solid #dbe4ee;
      border-radius: 14px;
      background: #f8fafc;
    }
    .career-page-toolbar label, .student-page-toolbar label { margin: 0; }
    .career-page-counter, .student-page-counter {
      align-self: center;
      color: #526575;
      font-size: 13px;
      font-weight: 700;
      white-space: nowrap;
    }
    .catalog-career-toolbar { margin: 16px 0; }
    .eligibility-career-browser { display: grid; gap: 10px; margin: 14px 0; }
    .student-page-toolbar {
      display: grid;
      grid-template-columns: minmax(260px, 1fr) auto auto auto;
      gap: 10px;
      align-items: end;
      padding: 12px 14px;
      border: 1px solid #e2e8f0;
      border-radius: 14px;
      background: white;
    }
    .career-paged-table th:nth-child(3), .career-paged-table td:nth-child(3) { display: none; }
    .career-summary-shortcut { cursor: pointer; transition: background .15s ease; }
    .career-summary-shortcut:hover { background: #eef6fb; }
    .eligibility-details > summary { position: sticky; top: 0; z-index: 2; padding: 10px 0; background: white; }
    @media (max-width: 920px) {
      .career-page-toolbar, .student-page-toolbar { grid-template-columns: 1fr 1fr; }
      .career-page-toolbar label, .career-page-counter, .student-page-toolbar label, .student-page-counter { grid-column: 1 / -1; }
      .career-page-counter, .student-page-counter { white-space: normal; }
    }
  `;
  document.head.appendChild(style);
})();
