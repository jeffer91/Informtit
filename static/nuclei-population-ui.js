(() => {
  'use strict';

  const populationCache = new Map();
  let scheduled = false;

  function clean(value = '') {
    return String(value ?? '').replace(/\u00a0/g, ' ').trim().replace(/\s+/g, ' ');
  }

  function normalize(value = '') {
    return clean(value)
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, ' ')
      .trim();
  }

  function canonicalCareer(value = '') {
    const external = window.informtitNucleiCareer?.canonicalCareer;
    if (typeof external === 'function') return clean(external(value));

    let text = clean(value)
      .replace(/^(?:TECNOLOG[IÍ]A|T[EÉ]CNICO)\s+SUPERIOR(?:\s+UNIVERSITARIA)?\s+EN\s+/i, '')
      .replace(/\s+(?:ONLINE|EN\s+L[IÍ]NEA|VIRTUAL|PRESENCIAL)\s*$/i, '')
      .trim();
    const key = normalize(text);
    if (key.includes('redes') && key.includes('telecomunicaciones')) return 'REDES Y TELECOMUNICACIONES';
    return text ? text.toLocaleUpperCase('es') : 'SIN CARRERA';
  }

  function studentIdentity(student = {}) {
    const identification = clean(student.identification || student.cedula || student.document || '');
    if (identification) return `id:${identification}`;
    const email = clean(student.email || student.correo || student.personal_email || '').toLowerCase();
    if (email) return `email:${email}`;
    const name = normalize(student.full_name || student.nombre || student.nombres || '');
    return name ? `name:${name}` : '';
  }

  function studentCareer(student = {}) {
    return canonicalCareer(
      student.career_name
      || student.career
      || student.carrera
      || student.nombreCarrera
      || student.nombre_carrera
      || student.program
      || '',
    );
  }

  function isComplexiveStudent(student = {}) {
    const route = normalize(student.route || student.ruta || 'COMPLEXIVO');
    const processStatus = normalize(student.process_status || student.estado_proceso || '');
    const retired = Boolean(student.retired || student.retirado) || processStatus === 'retirado';
    return !retired && (!route || route === 'complexivo');
  }

  function buildPopulation(students = []) {
    const byCareer = new Map();
    (Array.isArray(students) ? students : []).forEach(student => {
      if (!isComplexiveStudent(student)) return;
      const career = studentCareer(student);
      const key = normalize(career);
      const identity = studentIdentity(student);
      if (!key || key === 'sin carrera' || !identity) return;
      if (!byCareer.has(key)) byCareer.set(key, { career, students: new Set() });
      byCareer.get(key).students.add(identity);
    });
    return byCareer;
  }

  async function populationForReport(reportId) {
    if (populationCache.has(reportId)) return populationCache.get(reportId);
    const promise = (async () => {
      if (typeof api !== 'function') return { available: false, byCareer: new Map() };
      try {
        const payload = await api(`/api/reports/${reportId}/students-domain`);
        return {
          available: Array.isArray(payload?.students),
          byCareer: buildPopulation(payload?.students || []),
        };
      } catch (_) {
        return { available: false, byCareer: new Map() };
      }
    })();
    populationCache.set(reportId, promise);
    return promise;
  }

  function loadedCount(cell) {
    const label = clean(cell?.querySelector('.nuclei-cell-label')?.textContent || '');
    const match = label.match(/^(\d+)/);
    return match ? Number(match[1]) : 0;
  }

  function explicitReview(cell) {
    return Boolean(cell?.classList.contains('review'));
  }

  function updateKpi(matrix, total) {
    const kpis = [...matrix.querySelectorAll('.nuclei-kpi')];
    const studentKpi = kpis.find(kpi => normalize(kpi.querySelector('span')?.textContent) === 'estudiantes');
    const value = studentKpi?.querySelector('strong');
    if (value) value.textContent = String(total);
  }

  function populationCount(result, career) {
    if (!result.available) return null;
    return result.byCareer.get(normalize(canonicalCareer(career)))?.students?.size || 0;
  }

  function addPopulationColumn(matrix, result) {
    if (matrix.dataset.populationApplied === '1') return;

    const table = matrix.querySelector('.nuclei-matrix-table');
    if (!table) return;

    const headRow = table.querySelector('thead tr');
    const careerHead = headRow?.querySelector('th:first-child');
    if (!headRow || !careerHead) return;

    const populationHead = document.createElement('th');
    populationHead.className = 'nuclei-population-head';
    populationHead.textContent = 'Estudiantes';
    populationHead.title = 'Población oficial de estudiantes de la carrera en la ruta Examen Complexivo.';
    careerHead.insertAdjacentElement('afterend', populationHead);

    let totalPopulation = 0;

    table.querySelectorAll('tbody tr[data-nuclei-row]').forEach(row => {
      const career = row.dataset.career || '';
      const population = populationCount(result, career);
      if (population !== null) totalPopulation += population;

      const careerCell = row.querySelector('th[scope="row"]');
      if (!careerCell) return;

      const populationCell = document.createElement('td');
      populationCell.className = 'nuclei-population-cell';
      populationCell.innerHTML = population === null
        ? '<strong>—</strong><span>No disponible</span>'
        : `<strong>${population}</strong><span>oficiales</span>`;
      careerCell.insertAdjacentElement('afterend', populationCell);

      let hasPopulationMismatch = false;
      row.querySelectorAll('[data-nuclei-cell]').forEach(cell => {
        const count = loadedCount(cell);
        const originallyReview = explicitReview(cell);
        const label = cell.querySelector('.nuclei-cell-label');
        const nucleus = Number(cell.dataset.nucleus || 0);

        if (population === null) return;

        if (label) label.textContent = `${count}/${population}`;
        const mismatch = count > 0 && count !== population;
        const overPopulation = count > population;
        hasPopulationMismatch ||= mismatch;

        if (mismatch && !originallyReview) {
          cell.classList.remove('loaded', 'pending');
          cell.classList.add('review');
          const icon = cell.querySelector('.nuclei-cell-icon');
          if (icon) icon.textContent = '!';
        }

        const difference = population - count;
        if (count === 0) {
          cell.title = `${career} · Núcleo ${nucleus}: pendiente · 0/${population} estudiantes`;
        } else if (difference > 0) {
          cell.title = `${career} · Núcleo ${nucleus}: ${count}/${population} estudiantes · faltan ${difference}`;
        } else if (overPopulation) {
          cell.title = `${career} · Núcleo ${nucleus}: ${count}/${population} estudiantes · hay ${Math.abs(difference)} registro(s) adicional(es) por revisar`;
        } else if (!originallyReview) {
          cell.title = `${career} · Núcleo ${nucleus}: población completa (${count}/${population})`;
        }
      });

      if (hasPopulationMismatch) {
        row.dataset.populationMismatch = '1';
        row.dataset.review = String(Math.max(1, Number(row.dataset.review || 0)));
      }
    });

    if (result.available) updateKpi(matrix, totalPopulation);
    matrix.dataset.populationApplied = '1';
  }

  async function enhance() {
    const matrix = document.querySelector('#tab-nuclei [data-nuclei-matrix]');
    if (!matrix || matrix.dataset.populationApplied === '1') return;

    const reportId = Number(typeof state !== 'undefined' ? state.activeReport?.id || 0 : 0);
    if (!reportId) return;

    matrix.dataset.populationLoading = '1';
    const result = await populationForReport(reportId);
    if (!matrix.isConnected) return;
    if (Number(typeof state !== 'undefined' ? state.activeReport?.id || 0 : 0) !== reportId) return;
    addPopulationColumn(matrix, result);
  }

  function schedule() {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => {
      scheduled = false;
      void enhance();
    });
  }

  const observer = new MutationObserver(schedule);

  function install() {
    observer.observe(document.body, { childList: true, subtree: true });
    schedule();
  }

  const style = document.createElement('style');
  style.textContent = `
    .nuclei-matrix-table { min-width:960px !important; }
    .nuclei-matrix-table thead th:first-child { width:30% !important; }
    .nuclei-population-head { width:11%; white-space:nowrap; }
    .nuclei-population-cell { text-align:center !important; background:#fff; }
    .nuclei-population-cell strong { display:block; color:#173b57; font-size:15px; line-height:1.1; }
    .nuclei-population-cell span { display:block; margin-top:3px; color:#94a3b8; font-size:9px; text-transform:uppercase; letter-spacing:.035em; }
    .nuclei-cell-label { white-space:nowrap; }
    @media (max-width:760px) {
      .nuclei-matrix-table { min-width:900px !important; }
    }
  `;
  document.head.appendChild(style);

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install, { once: true });
  else install();
})();