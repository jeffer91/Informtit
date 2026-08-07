(() => {
  let busy = false;
  let scheduled = false;

  function esc(value = '') {
    return typeof escapeHtml === 'function'
      ? escapeHtml(String(value))
      : String(value).replace(/[&<>"']/g, character => ({
          '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;',
        })[character]);
  }

  function fmt(value) {
    const number = Number(value);
    return Number.isFinite(number) ? number.toFixed(2).replace('.', ',') : '—';
  }

  function reportId() {
    return Number(window.state?.activeReport?.id || 0);
  }

  function issueDetail() {
    return document.querySelector('#tab-nuclei [data-minimal-issues-detail]');
  }

  function candidateOptions(item) {
    const suggestions = item.suggestions || [];
    if (!suggestions.length) {
      return '<option value="">Sin candidatos habilitados</option>';
    }
    return [
      '<option value="">Seleccione el estudiante correcto</option>',
      ...suggestions.map(candidate => `
        <option value="${Number(candidate.student_id)}">
          ${esc(candidate.full_name)} · ${esc(candidate.identification || 'sin cédula')} · ${Number(candidate.similarity || 0).toFixed(1)}%
        </option>`),
    ].join('');
  }

  function unmatchedMarkup(items) {
    if (!items.length) return '';
    return `<section class="match-resolver-group">
      <div class="match-resolver-title">
        <strong>${items.length} registro${items.length === 1 ? '' : 's'} sin asociación exacta</strong>
        <span>Seleccione la persona correcta. Informtit recordará la relación para futuras cargas.</span>
      </div>
      <div class="match-resolver-list">
        ${items.map((item, index) => `
          <article class="match-resolver-row" data-match-row="${index}">
            <div class="match-source">
              <strong>${esc(item.full_name || 'Sin nombre')}</strong>
              <span>${esc(item.email || 'Sin correo')} · ${esc(item.career_name || 'Sin carrera')} · Núcleo ${Number(item.nucleus_number || 0)} · nota ${fmt(item.grade)}</span>
              <small>${esc(item.reason || 'Sin coincidencia')}</small>
            </div>
            <div class="match-action">
              <select data-match-student>${candidateOptions(item)}</select>
              <button class="button primary small" type="button" data-save-manual-match="${index}">Vincular</button>
            </div>
          </article>`).join('')}
      </div>
    </section>`;
  }

  function conflictMarkup(conflicts, rows) {
    if (!conflicts.length) return '';
    const byId = new Map((rows || []).map(row => [Number(row.student_id), row]));
    return `<section class="match-resolver-group">
      <div class="match-resolver-title">
        <strong>${conflicts.length} conflicto${conflicts.length === 1 ? '' : 's'} de nota</strong>
        <span>Las notas iguales se consolidan automáticamente. Solo debe elegir cuando los valores son diferentes.</span>
      </div>
      <div class="match-resolver-list">
        ${conflicts.map((conflict, index) => {
          const student = byId.get(Number(conflict.student_id)) || {};
          return `<article class="match-resolver-row conflict-row" data-conflict-row="${index}">
            <div class="match-source">
              <strong>${esc(student.full_name || 'Estudiante')}</strong>
              <span>${esc(student.career_name || '')} · Núcleo ${Number(conflict.nucleus_number || 0)}</span>
              <small>Se encontraron valores diferentes para el mismo núcleo.</small>
            </div>
            <div class="grade-choice">
              ${(conflict.grades || []).map(grade => `
                <button class="button secondary small" type="button"
                  data-resolve-grade
                  data-student-id="${Number(conflict.student_id)}"
                  data-nucleus-number="${Number(conflict.nucleus_number)}"
                  data-grade="${Number(grade)}">Usar ${fmt(grade)}</button>`).join('')}
            </div>
          </article>`;
        }).join('')}
      </div>
    </section>`;
  }

  async function refreshResolver() {
    const detail = issueDetail();
    const id = reportId();
    if (!detail || detail.hidden || !id || busy) return;
    busy = true;
    try {
      const data = await api(`/api/reports/${id}/nuclei/eligibility`);
      if (reportId() !== id) return;
      let resolver = detail.querySelector('[data-nuclei-match-resolver]');
      if (!resolver) {
        resolver = document.createElement('div');
        resolver.dataset.nucleiMatchResolver = 'true';
        detail.prepend(resolver);
      }
      const unmatched = data.unmatched || [];
      const conflicts = data.grade_conflicts || [];
      resolver.innerHTML = unmatched.length || conflicts.length
        ? `${unmatchedMarkup(unmatched)}${conflictMarkup(conflicts, data.rows || [])}`
        : '<div class="empty-mini">No quedan novedades de coincidencias o notas por resolver.</div>';
      resolver._eligibility = data;
    } catch (error) {
      const detailNow = issueDetail();
      if (detailNow) {
        let resolver = detailNow.querySelector('[data-nuclei-match-resolver]');
        if (!resolver) {
          resolver = document.createElement('div');
          resolver.dataset.nucleiMatchResolver = 'true';
          detailNow.prepend(resolver);
        }
        resolver.innerHTML = `<div class="empty-mini">${esc(error.message)}</div>`;
      }
    } finally {
      busy = false;
    }
  }

  function scheduleRefresh() {
    if (scheduled) return;
    scheduled = true;
    setTimeout(() => {
      scheduled = false;
      refreshResolver();
    }, 0);
  }

  document.addEventListener('click', async event => {
    if (event.target.closest('[data-toggle-minimal-issues]')) {
      scheduleRefresh();
      return;
    }

    const manualButton = event.target.closest('[data-save-manual-match]');
    if (manualButton) {
      const detail = issueDetail();
      const resolver = detail?.querySelector('[data-nuclei-match-resolver]');
      const data = resolver?._eligibility;
      const index = Number(manualButton.dataset.saveManualMatch);
      const item = data?.unmatched?.[index];
      const row = manualButton.closest('[data-match-row]');
      const selected = Number(row?.querySelector('[data-match-student]')?.value || 0);
      if (!item || !selected) {
        toast('Seleccione el estudiante correcto.', true);
        return;
      }
      manualButton.disabled = true;
      try {
        await api(`/api/reports/${reportId()}/nuclei/manual-match`, {
          method: 'POST',
          body: JSON.stringify({
            source_email: item.email || '',
            source_name: item.full_name || '',
            career_name: item.career_name || '',
            student_id: selected,
          }),
        });
        toast('Coincidencia guardada. La nota quedó vinculada al estudiante.');
        renderReport();
      } catch (error) {
        toast(error.message, true);
        manualButton.disabled = false;
      }
      return;
    }

    const gradeButton = event.target.closest('[data-resolve-grade]');
    if (gradeButton) {
      gradeButton.disabled = true;
      try {
        await api(`/api/reports/${reportId()}/nuclei/grade-resolution`, {
          method: 'POST',
          body: JSON.stringify({
            student_id: Number(gradeButton.dataset.studentId),
            nucleus_number: Number(gradeButton.dataset.nucleusNumber),
            chosen_grade: Number(gradeButton.dataset.grade),
          }),
        });
        toast('Nota seleccionada y registrada.');
        renderReport();
      } catch (error) {
        toast(error.message, true);
        gradeButton.disabled = false;
      }
    }
  });

  const tab = document.querySelector('#tab-nuclei');
  if (tab) {
    new MutationObserver(mutations => {
      if (!mutations.some(mutation => mutation.type === 'childList' && mutation.addedNodes.length)) return;
      const detail = issueDetail();
      if (detail && !detail.hidden && !detail.querySelector('[data-nuclei-match-resolver]')) {
        scheduleRefresh();
      }
    }).observe(tab, { childList: true, subtree: true });
  }

  const style = document.createElement('style');
  style.textContent = `
    #tab-nuclei [data-minimal-issues-detail] > details { display: none !important; }
    .match-resolver-group { display: grid; gap: 10px; margin-bottom: 14px; }
    .match-resolver-title { display: grid; gap: 3px; }
    .match-resolver-title strong { color: #173b57; }
    .match-resolver-title span { color: #64748b; font-size: 12px; }
    .match-resolver-list { display: grid; gap: 8px; }
    .match-resolver-row { display: grid; grid-template-columns: minmax(280px, 1.2fr) minmax(330px, 1fr); gap: 14px; align-items: center; padding: 12px; border: 1px solid #e2e8f0; border-radius: 12px; background: #fff; }
    .match-source { display: grid; gap: 3px; }
    .match-source span { color: #475569; font-size: 12px; }
    .match-source small { color: #9a3412; }
    .match-action { display: grid; grid-template-columns: 1fr auto; gap: 8px; align-items: center; }
    .grade-choice { display: flex; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }
    @media (max-width: 900px) {
      .match-resolver-row { grid-template-columns: 1fr; }
      .match-action { grid-template-columns: 1fr; }
      .grade-choice { justify-content: flex-start; }
    }
  `;
  document.head.appendChild(style);
})();
