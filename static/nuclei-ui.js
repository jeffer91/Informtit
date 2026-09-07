(() => {
  window.INFORMTIT_MINIMAL_NUCLEI = true;

  const previousRenderReport = renderReport;
  let activeNucleiReportId = 0;
  let selectedCareer = '';
  let searchText = '';

  function esc(value = '') {
    return typeof escapeHtml === 'function'
      ? escapeHtml(String(value))
      : String(value).replace(/[&<>"']/g, character => ({
          '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;',
        })[character]);
  }

  function normalize(value = '') {
    return String(value)
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, ' ')
      .trim();
  }

  function compareText(left, right) {
    return String(left || '').localeCompare(String(right || ''), 'es', { sensitivity: 'base' });
  }

  function fmt(value) {
    if (value === null || value === undefined || value === '') return '—';
    const number = Number(value);
    return Number.isFinite(number) ? number.toFixed(2).replace('.', ',') : '—';
  }

  function canonicalCareer(value = '') {
    const external = window.informtitNucleiCareer?.canonicalCareer;
    if (typeof external === 'function') return external(value);

    let text = String(value || '').replace(/\u00a0/g, ' ').trim().replace(/\s+/g, ' ');
    text = text
      .replace(/^(?:TECNOLOG[IÍ]A|T[EÉ]CNICO)\s+SUPERIOR(?:\s+UNIVERSITARIA)?\s+EN\s+/i, '')
      .replace(/\s+(?:ONLINE|EN\s+L[IÍ]NEA|VIRTUAL|PRESENCIAL)\s*$/i, '')
      .trim();
    const key = normalize(text);
    if (key.includes('redes') && key.includes('telecomunicaciones')) return 'REDES Y TELECOMUNICACIONES';
    return text ? text.toLocaleUpperCase('es') : 'SIN CARRERA';
  }

  function unique(values) {
    const seen = new Map();
    values.forEach(value => {
      const career = canonicalCareer(value);
      const key = normalize(career);
      if (key && !seen.has(key)) seen.set(key, career);
    });
    return [...seen.values()].sort(compareText);
  }

  function studentIdentity(student = {}) {
    const identification = String(student.identification || student.cedula || '').trim();
    if (identification) return `id:${identification}`;
    const email = String(student.email || student.correo || '').trim().toLowerCase();
    if (email) return `email:${email}`;
    const name = normalize(student.full_name || student.nombre || student.nombres || '');
    return name ? `name:${name}` : '';
  }

  function numericGrade(student = {}) {
    const value = Number(student.final_grade ?? student.notaFinal ?? student.nota_final);
    return Number.isFinite(value) ? value : null;
  }

  function statusCounts(students) {
    const approved = students.filter(student => normalize(student.final_status || student.estado) === 'aprobado').length;
    const failed = students.filter(student => normalize(student.final_status || student.estado) === 'reprobado').length;
    const pending = students.length - approved - failed;
    return { approved, failed, pending };
  }

  function courseTimestamp(course = {}) {
    const value = Date.parse(course.updated_at || course.updatedAt || course._updateTime || '');
    return Number.isFinite(value) ? value : 0;
  }

  function blankNucleus(number) {
    return {
      number,
      sources: [],
      studentsByIdentity: new Map(),
      students: [],
      duplicateCount: 0,
      conflictCount: 0,
      average: null,
      counts: { approved: 0, failed: 0, pending: 0 },
    };
  }

  function organizeCareers(courses, catalogCareers = []) {
    const groups = new Map();

    function ensure(rawCareer) {
      const career = canonicalCareer(rawCareer);
      const key = normalize(career);
      if (!groups.has(key)) {
        groups.set(key, {
          career,
          nuclei: {
            1: blankNucleus(1),
            2: blankNucleus(2),
            3: blankNucleus(3),
            4: blankNucleus(4),
          },
          uniqueStudents: 0,
          loadedNuclei: 0,
          duplicates: 0,
          conflicts: 0,
          search: '',
        });
      }
      return groups.get(key);
    }

    (catalogCareers || []).forEach(ensure);

    (courses || []).forEach(course => {
      const group = ensure(course.career_name);
      const nucleusNumber = Number(course.nucleus_number || 0);
      if (![1, 2, 3, 4].includes(nucleusNumber)) return;

      const slot = group.nuclei[nucleusNumber];
      const sourceTimestamp = courseTimestamp(course);
      slot.sources.push(course);

      (course.students || []).forEach((student, index) => {
        const identity = studentIdentity(student) || `anonymous:${normalize(student.full_name)}:${index}`;
        const candidate = {
          ...student,
          _sourceTimestamp: sourceTimestamp,
          _sourceTitle: course.course_title || `Núcleo ${nucleusNumber}`,
          _sourceTeacher: course.teacher_name || '',
        };
        const existing = slot.studentsByIdentity.get(identity);

        if (!existing) {
          slot.studentsByIdentity.set(identity, candidate);
          return;
        }

        slot.duplicateCount += 1;
        const existingGrade = numericGrade(existing);
        const candidateGrade = numericGrade(candidate);
        const existingStatus = normalize(existing.final_status || existing.estado);
        const candidateStatus = normalize(candidate.final_status || candidate.estado);

        if (
          (existingGrade !== null && candidateGrade !== null && Math.abs(existingGrade - candidateGrade) > 0.001)
          || (existingStatus && candidateStatus && existingStatus !== candidateStatus)
        ) {
          slot.conflictCount += 1;
        }

        const candidateIsNewer = candidate._sourceTimestamp > (existing._sourceTimestamp || 0);
        const candidateHasBetterData = existingGrade === null && candidateGrade !== null;
        if (candidateIsNewer || candidateHasBetterData) slot.studentsByIdentity.set(identity, candidate);
      });
    });

    const output = [...groups.values()];
    output.forEach(group => {
      const careerStudentIds = new Set();
      for (let number = 1; number <= 4; number += 1) {
        const slot = group.nuclei[number];
        slot.students = [...slot.studentsByIdentity.values()].sort((a, b) => compareText(a.full_name, b.full_name));
        slot.students.forEach(student => {
          const identity = studentIdentity(student);
          if (identity) careerStudentIds.add(identity);
        });
        const grades = slot.students.map(numericGrade).filter(value => value !== null);
        slot.average = grades.length ? grades.reduce((sum, value) => sum + value, 0) / grades.length : null;
        slot.counts = statusCounts(slot.students);
        group.duplicates += slot.duplicateCount;
        group.conflicts += slot.conflictCount;
      }
      group.uniqueStudents = careerStudentIds.size;
      group.loadedNuclei = [1, 2, 3, 4].filter(number => group.nuclei[number].students.length > 0).length;
      group.search = normalize([
        group.career,
        ...[1, 2, 3, 4].flatMap(number => group.nuclei[number].students.map(student => (
          `${student.full_name || ''} ${student.identification || student.cedula || ''} ${student.email || ''}`
        ))),
      ].join(' '));
    });

    return output.sort((a, b) => compareText(a.career, b.career));
  }

  renderReport = function renderReportWithCareerNuclei() {
    previousRenderReport();
    if (state.activeReport?.id) renderNucleiModule();
  };

  async function renderNucleiModule() {
    const tab = document.querySelector('#tab-nuclei');
    const reportId = Number(state.activeReport?.id || 0);
    if (!tab || !reportId) return;

    if (activeNucleiReportId !== reportId) {
      activeNucleiReportId = reportId;
      selectedCareer = '';
      searchText = '';
    }

    tab.dataset.nucleiReportId = String(reportId);
    bindDelegatedEvents(tab);
    tab.innerHTML = '<div class="panel"><div class="empty-mini">Cargando Núcleos...</div></div>';

    try {
      const data = await api(`/api/reports/${reportId}/nuclei`);
      if (Number(state.activeReport?.id || 0) !== reportId) return;
      const groups = organizeCareers(data?.courses || [], data?.careers || []);
      normalizeSelection(groups);
      tab.innerHTML = markup(groups, data?.excel_import || null);
      tab.dataset.nucleiReportId = String(reportId);
      applyFilters(tab);
    } catch (error) {
      tab.innerHTML = `<div class="panel"><div class="empty-mini">${esc(error.message)}</div></div>`;
    }
  }

  function normalizeSelection(groups) {
    const careers = groups.map(group => group.career);
    if (selectedCareer && !careers.some(career => normalize(career) === normalize(selectedCareer))) {
      selectedCareer = '';
    }
  }

  function markup(groups, sourceSummary) {
    return `
      <div class="process-stack excel-nuclei" data-minimal-nuclei>
        <section class="panel excel-nuclei-upload">
          <div class="panel-head">
            <div>
              <h2>Cargar Núcleos</h2>
              <p>Seleccione una carrera y cargue sus cuatro Núcleos. Informtit consolida la información por estudiante y evita mostrar materias o grupos repetidos.</p>
            </div>
          </div>
        </section>

        <section class="panel excel-nuclei-results">
          <div class="panel-head">
            <div>
              <h2>Núcleos por carrera</h2>
              <p>Cada carrera aparece una sola vez y contiene Núcleo 1, Núcleo 2, Núcleo 3 y Núcleo 4. Las variantes del nombre de carrera se normalizan automáticamente.</p>
            </div>
          </div>
          ${summaryMarkup(groups, sourceSummary)}
          ${careersMarkup(groups)}
        </section>
      </div>`;
  }

  function summaryMarkup(groups, sourceSummary) {
    const careerStudents = new Set();
    let results = 0;
    let loaded = 0;
    let duplicates = 0;
    groups.forEach(group => {
      [1, 2, 3, 4].forEach(number => {
        const slot = group.nuclei[number];
        if (slot.students.length) loaded += 1;
        results += slot.students.length;
        duplicates += slot.duplicateCount;
        slot.students.forEach(student => {
          const identity = studentIdentity(student);
          if (identity) careerStudents.add(`${normalize(group.career)}|${identity}`);
        });
      });
    });

    return `<div class="nuclei-import-summary nuclei-career-summary">
      <div><strong>${groups.length}</strong><span>Carreras</span></div>
      <div><strong>${careerStudents.size}</strong><span>Estudiantes únicos</span></div>
      <div><strong>${results}</strong><span>Resultados de Núcleos</span></div>
      <div><strong>${loaded}</strong><span>Núcleos cargados</span></div>
      <div><strong>${duplicates}</strong><span>Duplicados consolidados</span></div>
      <div class="nuclei-import-file"><strong>${esc(sourceSummary?.filename || 'Firebase UTET')}</strong><span>Fuente actual</span></div>
    </div>`;
  }

  function careersMarkup(groups) {
    if (!groups.length) {
      return '<div class="empty-mini">No se encontraron carreras para este período.</div>';
    }

    const careers = unique(groups.map(group => group.career));
    return `
      <div class="nuclei-result-bar">
        <div class="nuclei-result-count">${groups.length} carrera${groups.length === 1 ? '' : 's'} · cada carrera dispone de 4 Núcleos</div>
        <div class="nuclei-result-filters">
          <label>Carrera
            <select data-nuclei-career-filter>
              <option value="">Todas</option>
              ${careers.map(career => `<option value="${esc(career)}" ${normalize(career) === normalize(selectedCareer) ? 'selected' : ''}>${esc(career)}</option>`).join('')}
            </select>
          </label>
          <label>Buscar
            <input data-nuclei-search value="${esc(searchText)}" placeholder="Carrera, cédula o estudiante">
          </label>
        </div>
      </div>
      <div class="nuclei-career-list">
        ${groups.map(careerMarkup).join('')}
      </div>`;
  }

  function careerMarkup(group) {
    return `<article class="nuclei-career-card" data-nuclei-career-card data-career="${esc(group.career)}" data-search="${esc(group.search)}">
      <div class="nuclei-career-head">
        <div>
          <h3>${esc(group.career)}</h3>
          <p>${group.uniqueStudents} estudiante${group.uniqueStudents === 1 ? '' : 's'} · ${group.loadedNuclei}/4 Núcleos cargados</p>
        </div>
        ${group.conflicts ? `<span class="nuclei-conflict-badge">${group.conflicts} registro${group.conflicts === 1 ? '' : 's'} por revisar</span>` : ''}
      </div>
      <div class="nuclei-slot-grid">
        ${[1, 2, 3, 4].map(number => nucleusMarkup(group.career, group.nuclei[number])).join('')}
      </div>
    </article>`;
  }

  function nucleusMarkup(career, slot) {
    const loaded = slot.students.length > 0;
    const safeCareer = normalize(career).replace(/\s+/g, '-');
    const detailId = `nucleus-detail-${safeCareer}-${slot.number}`;
    const counts = slot.counts;

    return `<section class="nuclei-slot ${loaded ? 'loaded' : 'pending'}">
      <div class="nuclei-slot-head">
        <strong>Núcleo ${slot.number}</strong>
        <span class="nuclei-slot-state">${loaded ? 'Cargado' : 'Pendiente'}</span>
      </div>
      ${loaded ? `
        <div class="nuclei-slot-stats">
          <span><b>${slot.students.length}</b> estudiantes</span>
          <span>Promedio <b>${fmt(slot.average)}</b></span>
          <span class="nuclei-status-ok">${counts.approved} APR</span>
          ${counts.failed ? `<span class="nuclei-status-fail">${counts.failed} REP</span>` : ''}
          ${counts.pending ? `<span class="nuclei-status-pending">${counts.pending} sin evaluación</span>` : ''}
        </div>
        ${slot.sources.length > 1 ? `<small class="nuclei-merged-note">${slot.sources.length} cargas/grupos consolidados en un solo Núcleo</small>` : ''}
        <div class="nuclei-slot-actions">
          <button class="button secondary small" type="button" data-toggle-nuclei-detail="${detailId}">Ver estudiantes</button>
          <button class="button secondary small" type="button" data-load-nucleus data-career="${esc(career)}" data-nucleus="${slot.number}">Actualizar</button>
        </div>
        <div class="nuclei-course-detail" id="${detailId}" hidden>
          ${studentsTable(slot.students, slot.conflictCount)}
        </div>
      ` : `
        <div class="nuclei-slot-empty">
          <span>Sin información cargada</span>
          <button class="button primary small" type="button" data-load-nucleus data-career="${esc(career)}" data-nucleus="${slot.number}">Cargar Núcleo ${slot.number}</button>
        </div>
      `}
    </section>`;
  }

  function studentsTable(students, conflicts = 0) {
    return `<div class="student-table-wrap nuclei-student-table-wrap">
      ${conflicts ? `<div class="nuclei-detail-warning">${conflicts} duplicado${conflicts === 1 ? '' : 's'} tenía información diferente. Se muestra el registro más reciente disponible.</div>` : ''}
      <table class="student-table compact-table nuclei-student-table">
        <thead><tr><th>Cédula</th><th>Estudiante</th><th>Nota final</th><th>Estado</th></tr></thead>
        <tbody>${students.map(student => `<tr>
          <td>${esc(student.identification || student.cedula || '—')}</td>
          <td>${esc(student.full_name || '—')}</td>
          <td><strong>${fmt(numericGrade(student))}</strong></td>
          <td>${esc(student.final_status || student.estado || 'No evaluado')}</td>
        </tr>`).join('')}</tbody>
      </table>
    </div>`;
  }

  function bindDelegatedEvents(tab) {
    if (tab.dataset.nucleiDelegatedBound === '1') return;
    tab.dataset.nucleiDelegatedBound = '1';
    tab.addEventListener('click', handleTabClick);
    tab.addEventListener('change', handleTabChange);
    tab.addEventListener('input', handleTabInput);
  }

  function handleTabClick(event) {
    const toggle = event.target.closest('[data-toggle-nuclei-detail]');
    if (toggle) {
      const tab = event.currentTarget;
      const detail = tab.querySelector(`#${CSS.escape(toggle.dataset.toggleNucleiDetail)}`);
      if (!detail) return;
      detail.hidden = !detail.hidden;
      toggle.textContent = detail.hidden ? 'Ver estudiantes' : 'Ocultar estudiantes';
      return;
    }

    const load = event.target.closest('[data-load-nucleus]');
    if (!load) return;
    const tab = event.currentTarget;
    const career = load.dataset.career || '';
    const nucleus = Number(load.dataset.nucleus || 0);
    const box = tab.querySelector('[data-nuclei-final-box]');
    const form = box?.querySelector('[data-nuclei-final-form]');
    const select = form?.elements?.nucleus_number;

    if (!box || !form || !select) {
      toast('El formulario de carga de Núcleos todavía no está disponible.', true);
      return;
    }

    select.value = String(nucleus);
    let target = box.querySelector('[data-nuclei-target]');
    if (!target) {
      target = document.createElement('div');
      target.dataset.nucleiTarget = '1';
      target.className = 'nuclei-target';
      const title = box.querySelector('.nuclei-final-title');
      title?.insertAdjacentElement('afterend', target);
    }
    target.innerHTML = `<span>Está cargando</span><strong>${esc(career)} · Núcleo ${nucleus}</strong>`;
    form.dataset.targetCareer = career;
    box.scrollIntoView({ behavior: 'smooth', block: 'start' });
    window.setTimeout(() => form.elements.text?.focus(), 350);
  }

  function handleTabChange(event) {
    if (!event.target.matches('[data-nuclei-career-filter]')) return;
    selectedCareer = event.target.value;
    applyFilters(event.currentTarget);
  }

  function handleTabInput(event) {
    if (!event.target.matches('[data-nuclei-search]')) return;
    searchText = event.target.value;
    applyFilters(event.currentTarget);
  }

  function applyFilters(tab) {
    const career = tab.querySelector('[data-nuclei-career-filter]')?.value || selectedCareer;
    const query = normalize(tab.querySelector('[data-nuclei-search]')?.value || searchText);
    selectedCareer = career;
    searchText = tab.querySelector('[data-nuclei-search]')?.value || searchText;

    tab.querySelectorAll('[data-nuclei-career-card]').forEach(card => {
      const sameCareer = !career || normalize(card.dataset.career) === normalize(career);
      const matchesSearch = !query || String(card.dataset.search || '').includes(query);
      card.hidden = !(sameCareer && matchesSearch);
    });
  }

  const style = document.createElement('style');
  style.textContent = `
    .excel-nuclei { gap: 14px; }
    .excel-nuclei-upload .panel-head p, .excel-nuclei-results .panel-head p { margin: 4px 0 0; color: #64748b; max-width: 980px; }
    .nuclei-import-summary { display: grid; grid-template-columns: repeat(5, minmax(120px, 1fr)) minmax(220px, 1.4fr); gap: 9px; margin: 14px 0; }
    .nuclei-import-summary > div { padding: 11px 12px; border: 1px solid #e2e8f0; border-radius: 12px; background: #f8fafc; display: grid; gap: 2px; }
    .nuclei-import-summary strong { color: #173b57; font-size: 16px; }
    .nuclei-import-summary span { color: #64748b; font-size: 11px; }
    .nuclei-import-file strong { font-size: 12px; overflow-wrap: anywhere; }
    .nuclei-result-bar { display: grid; gap: 12px; margin: 10px 0 14px; }
    .nuclei-result-count { color: #64748b; font-size: 12px; font-weight: 700; }
    .nuclei-result-filters { display: grid; grid-template-columns: minmax(260px, .8fr) minmax(280px, 1fr); gap: 12px; }
    .nuclei-career-list { display: grid; gap: 14px; }
    .nuclei-career-card { border: 1px solid #dbe5ee; border-radius: 15px; background: #fff; padding: 15px; }
    .nuclei-career-card[hidden], .nuclei-course-detail[hidden] { display: none !important; }
    .nuclei-career-head { display: flex; justify-content: space-between; align-items: start; gap: 12px; margin-bottom: 12px; }
    .nuclei-career-head h3 { margin: 0; color: #173b57; font-size: 17px; }
    .nuclei-career-head p { margin: 4px 0 0; color: #64748b; font-size: 12px; }
    .nuclei-conflict-badge { padding: 5px 8px; border-radius: 999px; background: #fff7ed; border: 1px solid #fed7aa; color: #9a3412; font-size: 10px; font-weight: 800; }
    .nuclei-slot-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }
    .nuclei-slot { min-width: 0; border: 1px solid #e2e8f0; border-radius: 12px; padding: 12px; background: #f8fafc; }
    .nuclei-slot.loaded { background: #fbfefc; border-color: #cce8d7; }
    .nuclei-slot.pending { background: #fafafa; border-style: dashed; }
    .nuclei-slot-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
    .nuclei-slot-head strong { color: #173b57; }
    .nuclei-slot-state { font-size: 10px; font-weight: 800; padding: 4px 7px; border-radius: 999px; background: #e2e8f0; color: #475569; }
    .nuclei-slot.loaded .nuclei-slot-state { background: #dcfce7; color: #166534; }
    .nuclei-slot-stats { display: flex; flex-wrap: wrap; gap: 6px 9px; margin-top: 10px; }
    .nuclei-slot-stats span { color: #64748b; font-size: 11px; }
    .nuclei-status-ok { color: #166534 !important; font-weight: 800; }
    .nuclei-status-fail { color: #991b1b !important; font-weight: 800; }
    .nuclei-status-pending { color: #92400e !important; font-weight: 800; }
    .nuclei-merged-note { display: block; margin-top: 8px; color: #64748b; font-size: 10px; line-height: 1.4; }
    .nuclei-slot-actions { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 10px; }
    .nuclei-slot-empty { display: grid; gap: 11px; align-content: start; min-height: 92px; margin-top: 10px; }
    .nuclei-slot-empty span { color: #94a3b8; font-size: 11px; }
    .nuclei-course-detail { margin-top: 10px; padding-top: 10px; border-top: 1px solid #e2e8f0; }
    .nuclei-student-table-wrap { max-height: 360px; overflow: auto; }
    .nuclei-student-table { min-width: 590px; }
    .nuclei-detail-warning { margin-bottom: 8px; padding: 8px 9px; border-radius: 8px; background: #fff7ed; color: #9a3412; font-size: 10px; }
    .nuclei-target { margin: 0 0 12px; padding: 10px 12px; border: 1px solid #bfdbfe; border-radius: 10px; background: #eff6ff; display: grid; gap: 2px; }
    .nuclei-target span { color: #64748b; font-size: 10px; text-transform: uppercase; letter-spacing: .04em; }
    .nuclei-target strong { color: #173b57; font-size: 13px; }
    @media (max-width: 1200px) {
      .nuclei-slot-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .nuclei-import-summary { grid-template-columns: repeat(3, 1fr); }
    }
    @media (max-width: 760px) {
      .nuclei-result-filters, .nuclei-import-summary, .nuclei-slot-grid { grid-template-columns: 1fr; }
      .nuclei-career-head { display: grid; }
    }
  `;
  document.head.appendChild(style);
})();