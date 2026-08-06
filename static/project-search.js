(() => {
  const tab = document.querySelector('#tab-projects');
  if (!tab) return;

  function escapeLocal(value = '') {
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
      .replace(/[^a-z0-9@._-]+/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  }

  function distance(left, right) {
    if (left === right) return 0;
    if (!left) return right.length;
    if (!right) return left.length;
    const previous = Array.from({ length: right.length + 1 }, (_, index) => index);
    for (let row = 1; row <= left.length; row += 1) {
      const current = [row];
      for (let column = 1; column <= right.length; column += 1) {
        current[column] = Math.min(
          current[column - 1] + 1,
          previous[column] + 1,
          previous[column - 1] + (left[row - 1] === right[column - 1] ? 0 : 1),
        );
      }
      previous.splice(0, previous.length, ...current);
    }
    return previous[right.length];
  }

  function studentFields(student) {
    return {
      identification: normalize(student.identification),
      name: normalize(student.full_name),
      institutionalEmail: normalize(student.email),
      personalEmail: normalize(student.personal_email),
      careerCode: normalize(student.career_code || student.report_career_code),
      career: normalize(student.career_name),
      campus: normalize(student.campus),
    };
  }

  function scoreStudent(student, query) {
    const cleanQuery = normalize(query);
    if (!cleanQuery) return 0;
    const fields = studentFields(student);
    const exactFields = [
      fields.identification,
      fields.institutionalEmail,
      fields.personalEmail,
      fields.careerCode,
    ];
    if (exactFields.includes(cleanQuery)) return 10000;

    let score = 0;
    if (fields.identification.startsWith(cleanQuery)) score += 2800;
    if (fields.institutionalEmail.startsWith(cleanQuery)) score += 2600;
    if (fields.personalEmail.startsWith(cleanQuery)) score += 2400;
    if (fields.careerCode.startsWith(cleanQuery)) score += 2200;
    if (fields.name.startsWith(cleanQuery)) score += 1800;
    if (fields.name.includes(cleanQuery)) score += 1300;
    if (fields.career.includes(cleanQuery)) score += 750;

    const queryTokens = cleanQuery.split(' ').filter(Boolean);
    const searchableWords = [
      ...fields.name.split(' '),
      ...fields.career.split(' '),
      fields.identification,
      fields.institutionalEmail,
      fields.personalEmail,
      fields.careerCode,
    ].filter(Boolean);

    for (const token of queryTokens) {
      let best = 0;
      for (const word of searchableWords) {
        if (word === token) best = Math.max(best, 320);
        else if (word.startsWith(token)) best = Math.max(best, 230);
        else if (word.includes(token)) best = Math.max(best, 145);
        else if (token.length >= 4) {
          const allowed = token.length >= 8 ? 2 : 1;
          if (distance(token, word) <= allowed) best = Math.max(best, 105);
        }
      }
      if (!best) return 0;
      score += best;
    }
    return score;
  }

  function bestStudents(students, query, limit = 8) {
    return students
      .map(student => ({ student, score: scoreStudent(student, query) }))
      .filter(item => item.score > 0)
      .sort((a, b) => b.score - a.score || String(a.student.full_name).localeCompare(String(b.student.full_name)))
      .slice(0, limit);
  }

  function exactStudentFromText(students, text) {
    const normalizedText = normalize(text);
    const identifications = String(text).match(/\b\d{10}\b/g) || [];
    for (const identification of identifications) {
      const matches = students.filter(student => normalize(student.identification) === identification);
      if (matches.length === 1) return matches[0];
    }

    const emails = String(text).match(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi) || [];
    for (const email of emails) {
      const cleanEmail = normalize(email);
      const matches = students.filter(student =>
        normalize(student.email) === cleanEmail || normalize(student.personal_email) === cleanEmail,
      );
      if (matches.length === 1) return matches[0];
    }

    const codes = String(text).match(/\b[A-Z0-9]{5,}(?:-[A-Z0-9]+){1,}\b/gi) || [];
    const nameMatch = String(text).match(/Nombres?\s*:\s*([^\n\r]+)/i);
    const combined = normalize(`${nameMatch?.[1] || ''} ${codes[0] || ''}`);
    if (combined) {
      const ranked = bestStudents(students, combined, 2);
      if (ranked.length === 1 || (ranked[0] && ranked[0].score >= (ranked[1]?.score || 0) + 350)) {
        return ranked[0]?.student || null;
      }
    }

    // Como último recurso, busca el nombre completo dentro del texto pegado.
    const direct = students.filter(student => {
      const name = normalize(student.full_name);
      return name.length >= 10 && normalizedText.includes(name);
    });
    return direct.length === 1 ? direct[0] : null;
  }

  function selectedCard(student, registered, automatic) {
    return `
      <div class="smart-student-selected-card">
        <div>
          <span class="smart-student-status">${automatic ? 'Identificado automáticamente' : 'Estudiante seleccionado'}</span>
          <strong>${escapeLocal(student.full_name)}</strong>
          <p>${escapeLocal(student.identification || 'Sin cédula')} · ${escapeLocal(student.career_name || 'Sin carrera')}</p>
          <small>${escapeLocal(student.career_code || student.report_career_code || '')}${student.email ? ` · ${escapeLocal(student.email)}` : ''}</small>
          ${registered ? '<div class="smart-student-warning">Este estudiante ya tiene un registro. Al guardar se actualizará.</div>' : ''}
        </div>
        <button class="button secondary small" type="button" data-change-student>Cambiar estudiante</button>
      </div>`;
  }

  async function enhanceForm(form) {
    if (!form || form.dataset.smartStudentReady === '1') return;
    const select = form.querySelector('select[name="student_id"]');
    const textarea = form.querySelector('textarea[name="text"]');
    if (!select || !textarea || !state.activeReport?.id) return;
    form.dataset.smartStudentReady = '1';

    const originalLabel = select.closest('label');
    if (originalLabel) originalLabel.hidden = true;

    const searchBox = document.createElement('section');
    searchBox.className = 'smart-student-search';
    searchBox.innerHTML = `
      <label class="smart-student-search-label">
        Buscar estudiante de la base
        <input type="search" data-student-search autocomplete="off" spellcheck="false"
          placeholder="Nombre, cédula, correo, código o carrera...">
      </label>
      <p class="smart-student-help">Puede escribir los nombres en cualquier orden y sin tildes. También se toleran errores pequeños.</p>
      <div class="smart-student-results" data-student-results hidden></div>
      <div data-selected-student></div>
    `;
    originalLabel?.insertAdjacentElement('afterend', searchBox);

    const input = searchBox.querySelector('[data-student-search]');
    const results = searchBox.querySelector('[data-student-results]');
    const selectedContainer = searchBox.querySelector('[data-selected-student]');

    let students = [];
    let registeredIds = new Set();
    let selectedStudent = null;
    let manuallySelected = false;

    try {
      const [rosterData, projectData] = await Promise.all([
        api(`/api/reports/${state.activeReport.id}/roster`),
        api(`/api/reports/${state.activeReport.id}/projects`),
      ]);
      students = rosterData.students || [];
      registeredIds = new Set((projectData.projects || []).map(project => Number(project.student_id)).filter(Boolean));
    } catch (error) {
      input.disabled = true;
      input.placeholder = 'No se pudo cargar la base de estudiantes';
      if (typeof toast === 'function') toast(error.message, true);
      return;
    }

    function chooseStudent(student, automatic = false) {
      selectedStudent = student;
      manuallySelected = !automatic;
      select.value = String(student.id);
      input.value = student.full_name;
      results.hidden = true;
      results.innerHTML = '';
      selectedContainer.innerHTML = selectedCard(student, registeredIds.has(Number(student.id)), automatic);
      selectedContainer.querySelector('[data-change-student]')?.addEventListener('click', () => {
        selectedStudent = null;
        manuallySelected = false;
        select.value = '';
        selectedContainer.innerHTML = '';
        input.value = '';
        input.focus();
      });
    }

    function renderResults(query) {
      const ranked = bestStudents(students, query);
      if (!normalize(query)) {
        results.hidden = true;
        results.innerHTML = '';
        return;
      }
      results.hidden = false;
      results.innerHTML = ranked.length
        ? ranked.map(({ student }) => `
            <button type="button" class="smart-student-result" data-student-id="${student.id}">
              <strong>${escapeLocal(student.full_name)}</strong>
              <span>${escapeLocal(student.identification || 'Sin cédula')} · ${escapeLocal(student.career_name || 'Sin carrera')}</span>
              <small>${escapeLocal(student.career_code || student.report_career_code || '')}${student.email ? ` · ${escapeLocal(student.email)}` : ''}</small>
            </button>`).join('')
        : '<div class="smart-student-no-results">No se encontraron coincidencias.</div>';
      results.querySelectorAll('[data-student-id]').forEach(button => {
        button.addEventListener('click', () => {
          const student = students.find(item => Number(item.id) === Number(button.dataset.studentId));
          if (student) chooseStudent(student, false);
        });
      });
    }

    input.addEventListener('input', () => {
      if (selectedStudent && input.value !== selectedStudent.full_name) {
        selectedStudent = null;
        select.value = '';
        selectedContainer.innerHTML = '';
      }
      renderResults(input.value);
    });
    input.addEventListener('focus', () => renderResults(input.value));
    document.addEventListener('click', event => {
      if (!searchBox.contains(event.target)) results.hidden = true;
    });

    let detectionTimer = null;
    function detectFromProjectText() {
      clearTimeout(detectionTimer);
      detectionTimer = setTimeout(() => {
        const detected = exactStudentFromText(students, textarea.value);
        if (detected && (!manuallySelected || Number(selectedStudent?.id) !== Number(detected.id))) {
          chooseStudent(detected, true);
        }
      }, 180);
    }
    textarea.addEventListener('input', detectFromProjectText);
    textarea.addEventListener('paste', () => setTimeout(detectFromProjectText, 0));

    form.addEventListener('submit', event => {
      if (!select.value) {
        event.preventDefault();
        event.stopImmediatePropagation();
        input.focus();
        if (typeof toast === 'function') toast('Busque o identifique primero al estudiante.', true);
      }
    }, true);
  }

  const style = document.createElement('style');
  style.textContent = `
    .smart-student-search { position: relative; margin-bottom: 16px; }
    .smart-student-search-label { display: grid; gap: 7px; font-weight: 700; color: #334155; }
    .smart-student-search input { width: 100%; min-height: 46px; font-size: 15px; }
    .smart-student-help { margin: 6px 0 0; color: #64748b; font-size: 13px; }
    .smart-student-results { position: absolute; z-index: 30; left: 0; right: 0; top: 78px; max-height: 360px; overflow-y: auto; background: white; border: 1px solid #b9cce0; border-radius: 12px; box-shadow: 0 16px 35px rgba(15, 23, 42, .16); padding: 7px; }
    .smart-student-result { display: grid; width: 100%; gap: 3px; padding: 11px 12px; text-align: left; border: 0; border-radius: 9px; background: transparent; cursor: pointer; color: #0f172a; }
    .smart-student-result:hover, .smart-student-result:focus { background: #edf6ff; outline: none; }
    .smart-student-result span, .smart-student-result small { color: #64748b; }
    .smart-student-no-results { padding: 16px; text-align: center; color: #64748b; }
    .smart-student-selected-card { display: flex; justify-content: space-between; gap: 18px; align-items: center; margin-top: 12px; padding: 14px 16px; border: 1px solid #a7c7e8; border-radius: 12px; background: #f1f8ff; }
    .smart-student-selected-card strong { display: block; margin: 2px 0 4px; color: #123f68; }
    .smart-student-selected-card p { margin: 0 0 3px; color: #334155; }
    .smart-student-selected-card small { color: #64748b; }
    .smart-student-status { display: block; color: #18704b; font-size: 12px; font-weight: 800; text-transform: uppercase; letter-spacing: .03em; }
    .smart-student-warning { margin-top: 7px; color: #9a5a00; font-size: 13px; font-weight: 700; }
    @media (max-width: 720px) { .smart-student-selected-card { align-items: flex-start; flex-direction: column; } }
  `;
  document.head.appendChild(style);

  function scan() {
    enhanceForm(tab.querySelector('#project-import-form'));
  }
  new MutationObserver(scan).observe(tab, { childList: true, subtree: true });
  scan();
})();
