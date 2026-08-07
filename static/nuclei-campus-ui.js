(() => {
  let requestSequence = 0;
  let scheduled = false;
  let observer = null;

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

  function metadataFromTitle(title = '') {
    const text = String(title || '').replace(/\s+/g, ' ').trim();
    const moduleMatch = text.match(/\bMod\s*(\d+)\b/i);
    const periodMatch = text.match(/\bMod\s*\d+\s*,\s*([^,\]\s]+)/i);
    const groupMatch = text.match(/\bEsp\.\s*([A-Za-z0-9_-]+)/i);
    const scheduleMatch = text.match(/(\d{1,2}h\d{2}\s*-\s*\d{1,2}h\d{2})/i);
    const campusMatch = text.match(/\d{1,2}h\d{2}\s*-\s*\d{1,2}h\d{2}\s*-\s*([^\]\n]+)\]/i);
    return {
      campus: campusMatch?.[1]?.trim() || '',
      moduleCode: moduleMatch?.[1] || '',
      periodLabel: periodMatch?.[1]?.trim() || '',
      groupCode: groupMatch?.[1]?.trim() || '',
      schedule: scheduleMatch?.[1]?.replace(/\s+/g, '') || '',
    };
  }

  function decorateImportGuidance() {
    const note = document.querySelector('#tab-nuclei .nuclei-rule-note');
    if (note && note.dataset.multicampusCopy !== '1') {
      note.dataset.multicampusCopy = '1';
      note.innerHTML = '<strong>Asignación docente y sedes:</strong> un mismo profesor puede impartir uno o varios núcleos. Una misma carrera puede tener el mismo núcleo en Quito, Manta u otras sedes con docentes diferentes. Informtit guarda cada curso Moodle de forma independiente por carrera, núcleo y datos del curso.';
    }
  }

  function decoratePreview() {
    const preview = document.querySelector('#nucleus-preview .nucleus-preview-card');
    if (!preview) return;
    const title = preview.querySelector('.panel-head p')?.textContent || '';
    const metadata = metadataFromTitle(title);
    const signature = [metadata.campus, metadata.moduleCode, metadata.periodLabel, metadata.groupCode, metadata.schedule].join('|');
    let block = preview.querySelector('[data-preview-course-meta]');
    if (!block) {
      block = document.createElement('div');
      block.className = 'preview-course-meta';
      block.dataset.previewCourseMeta = '1';
      preview.querySelector('.panel-head')?.insertAdjacentElement('afterend', block);
    }
    if (block.dataset.signature === signature) return;
    block.dataset.signature = signature;
    const items = [
      ['Sede', metadata.campus || 'No detectada'],
      ['Módulo', metadata.moduleCode || '—'],
      ['Período', metadata.periodLabel || '—'],
      ['Grupo', metadata.groupCode || '—'],
      ['Horario', metadata.schedule || '—'],
    ];
    block.innerHTML = items.map(([label, value]) => `<span><small>${esc(label)}</small><strong>${esc(value)}</strong></span>`).join('');
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
        const value = `${visible} curso${visible === 1 ? '' : 's'} cargado${visible === 1 ? '' : 's'}${campusText}`;
        if (counter.textContent !== value) counter.textContent = value;
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
      const matchingCampus = campuses.find(campus => normalize(campus) === normalize(current));
      if (matchingCampus) campusSelect.value = matchingCampus;
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
    const text = 'Un docente puede impartir varios núcleos y una misma carrera puede tener docentes distintos por sede, módulo o paralelo.';
    if (description && description.textContent !== text) description.textContent = text;
  }

  function renderGradeConflicts(data) {
    const panel = document.querySelector('[data-eligibility-panel]');
    if (!panel) return;
    const conflicts = data.grade_conflicts || [];
    const existing = panel.querySelector('[data-campus-grade-conflicts]');
    if (!conflicts.length) {
      existing?.remove();
      return;
    }
    const students = new Map((data.rows || []).map(row => [Number(row.student_id), row]));
    const markup = `
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
    let details = existing;
    if (!details) {
      details = document.createElement('details');
      details.className = 'eligibility-details campus-grade-conflicts';
      details.dataset.campusGradeConflicts = '1';
      panel.appendChild(details);
    }
    if (details.innerHTML !== markup) details.innerHTML = markup;
  }

  async function enhance() {
    const reportId = Number(state.activeReport?.id || 0);
    const tab = document.querySelector('#tab-nuclei');
    if (!reportId || !tab?.classList.contains('active')) return;
    const request = ++requestSequence;
    try {
      const [nuclei, eligibility] = await Promise.all([
        api(`/api/reports/${reportId}/nuclei`),
        api(`/api/reports/${reportId}/nuclei/eligibility`),
      ]);
      if (request !== requestSequence || Number(state.activeReport?.id || 0) !== reportId) return;
      observer?.disconnect();
      try {
        decorateImportGuidance();
        decoratePreview();
        const courses = nuclei.courses || [];
        decorateSavedCourses(courses);
        rebuildTeacherLoad(courses);
        renderGradeConflicts(eligibility);
      } finally {
        observer?.observe(document.body, { childList: true, subtree: true });
      }
    } catch (_error) {
      observer?.observe(document.body, { childList: true, subtree: true });
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

  function mutationContainsRelevantUi(record) {
    return [...record.addedNodes].some(node => {
      if (!(node instanceof Element)) return false;
      return node.matches?.('#tab-nuclei .process-stack, #nucleus-preview .nucleus-preview-card, [data-saved-career-browser], [data-eligibility-panel], .teacher-load-panel')
        || Boolean(node.querySelector?.('#nucleus-preview .nucleus-preview-card, [data-saved-career-browser], [data-eligibility-panel], .teacher-load-panel'));
    });
  }

  observer = new MutationObserver(records => {
    if (records.some(mutationContainsRelevantUi)) schedule();
  });
  observer.observe(document.body, { childList: true, subtree: true });

  document.addEventListener('click', event => {
    if (event.target.closest('[data-tab="nuclei"]')) {
      setTimeout(enhance, 100);
    }
  });
  schedule();

  const style = document.createElement('style');
  style.textContent = `
    .campus-badge { background: #e9f7ef !important; color: #236a45 !important; }
    .career-browser-toolbar { grid-template-columns: auto minmax(220px, 1fr) minmax(180px, .8fr) auto auto !important; }
    .campus-grade-conflicts { margin-top: 16px; border-color: #f0c36a; background: #fffaf0; }
    .campus-grade-conflicts > p { margin: 10px 0; color: #6b5428; }
    .preview-course-meta { display: grid; grid-template-columns: repeat(5, minmax(110px, 1fr)); gap: 8px; margin: 12px 0 4px; }
    .preview-course-meta span { padding: 9px 10px; border: 1px solid #d7e3ec; border-radius: 10px; background: white; }
    .preview-course-meta small { display: block; margin-bottom: 3px; color: #64748b; font-size: 10px; text-transform: uppercase; letter-spacing: .04em; }
    .preview-course-meta strong { color: #263b4d; font-size: 13px; }
    @media (max-width: 1050px) {
      .career-browser-toolbar { grid-template-columns: 1fr 1fr !important; }
      .career-browser-toolbar label, .career-browser-counter { grid-column: auto !important; }
      .preview-course-meta { grid-template-columns: repeat(2, minmax(120px, 1fr)); }
    }
  `;
  document.head.appendChild(style);
})();
