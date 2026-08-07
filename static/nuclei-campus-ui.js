(() => {
  let requestSequence = 0;
  let scheduled = false;

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

  function fmt(value) {
    if (value === null || value === undefined || value === '') return '—';
    return Number(value).toFixed(2).replace('.', ',');
  }

  function courseByCard(courses, card) {
    const button = card.querySelector('[data-delete-nucleus]');
    const id = Number(button?.dataset.deleteNucleus || 0);
    return courses.find(course => Number(course.id) === id);
  }

  function decorateSavedCourses(courses) {
    const browser = document.querySelector('[data-saved-career-browser]');
    if (!browser) return;
    const cards = [...browser.querySelectorAll('[data-nucleus-course-card]')];
    cards.forEach(card => {
      const course = courseByCard(courses, card);
      if (!course) return;
      card.dataset.campus = course.campus || '';
      card.dataset.moduleCode = course.module_code || '';
      card.dataset.groupCode = course.group_code || '';
      const badges = card.querySelector('.nucleus-card-badges');
      if (badges && !badges.querySelector('[data-campus-badge]')) {
        badges.insertAdjacentHTML(
          'afterbegin',
          `<span class="badge campus-badge" data-campus-badge>${esc(course.campus || 'Sede no indicada')}</span>`,
        );
      }
      const head = card.querySelector('.career-head > div');
      if (head && !head.querySelector('[data-course-location]')) {
        const details = [
          course.campus ? `Sede: ${course.campus}` : '',
          course.module_code ? `Módulo ${course.module_code}` : '',
          course.group_code ? `Grupo ${course.group_code}` : '',
          course.schedule ? `Horario ${course.schedule}` : '',
        ].filter(Boolean).join(' · ');
        head.insertAdjacentHTML(
          'beforeend',
          `<p data-course-location><strong>Curso Moodle:</strong> ${esc(details || 'Sin metadatos adicionales')}</p>`,
        );
      }
    });

    const toolbar = browser.querySelector('.career-browser-toolbar');
    const careerSelect = browser.querySelector('[data-saved-career-select]');
    if (!toolbar || !careerSelect) return;
    let campusLabel = toolbar.querySelector('[data-campus-filter-label]');
    if (!campusLabel) {
      campusLabel = document.createElement('label');
      campusLabel.dataset.campusFilterLabel = '1';
      campusLabel.innerHTML = 'Sede<select data-campus-filter></select>';
      careerSelect.closest('label')?.insertAdjacentElement('afterend', campusLabel);
    }
    const campusSelect = campusLabel.querySelector('[data-campus-filter]');

    function applyCampusFilter() {
      const careerKey = normalize(careerSelect.value);
      const campusKey = normalize(campusSelect.value);
      let visible = 0;
      cards.forEach(card => {
        const sameCareer = normalize(card.dataset.careerName) === careerKey;
        const sameCampus = !campusKey || normalize(card.dataset.campus) === campusKey;
        card.hidden = !(sameCareer && sameCampus);
        if (!card.hidden) visible += 1;
      });
      const counter = browser.querySelector('[data-saved-career-counter]');
      if (counter) {
        const campusText = campusSelect.value ? ` · ${campusSelect.value}` : ' · todas las sedes';
        counter.textContent = `${visible} curso${visible === 1 ? '' : 's'} cargado${visible === 1 ? '' : 's'}${campusText}`;
      }
    }

    function refreshCampusOptions() {
      const careerKey = normalize(careerSelect.value);
      const careerCourses = courses.filter(course => normalize(course.career_name) === careerKey);
      const campuses = [...new Set(careerCourses.map(course => String(course.campus || '').trim()).filter(Boolean))]
        .sort((left, right) => left.localeCompare(right, 'es', { sensitivity: 'base' }));
      const current = campusSelect.value;
      const markup = `<option value="">Todas las sedes</option>${campuses.map(campus => `<option value="${esc(campus)}">${esc(campus)}</option>`).join('')}`;
      if (campusSelect.innerHTML !== markup) campusSelect.innerHTML = markup;
      if (campuses.some(campus => normalize(campus) === normalize(current))) campusSelect.value = current;
      applyCampusFilter();
    }

    if (campusSelect.dataset.bound !== '1') {
      campusSelect.dataset.bound = '1';
      campusSelect.addEventListener('change', applyCampusFilter);
      careerSelect.addEventListener('change', () => setTimeout(refreshCampusOptions, 0));
      window.addEventListener('informtit:nuclei-career-change', () => setTimeout(refreshCampusOptions, 0));
    }
    refreshCampusOptions();
  }

  function rebuildTeacherLoad(courses) {
    const panel = document.querySelector('.teacher-load-panel');
    const grid = panel?.querySelector('.teacher-load-grid');
    if (!panel || !grid) return;
    const grouped = new Map();
    courses.forEach(course => {
      const teacher = String(course.teacher_name || '').trim();
      if (!teacher) return;
      const key = normalize(teacher);
      if (!grouped.has(key)) grouped.set(key, { teacher, courses: [] });
      grouped.get(key).courses.push(course);
    });
    const teachers = [...grouped.values()].sort((a, b) => a.teacher.localeCompare(b.teacher, 'es', { sensitivity: 'base' }));
    const markup = teachers.map(item => `
      <article class="teacher-load-card">
        <strong>${esc(item.teacher)}</strong>
        <span>${item.courses.length} curso${item.courses.length === 1 ? '' : 's'} de Núcleos</span>
        <div class="teacher-assignment-list">${item.courses
          .sort((a, b) => String(a.career_name).localeCompare(String(b.career_name), 'es', { sensitivity: 'base' }) || String(a.campus).localeCompare(String(b.campus), 'es', { sensitivity: 'base' }) || Number(a.nucleus_number) - Number(b.nucleus_number))
          .map(course => `<span>${esc(course.career_name)} · ${esc(course.campus || 'Sede no indicada')} · Núcleo ${course.nucleus_number}${course.module_code ? ` · Mod ${esc(course.module_code)}` : ''}</span>`)
          .join('')}</div>
      </article>`).join('');
    if (grid.innerHTML !== markup) grid.innerHTML = markup;
    const description = panel.querySelector('.teacher-load-head p');
    if (description) description.textContent = 'Un docente puede impartir varios núcleos y una misma carrera puede tener docentes distintos por sede, módulo o paralelo.';
  }

  function renderGradeConflicts(data) {
    const panel = document.querySelector('[data-eligibility-panel]');
    if (!panel) return;
    const conflicts = data.grade_conflicts || [];
    const signature = JSON.stringify(conflicts.map(item => [item.student_id, item.nucleus_number, item.grades, item.sources]));
    const existing = panel.querySelector('[data-campus-grade-conflicts]');
    if (!conflicts.length) {
      existing?.remove();
      return;
    }
    if (existing?.dataset.conflictSignature === signature) return;
    existing?.remove();
    const students = new Map((data.rows || []).map(row => [Number(row.student_id), row]));
    const details = document.createElement('details');
    details.className = 'eligibility-details campus-grade-conflicts';
    details.dataset.campusGradeConflicts = '1';
    details.dataset.conflictSignature = signature;
    details.innerHTML = `
      <summary>${conflicts.length} conflicto${conflicts.length === 1 ? '' : 's'} de notas del mismo núcleo</summary>
      <p>Informtit no usa una nota al azar. Cuando un estudiante aparece con valores diferentes para el mismo núcleo, queda pendiente hasta revisar la sede o el curso correcto.</p>
      <div class="student-table-wrap"><table class="student-table compact-table">
        <thead><tr><th>Estudiante</th><th>Carrera</th><th>Núcleo</th><th>Fuentes encontradas</th></tr></thead>
        <tbody>${conflicts.map(conflict => {
          const student = students.get(Number(conflict.student_id)) || {};
          const sources = (conflict.sources || []).map(source => `${source.campus || 'Sin sede'}: ${fmt(source.grade)}${source.teacher_name ? ` · ${source.teacher_name}` : ''}`).join(' | ');
          return `<tr><td>${esc(student.full_name || '—')}</td><td>${esc(student.career_name || '—')}</td><td>${conflict.nucleus_number}</td><td>${esc(sources)}</td></tr>`;
        }).join('')}</tbody>
      </table></div>`;
    panel.appendChild(details);
  }

  async function enhance() {
    const reportId = Number(state.activeReport?.id || 0);
    const tab = document.querySelector('#tab-nuclei');
    if (!reportId || !tab) return;
    const request = ++requestSequence;
    try {
      const [nuclei, eligibility] = await Promise.all([
        api(`/api/reports/${reportId}/nuclei`),
        api(`/api/reports/${reportId}/nuclei/eligibility`),
      ]);
      if (request !== requestSequence || Number(state.activeReport?.id || 0) !== reportId) return;
      const courses = nuclei.courses || [];
      const signature = JSON.stringify({
        courses: courses.map(course => [course.id, course.career_name, course.nucleus_number, course.campus, course.module_code, course.group_code, course.schedule, course.teacher_name]),
        conflicts: (eligibility.grade_conflicts || []).map(item => [item.student_id, item.nucleus_number, item.grades]),
      });
      const alreadyApplied = tab.dataset.campusUiSignature === signature
        && Boolean(tab.querySelector('[data-campus-filter]'))
        && (!(eligibility.grade_conflicts || []).length || Boolean(tab.querySelector('[data-campus-grade-conflicts]')));
      if (alreadyApplied) return;
      decorateSavedCourses(courses);
      rebuildTeacherLoad(courses);
      renderGradeConflicts(eligibility);
      tab.dataset.campusUiSignature = signature;
    } catch (_error) {
      // Se conserva la interfaz base si el módulo todavía no terminó de renderizar.
    }
  }

  function schedule() {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => {
      scheduled = false;
      enhance();
    });
  }

  new MutationObserver(schedule).observe(document.body, { childList: true, subtree: true });
  document.addEventListener('click', event => {
    if (event.target.closest('[data-tab="nuclei"]')) {
      setTimeout(enhance, 100);
      setTimeout(enhance, 500);
    }
  });
  schedule();

  const style = document.createElement('style');
  style.textContent = `
    .campus-badge { background: #e9f7ef !important; color: #236a45 !important; }
    .career-browser-toolbar { grid-template-columns: auto minmax(220px, 1fr) minmax(180px, .8fr) auto auto !important; }
    .campus-grade-conflicts { margin-top: 16px; border-color: #f0c36a; background: #fffaf0; }
    .campus-grade-conflicts > p { margin: 10px 0; color: #6b5428; }
    @media (max-width: 1050px) {
      .career-browser-toolbar { grid-template-columns: 1fr 1fr !important; }
      .career-browser-toolbar label, .career-browser-counter { grid-column: auto !important; }
    }
  `;
  document.head.appendChild(style);
})();
