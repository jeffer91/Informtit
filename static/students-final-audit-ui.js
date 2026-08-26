(() => {
  let scheduled = false;

  function escapeValue(value) {
    return String(value == null ? '' : value).replace(/[&<>'"]/g, char => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      "'": '&#39;',
      '"': '&quot;',
    }[char]));
  }

  function projectId() {
    return Number(window.state?.activeReport?.project_summary?.period_project_id || 0);
  }

  async function request(path, options = {}) {
    if (typeof api === 'function') return api(path, options);
    const response = await fetch(path, {
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
      ...options,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.ok === false) throw new Error(data.error || `Error ${response.status}`);
    return data;
  }

  function notify(message, isError = false) {
    if (typeof toast === 'function') toast(message, isError);
    else if (isError) alert(message);
  }

  function addOption(select, value, label) {
    if (!select || select.querySelector(`option[value="${value}"]`)) return;
    const option = document.createElement('option');
    option.value = value;
    option.textContent = label;
    select.appendChild(option);
  }

  function ensureStyles() {
    if (document.getElementById('student-final-audit-style')) return;
    const style = document.createElement('style');
    style.id = 'student-final-audit-style';
    style.textContent = `
      .student-final-audit-tools { margin-top: 16px; }
      .student-final-audit-list { display: grid; gap: 12px; }
      .student-final-audit-card { border: 1px solid var(--border, #d9dee7); border-radius: 12px; padding: 14px; background: var(--surface, #fff); }
      .student-final-audit-card header { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }
      .student-final-audit-search { display: grid; grid-template-columns: minmax(180px, 1fr) auto; gap: 8px; margin-top: 10px; }
      .student-final-audit-results { display: grid; gap: 6px; margin-top: 8px; }
      .student-final-audit-result { text-align: left; white-space: normal; }
      .student-final-audit-actions { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px; }
      .student-audit-link-list { display: grid; gap: 10px; margin: 12px 0; max-height: 58vh; overflow: auto; }
      .student-audit-link { border: 1px solid var(--border, #d9dee7); border-radius: 10px; padding: 12px; }
      .student-audit-link small { display: block; margin-top: 4px; }
      .student-audit-row-button { margin-top: 6px; }
      #student-final-audit-dialog { width: min(760px, 94vw); border: 0; border-radius: 14px; padding: 0; }
      #student-final-audit-dialog::backdrop { background: rgb(15 23 42 / .45); }
      #student-final-audit-dialog .dialog-form { padding: 18px; }
    `;
    document.head.appendChild(style);
  }

  function moduleLabel(module) {
    return ({
      NUCLEI: 'Núcleos',
      COMPLEXIVE: 'Examen Complexivo',
      THESIS: 'Trabajo de Titulación',
    }[module] || module || 'Fuente');
  }

  function modalityLabel(value) {
    return String(value || '') === 'en_linea' ? 'Online' : 'Presencial';
  }

  function ensureDialog() {
    let dialog = document.getElementById('student-final-audit-dialog');
    if (dialog) return dialog;
    dialog = document.createElement('dialog');
    dialog.id = 'student-final-audit-dialog';
    dialog.innerHTML = `
      <form method="dialog" class="dialog-form">
        <div class="dialog-head">
          <div><h2 id="student-final-audit-title">Vínculos del estudiante</h2><p id="student-final-audit-subtitle"></p></div>
          <button class="icon-button" value="cancel" aria-label="Cerrar">×</button>
        </div>
        <div id="student-final-audit-dialog-body"></div>
        <div class="dialog-actions"><button class="button secondary" value="cancel">Cerrar</button></div>
      </form>`;
    document.body.appendChild(dialog);
    return dialog;
  }

  async function refreshStudents() {
    const button = document.getElementById('period-student-refresh');
    if (button) {
      button.click();
      return;
    }
    const studentsButton = document.querySelector('[data-period-students-view]');
    studentsButton?.click();
  }

  function renderLinkDialog(view, studentId) {
    const data = view.__finalAuditData;
    const student = (data?.students || []).find(row => Number(row.id) === Number(studentId));
    if (!student) return;
    const dialog = ensureDialog();
    dialog.querySelector('#student-final-audit-title').textContent = student.full_name || 'Estudiante';
    dialog.querySelector('#student-final-audit-subtitle').textContent =
      `${student.identification || 'Sin cédula visible'} · ${student.career_name || 'Sin carrera'} · ${modalityLabel(student.modality)}`;
    const links = Array.isArray(student.source_links) ? student.source_links : [];
    const body = dialog.querySelector('#student-final-audit-dialog-body');
    body.innerHTML = links.length
      ? `<div class="student-audit-link-list">${links.map(link => `
          <article class="student-audit-link">
            <strong>${escapeValue(moduleLabel(link.source_module))}</strong>
            <small>${escapeValue(link.source_name || 'Sin nombre de origen')}</small>
            <small>${escapeValue(link.match_method || 'Automático')} · ${escapeValue(link.match_status || 'OK')}${link.match_confidence != null ? ` · ${escapeValue(link.match_confidence)}%` : ''}</small>
            <button type="button" class="button secondary compact final-audit-unlink"
              data-link-id="${Number(link.id)}">Desvincular y revisar</button>
          </article>`).join('')}</div>`
      : '<div class="empty-mini">Este estudiante no tiene vínculos académicos activos.</div>';
    dialog.showModal();
  }

  function openLinkCard(link) {
    const linked = Number(link.period_student_id || 0) > 0;
    return `<article class="student-final-audit-card" data-final-link="${Number(link.id)}">
      <header>
        <div>
          <strong>${escapeValue(moduleLabel(link.source_module))}</strong>
          <small>${escapeValue(link.match_status || 'REVIEW_REQUIRED')} · ${escapeValue(modalityLabel(link.dataset_modality))}</small>
        </div>
        <span>${escapeValue(link.match_confidence == null ? '—' : `${link.match_confidence}%`)}</span>
      </header>
      <p><strong>${escapeValue(link.source_name || 'Sin nombre')}</strong><br>
      ${escapeValue(link.source_identification || 'sin cédula en la fuente')} · ${escapeValue(link.source_email || 'sin correo')}</p>
      ${link.detail ? `<p><small>${escapeValue(link.detail)}</small></p>` : ''}
      <div class="student-final-audit-search">
        <input type="search" data-final-search-input="${Number(link.id)}"
          placeholder="Buscar cédula, nombre, correo o carrera">
        <button type="button" class="button secondary compact final-audit-search"
          data-link-id="${Number(link.id)}">Buscar estudiante</button>
      </div>
      <div class="student-final-audit-results" data-final-results="${Number(link.id)}"></div>
      ${linked ? `<div class="student-final-audit-actions">
        <button type="button" class="button secondary compact final-audit-unlink"
          data-link-id="${Number(link.id)}">Desvincular asociación actual</button>
      </div>` : ''}
    </article>`;
  }

  function bindView(view) {
    if (view.dataset.finalAuditBound === '1') return;
    view.dataset.finalAuditBound = '1';

    view.addEventListener('click', async event => {
      const review = event.target.closest('.student-audit-row-button');
      if (review) {
        renderLinkDialog(view, Number(review.dataset.studentId));
        return;
      }

      const searchButton = event.target.closest('.final-audit-search');
      if (searchButton) {
        const pid = projectId();
        const linkId = Number(searchButton.dataset.linkId);
        const input = view.querySelector(`[data-final-search-input="${linkId}"]`);
        const resultHost = view.querySelector(`[data-final-results="${linkId}"]`);
        if (!pid || !resultHost) return;
        searchButton.disabled = true;
        try {
          const query = encodeURIComponent(input?.value || '');
          const data = await request(`/api/period-projects/${pid}/students-domain/matches/${linkId}/candidates?q=${query}`);
          const candidates = data.candidates || [];
          resultHost.innerHTML = candidates.length
            ? candidates.map(candidate => `
                <button type="button" class="button secondary compact student-final-audit-result final-audit-confirm"
                  data-link-id="${linkId}" data-student-id="${Number(candidate.student_id)}">
                  ${escapeValue(candidate.full_name)} · ${escapeValue(candidate.identification || 'sin cédula')} · ${escapeValue(candidate.career_name || '')}
                </button>`).join('')
            : '<small>No se encontraron estudiantes de Requisitos en este mismo dataset.</small>';
        } catch (error) {
          notify(error.message, true);
        } finally {
          searchButton.disabled = false;
        }
        return;
      }

      const confirm = event.target.closest('.final-audit-confirm');
      if (confirm) {
        const pid = projectId();
        if (!pid) return;
        confirm.disabled = true;
        try {
          await request(`/api/period-projects/${pid}/students-domain/matches/${Number(confirm.dataset.linkId)}/confirm`, {
            method: 'POST',
            body: JSON.stringify({ student_id: Number(confirm.dataset.studentId) }),
          });
          notify('Coincidencia confirmada.');
          await refreshStudents();
        } catch (error) {
          notify(error.message, true);
          confirm.disabled = false;
        }
        return;
      }

      const unlink = event.target.closest('.final-audit-unlink');
      if (unlink) {
        const pid = projectId();
        if (!pid) return;
        if (!window.confirm('¿Desvincular este registro y dejarlo pendiente de revisión manual?')) return;
        unlink.disabled = true;
        try {
          await request(`/api/period-projects/${pid}/students-domain/matches/${Number(unlink.dataset.linkId)}/unlink`, {
            method: 'POST',
            body: JSON.stringify({}),
          });
          document.getElementById('student-final-audit-dialog')?.close();
          notify('Vínculo desasociado. El registro quedó pendiente de revisión.');
          await refreshStudents();
        } catch (error) {
          notify(error.message, true);
          unlink.disabled = false;
        }
      }
    });
  }

  async function enhance() {
    const view = document.getElementById('period-students-view');
    const pid = projectId();
    if (!view || !pid || !view.querySelector('.student-match-panel')) return;
    if (view.querySelector('[data-final-audit-tools]')) return;

    ensureStyles();
    bindView(view);

    const reconciliation = view.querySelector('#period-student-reconciliation');
    [
      ['AMBIGUOUS', 'Ambiguo'],
      ['GRADE_CONFLICT', 'Conflicto de notas'],
      ['IDENTITY_CONFLICT', 'Conflicto de identidad'],
      ['DUPLICATE', 'Duplicado en Requisitos'],
      ['MODALITY_CONFLICT', 'Duplicado Presencial / Online'],
    ].forEach(([value, label]) => addOption(reconciliation, value, label));

    view.querySelectorAll('.period-process-select').forEach(select => {
      addOption(select, 'DERIVED', 'Restablecer según Requisitos');
    });

    try {
      const data = await request(`/api/period-projects/${pid}/students-domain`);
      view.__finalAuditData = data;

      const sourceAlerts = Number(data.summary?.source_alerts || data.open_links?.length || 0);
      const summaryGrid = view.querySelector('.student-summary-grid');
      if (summaryGrid && !summaryGrid.querySelector('[data-source-alerts]')) {
        summaryGrid.insertAdjacentHTML('beforeend',
          `<div class="student-metric" data-source-alerts><strong>${sourceAlerts}</strong><span>Fuentes por conciliar</span></div>`);
      }

      const byId = new Map((data.students || []).map(row => [Number(row.id), row]));
      view.querySelectorAll('[data-period-student-row]').forEach(rowNode => {
        const routeSelect = rowNode.querySelector('.period-route-select');
        const studentId = Number(routeSelect?.dataset.studentId || 0);
        if (!studentId || !byId.has(studentId)) return;
        const target = rowNode.lastElementChild;
        if (target && !target.querySelector('.student-audit-row-button')) {
          target.insertAdjacentHTML('beforeend',
            `<button type="button" class="button secondary compact student-audit-row-button"
              data-student-id="${studentId}">Revisar vínculos</button>`);
        }
      });

      const panel = view.querySelector('.student-match-panel');
      const links = data.open_links || [];
      panel.insertAdjacentHTML('afterend', `
        <div class="panel student-final-audit-tools" data-final-audit-tools>
          <div class="panel-head">
            <div>
              <h2>Resolución manual avanzada</h2>
              <p>Busque cualquier estudiante de Requisitos del mismo dataset cuando la sugerencia automática no sea suficiente. También puede desvincular una asociación incorrecta sin borrar la evidencia original.</p>
            </div>
            <strong>${links.length}</strong>
          </div>
          ${links.length
            ? `<div class="student-final-audit-list">${links.map(openLinkCard).join('')}</div>`
            : '<div class="empty-mini">No existen fuentes pendientes de conciliación.</div>'}
        </div>`);
    } catch (error) {
      notify(`No se pudo cargar la auditoría avanzada: ${error.message}`, true);
    }
  }

  function scheduleEnhance() {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => {
      scheduled = false;
      enhance();
    });
  }

  const host = document.getElementById('view-report');
  if (host) {
    const observer = new MutationObserver(scheduleEnhance);
    observer.observe(host, { childList: true, subtree: true });
  }
  document.addEventListener('click', event => {
    if (event.target.closest('[data-period-students-view],#period-student-refresh')) {
      setTimeout(scheduleEnhance, 0);
    }
  });
  window.addEventListener('load', scheduleEnhance);
})();