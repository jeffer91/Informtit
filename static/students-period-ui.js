(() => {
  let observerQueued = false;

  function apiRequest(path, options = {}) {
    if (typeof api === 'function') return api(path, options);
    return fetch(path, {
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
      ...options,
    }).then(async response => {
      const data = await response.json().catch(() => ({}));
      if (!response.ok || data.ok === false) throw new Error(data.error || `Error ${response.status}`);
      return data;
    });
  }

  function escapeValue(value) {
    if (typeof escapeHtml === 'function') return escapeHtml(value == null ? '' : value);
    return String(value == null ? '' : value).replace(/[&<>'"]/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
  }

  function projectId() {
    return Number(window.state?.activeReport?.project_summary?.period_project_id || 0);
  }

  function isUnifiedNormal() {
    const project = window.state?.activeReport?.project_summary;
    return Boolean(project?.period_project_id) && String(project?.report_type || 'normal').toLowerCase() !== 'pvc';
  }

  function badge(text, kind = '') {
    return `<span class="student-badge ${kind}">${escapeValue(text)}</span>`;
  }

  function missingBadge(row) {
    const missing = Array.isArray(row.missing_requirements) ? row.missing_requirements : [];
    if (!missing.length) return badge('8/8 habilitantes', 'ok');
    if (missing.length === 1) return badge(`Falta: ${missing[0]}`, 'warn');
    return badge(`${missing.length} pendientes`, 'danger');
  }

  function summaryHtml(summary) {
    return `<div class="student-summary-grid">
      <div class="student-metric"><strong>${summary.students || 0}</strong><span>Total</span></div>
      <div class="student-metric"><strong>${summary.presencial || 0}</strong><span>Presencial</span></div>
      <div class="student-metric"><strong>${summary.online || 0}</strong><span>Online</span></div>
      <div class="student-metric"><strong>${summary.complexive || 0}</strong><span>Complexivo</span></div>
      <div class="student-metric"><strong>${summary.thesis || 0}</strong><span>Trabajo titulación</span></div>
      <div class="student-metric"><strong>${summary.graduated || 0}</strong><span>Graduados oficiales</span></div>
      <div class="student-metric"><strong>${summary.retired || 0}</strong><span>Retirados</span></div>
      <div class="student-metric"><strong>${summary.review || 0}</strong><span>Casos por revisar</span></div>
    </div>`;
  }

  function rowHtml(row) {
    const official = Number(row.official_graduated) === 1 ? badge('Graduado', 'ok') : badge('No graduado', 'muted');
    const reconciliation = row.reconciliation_status === 'OK'
      ? badge('Correcto', 'ok')
      : badge(row.reconciliation_status || 'Revisión', 'warn');
    return `<tr data-period-student-row="1"
      data-search="${escapeValue(`${row.identification || ''} ${row.full_name || ''} ${row.email || ''} ${row.career_name || ''}`.toLowerCase())}"
      data-route="${escapeValue(row.route || '')}" data-modality="${escapeValue(row.modality || '')}"
      data-process="${escapeValue(row.process_status || '')}" data-reconciliation="${escapeValue(row.reconciliation_status || '')}">
      <td><strong>${escapeValue(row.full_name)}</strong><small>${escapeValue(row.identification)}</small><small>${escapeValue(row.email)}</small></td>
      <td>${escapeValue(row.career_name)}<small>${row.modality === 'en_linea' ? 'Online' : 'Presencial'} · ${escapeValue(row.campus || 'Sin sede')}</small></td>
      <td><select class="student-route-select period-route-select" data-student-id="${Number(row.id)}">
        <option value="COMPLEXIVO" ${row.route === 'COMPLEXIVO' ? 'selected' : ''}>Examen Complexivo</option>
        <option value="TRABAJO_TITULACION" ${row.route === 'TRABAJO_TITULACION' ? 'selected' : ''}>Trabajo de Titulación</option>
      </select><small>${row.route_source === 'MANUAL' ? 'Definido manualmente' : row.route_source === 'AUTO_EVIDENCE' ? 'Detectado automáticamente' : 'Complexivo por defecto'}</small></td>
      <td>${missingBadge(row)}
        <select class="student-route-select period-process-select" data-student-id="${Number(row.id)}" title="Permite una corrección manual excepcional del estado">
          <option value="ACTIVO" ${row.process_status === 'ACTIVO' ? 'selected' : ''}>Continúa proceso</option>
          <option value="NO_APROBADO_REQUISITO" ${row.process_status === 'NO_APROBADO_REQUISITO' ? 'selected' : ''}>No aprobado por requisito</option>
          <option value="RETIRADO" ${row.process_status === 'RETIRADO' ? 'selected' : ''}>Retirado</option>
        </select><small>${row.process_status_source === 'MANUAL' ? 'Estado corregido manualmente' : 'Calculado desde Requisitos'}</small>
      </td>
      <td>${badge(row.has_nuclei ? 'Núcleos cargados' : 'Sin Núcleos', row.has_nuclei ? 'ok' : 'muted')}<small>${row.has_complexive ? 'Complexivo cargado' : ''}${row.has_thesis ? `${row.has_complexive ? ' · ' : ''}Trabajo cargado` : ''}</small></td>
      <td>${official}<small>${Number(row.official_titulation_completed) === 1 ? 'Titulación: CUMPLE' : 'Titulación pendiente'}</small></td>
      <td>${reconciliation}<small>${escapeValue(row.reconciliation_detail || '')}</small></td>
    </tr>`;
  }

  function moduleLabel(module) {
    return ({NUCLEI:'Núcleos', COMPLEXIVE:'Examen Complexivo', THESIS:'Trabajo de Titulación', ROUTE:'Ruta de titulación', REQUIREMENTS:'Requisitos'}[module] || module || 'Fuente');
  }

  function openLinkHtml(link) {
    const type = String(link.case_type || 'IDENTITY');
    const candidates = Array.isArray(link.candidates) ? link.candidates.slice(0, 3) : [];
    const status = String(link.match_status || 'REVIEW_REQUIRED');
    const title = moduleLabel(link.source_module);
    const student = link.source_name || 'Sin nombre';
    const identification = link.source_identification || 'sin cédula';
    const occurrences = Number(link.occurrences || 1);

    if (type === 'ROUTE') {
      return `<article class="student-match-card">
        <div><strong>${escapeValue(title)}</strong> ${badge('CONFLICTO DE RUTA', 'warn')}</div>
        <p><strong>${escapeValue(student)}</strong> · ${escapeValue(identification)}</p>
        <p>${escapeValue(link.detail || '')}</p>
        <div class="student-match-candidates">
          <button type="button" class="button secondary compact period-route-case"
            data-student-id="${Number(link.student_id)}" data-route="COMPLEXIVO">Usar Examen Complexivo</button>
          <button type="button" class="button secondary compact period-route-case"
            data-student-id="${Number(link.student_id)}" data-route="TRABAJO_TITULACION">Usar Trabajo de Titulación</button>
        </div>
        <small>La identidad ya está confirmada. Elegir una ruta resuelve el conflicto completo sin borrar la otra evidencia.</small>
      </article>`;
    }

    if (type === 'GRADE') {
      const options = Array.isArray(link.grade_options) ? link.grade_options : [];
      return `<article class="student-match-card">
        <div><strong>${escapeValue(title)}</strong> ${badge('CONFLICTO DE NOTA', 'warn')}</div>
        <p><strong>${escapeValue(student)}</strong> · ${escapeValue(identification)}</p>
        <p>${escapeValue(link.detail || '')}</p>
        <div class="student-match-candidates">
          ${options.map(value => `<button type="button" class="button secondary compact period-grade-case"
            data-student-id="${Number(link.student_id)}"
            data-module="${escapeValue(link.source_module || '')}"
            data-nucleus="${Number(link.nucleus_number || 0)}"
            data-grade="${escapeValue(value)}">Usar ${escapeValue(value)}</button>`).join('')}
        </div>
        <small>Informtit no elige automáticamente entre notas contradictorias. La opción seleccionada queda auditada.</small>
      </article>`;
    }

    if (type === 'OFFICIAL') {
      return `<article class="student-match-card">
        <div><strong>Requisitos</strong> ${badge(status, 'warn')}</div>
        <p><strong>${escapeValue(student)}</strong> · ${escapeValue(identification)}</p>
        <p>${escapeValue(link.detail || '')}</p>
        <small>Requisitos es la fuente maestra. Corrija el dato oficial en esa fuente y vuelva a conciliar.</small>
      </article>`;
    }

    const suggestion = link.suggestion || candidates[0] || null;
    const candidateHtml = candidates.length
      ? `<div class="student-match-candidates">
          ${suggestion ? `<small><strong>Sugerencia de Informtit:</strong> ${escapeValue(suggestion.full_name || '')} · ${escapeValue(suggestion.similarity || link.match_confidence || 0)}%</small>` : ''}
          ${candidates.map((candidate, index) => `
          <button type="button" class="button secondary compact period-match-confirm"
            data-link-id="${Number(link.id)}" data-student-id="${Number(candidate.student_id)}">
            ${index === 0 ? 'Sugerido · ' : ''}${escapeValue(candidate.full_name)} · ${escapeValue(candidate.identification || 'sin cédula')} · ${escapeValue(candidate.similarity || 0)}%
          </button>`).join('')}
        </div>`
      : '';
    return `<article class="student-match-card">
      <div><strong>${escapeValue(title)}</strong> ${badge(status, 'warn')}</div>
      <p><strong>${escapeValue(student)}</strong> · ${escapeValue(identification)} · ${link.dataset_modality === 'en_linea' ? 'Online' : 'Presencial'}</p>
      ${occurrences > 1 ? `<small>${occurrences} evidencias agrupadas en un solo caso.</small>` : ''}
      ${link.detail ? `<p>${escapeValue(link.detail)}</p>` : ''}
      ${candidateHtml}
      <div class="student-final-audit-search">
        <input type="search" data-period-case-search-input="${Number(link.id)}"
          placeholder="Buscar cédula, nombre, correo o carrera">
        <button type="button" class="button secondary compact period-case-search"
          data-link-id="${Number(link.id)}">Buscar estudiante</button>
      </div>
      <div class="student-final-audit-results" data-period-case-results="${Number(link.id)}"></div>
    </article>`;
  }

  function applyFilters(view) {
    const search = (view.querySelector('#period-student-search')?.value || '').trim().toLowerCase();
    const modality = view.querySelector('#period-student-modality')?.value || '';
    const route = view.querySelector('#period-student-route')?.value || '';
    const process = view.querySelector('#period-student-process')?.value || '';
    const reconciliation = view.querySelector('#period-student-reconciliation')?.value || '';
    view.querySelectorAll('[data-period-student-row]').forEach(row => {
      row.hidden = !(
        (!search || row.dataset.search.includes(search)) &&
        (!modality || row.dataset.modality === modality) &&
        (!route || row.dataset.route === route) &&
        (!process || row.dataset.process === process) &&
        (!reconciliation || row.dataset.reconciliation === reconciliation)
      );
    });
  }

  function getView() {
    let view = document.getElementById('period-students-view');
    if (!view) {
      view = document.createElement('div');
      view.id = 'period-students-view';
      view.style.display = 'none';
      const tabs = document.getElementById('report-tabs');
      tabs?.insertAdjacentElement('afterend', view);
    }
    return view;
  }

  async function renderGlobalStudents() {
    const pid = projectId();
    const view = getView();
    if (!pid || !view) return;
    view.innerHTML = '<div class="panel"><p>Cargando estudiantes Presencial + Online...</p></div>';
    try {
      const data = await apiRequest(`/api/period-projects/${pid}/students-domain`);
      const students = data.students || [];
      const openLinks = data.open_links || [];
      view.innerHTML = `<div class="panel">
        <div class="panel-head"><div><h2>Estudiantes del período</h2><p>Vista global. Requisitos conserva la identidad oficial; todos parten por Complexivo y los casos excepcionales se cambian aquí a Trabajo de Titulación.</p></div>
          <button class="button secondary" id="period-student-refresh" type="button" title="Identifica y corrige automáticamente todos los casos seguros; deja únicamente las decisiones ambiguas para revisión">Reconciliar y resolver seguros</button></div>
        ${summaryHtml(data.summary || {})}
        <div class="student-filters">
          <input id="period-student-search" placeholder="Buscar por cédula, nombre, correo o carrera">
          <select id="period-student-modality"><option value="">Presencial + Online</option><option value="presencial">Presencial</option><option value="en_linea">Online</option></select>
          <select id="period-student-route"><option value="">Todas las rutas</option><option value="COMPLEXIVO">Complexivo</option><option value="TRABAJO_TITULACION">Trabajo de Titulación</option></select>
          <select id="period-student-process"><option value="">Todos los estados</option><option value="ACTIVO">Continúa proceso</option><option value="NO_APROBADO_REQUISITO">Falta un requisito</option><option value="RETIRADO">Retirado</option></select>
          <select id="period-student-reconciliation"><option value="">Toda conciliación</option><option value="OK">Correctos</option><option value="ROUTE_CONFLICT">Conflicto de ruta</option><option value="OFFICIAL_DATA_CONFLICT">Conflicto oficial</option><option value="REVIEW_REQUIRED">Requiere revisión</option><option value="UNMATCHED">Sin coincidencia</option></select>
        </div>
        <div class="table-scroll"><table class="student-table"><thead><tr><th>Estudiante</th><th>Carrera</th><th>Ruta</th><th>Requisitos / estado</th><th>Evidencia</th><th>Oficial</th><th>Conciliación</th></tr></thead><tbody>${students.map(rowHtml).join('')}</tbody></table></div>
      </div>
      <div class="panel student-match-panel">
        <div class="panel-head"><div><h2>Casos que requieren atención</h2><p>Informtit resuelve automáticamente lo seguro. Aquí quedan únicamente identidades ambiguas, personas fuera de población, rutas dobles, notas contradictorias o conflictos de Requisitos.</p></div><strong>${openLinks.length}</strong></div>
        ${openLinks.length ? `<div class="student-match-list">${openLinks.map(openLinkHtml).join('')}</div>` : '<div class="empty-mini">No existen discrepancias de matching pendientes.</div>'}
      </div>`;

      view.querySelectorAll('#period-student-search,#period-student-modality,#period-student-route,#period-student-process,#period-student-reconciliation').forEach(control => {
        control.addEventListener('input', () => applyFilters(view));
        control.addEventListener('change', () => applyFilters(view));
      });
      const reconcileButton = view.querySelector('#period-student-refresh');
      reconcileButton?.addEventListener('click', async () => {
        reconcileButton.disabled = true;
        const previousText = reconcileButton.textContent;
        reconcileButton.textContent = 'Reconciliando...';
        try {
          await apiRequest(`/api/period-projects/${pid}/students-domain/reconcile`, {
            method: 'POST', body: JSON.stringify({}),
          });
          if (typeof toast === 'function') toast('Conciliación actualizada.');
          await renderGlobalStudents();
        } catch (error) {
          if (typeof toast === 'function') toast(error.message, true); else alert(error.message);
          reconcileButton.disabled = false;
          reconcileButton.textContent = previousText;
        }
      });
      view.querySelectorAll('.period-route-select').forEach(select => {
        select.addEventListener('change', async event => {
          const studentId = Number(event.target.dataset.studentId);
          event.target.disabled = true;
          try {
            await apiRequest(`/api/period-projects/${pid}/students-domain/${studentId}/route`, {
              method: 'PUT', body: JSON.stringify({route: event.target.value}),
            });
            await renderGlobalStudents();
          } catch (error) {
            if (typeof toast === 'function') toast(error.message, true); else alert(error.message);
            await renderGlobalStudents();
          }
        });
      });
      view.querySelectorAll('.period-process-select').forEach(select => {
        select.addEventListener('change', async event => {
          const studentId = Number(event.target.dataset.studentId);
          event.target.disabled = true;
          try {
            await apiRequest(`/api/period-projects/${pid}/students-domain/${studentId}/process-status`, {
              method: 'PUT', body: JSON.stringify({process_status: event.target.value}),
            });
            await renderGlobalStudents();
          } catch (error) {
            if (typeof toast === 'function') toast(error.message, true); else alert(error.message);
            await renderGlobalStudents();
          }
        });
      });
      view.querySelectorAll('.period-match-confirm').forEach(button => {
        button.addEventListener('click', async () => {
          button.disabled = true;
          try {
            await apiRequest(`/api/period-projects/${pid}/students-domain/matches/${Number(button.dataset.linkId)}/confirm`, {
              method: 'POST', body: JSON.stringify({student_id: Number(button.dataset.studentId)}),
            });
            await renderGlobalStudents();
          } catch (error) {
            if (typeof toast === 'function') toast(error.message, true); else alert(error.message);
            button.disabled = false;
          }
        });
      });

      view.querySelectorAll('.period-route-case').forEach(button => {
        button.addEventListener('click', async () => {
          button.disabled = true;
          try {
            await apiRequest(`/api/period-projects/${pid}/students-domain/${Number(button.dataset.studentId)}/route`, {
              method: 'PUT', body: JSON.stringify({route: button.dataset.route}),
            });
            if (typeof toast === 'function') toast('Ruta resuelta y guardada.');
            await renderGlobalStudents();
          } catch (error) {
            if (typeof toast === 'function') toast(error.message, true); else alert(error.message);
            button.disabled = false;
          }
        });
      });

      view.querySelectorAll('.period-grade-case').forEach(button => {
        button.addEventListener('click', async () => {
          button.disabled = true;
          try {
            await apiRequest(`/api/period-projects/${pid}/students-domain/grade-conflicts/resolve`, {
              method: 'POST',
              body: JSON.stringify({
                module: button.dataset.module,
                student_id: Number(button.dataset.studentId),
                nucleus_number: Number(button.dataset.nucleus || 0),
                grade: button.dataset.grade,
              }),
            });
            if (typeof toast === 'function') toast('Calificación seleccionada y auditada.');
            await renderGlobalStudents();
          } catch (error) {
            if (typeof toast === 'function') toast(error.message, true); else alert(error.message);
            button.disabled = false;
          }
        });
      });

      view.querySelectorAll('.period-case-search').forEach(button => {
        button.addEventListener('click', async () => {
          const linkId = Number(button.dataset.linkId);
          const input = view.querySelector(`[data-period-case-search-input="${linkId}"]`);
          const host = view.querySelector(`[data-period-case-results="${linkId}"]`);
          if (!host) return;
          button.disabled = true;
          try {
            const q = encodeURIComponent(input?.value || '');
            const result = await apiRequest(`/api/period-projects/${pid}/students-domain/matches/${linkId}/candidates?q=${q}`);
            const candidates = result.candidates || [];
            host.innerHTML = candidates.length
              ? candidates.slice(0, 3).map((candidate, index) => `
                <button type="button" class="button secondary compact period-case-search-confirm"
                  data-link-id="${linkId}" data-student-id="${Number(candidate.student_id)}">
                  ${index === 0 ? 'Sugerido · ' : ''}${escapeValue(candidate.full_name)} ·
                  ${escapeValue(candidate.identification || 'sin cédula')}
                </button>`).join('')
              : '<small>No se encontraron estudiantes compatibles en Requisitos.</small>';
            host.querySelectorAll('.period-case-search-confirm').forEach(candidateButton => {
              candidateButton.addEventListener('click', async () => {
                candidateButton.disabled = true;
                try {
                  await apiRequest(`/api/period-projects/${pid}/students-domain/matches/${Number(candidateButton.dataset.linkId)}/confirm`, {
                    method: 'POST',
                    body: JSON.stringify({student_id: Number(candidateButton.dataset.studentId)}),
                  });
                  if (typeof toast === 'function') toast('Asociación confirmada.');
                  await renderGlobalStudents();
                } catch (error) {
                  if (typeof toast === 'function') toast(error.message, true); else alert(error.message);
                  candidateButton.disabled = false;
                }
              });
            });
          } catch (error) {
            if (typeof toast === 'function') toast(error.message, true); else alert(error.message);
          } finally {
            button.disabled = false;
          }
        });
      });
    } catch (error) {
      view.innerHTML = `<div class="empty-state"><h3>No se pudo cargar Estudiantes</h3><p>${escapeValue(error.message)}</p></div>`;
    }
  }

  function showGlobalStudents() {
    if (!isUnifiedNormal()) return;
    const all = document.getElementById('period-all-view');
    if (all) all.style.display = 'none';
    document.querySelectorAll('.tab-content').forEach(node => { node.style.display = 'none'; });
    const tabs = document.getElementById('report-tabs');
    if (tabs) tabs.style.display = 'none';
    const view = getView();
    view.style.display = '';
    document.querySelectorAll('[data-period-view]').forEach(button => button.classList.remove('active'));
    const studentsButton = document.querySelector('[data-period-students-view]');
    studentsButton?.classList.add('active');
    renderGlobalStudents();
  }

  function hideGlobalStudents() {
    const view = document.getElementById('period-students-view');
    if (view) view.style.display = 'none';
    document.querySelector('[data-period-students-view]')?.classList.remove('active');
  }

  function ensureButton() {
    if (!isUnifiedNormal()) {
      hideGlobalStudents();
      return;
    }
    const filter = document.querySelector('#period-project-controls .period-filter');
    if (!filter || filter.querySelector('[data-period-students-view]')) return;
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'button small';
    button.dataset.periodStudentsView = '1';
    button.textContent = 'Estudiantes';
    button.addEventListener('click', showGlobalStudents);
    filter.appendChild(button);
  }

  document.addEventListener('click', event => {
    if (event.target.closest('[data-period-view]')) hideGlobalStudents();
  }, true);

  const observer = new MutationObserver(() => {
    if (observerQueued) return;
    observerQueued = true;
    requestAnimationFrame(() => {
      observerQueued = false;
      ensureButton();
    });
  });
  observer.observe(document.documentElement, {subtree: true, childList: true});
  document.addEventListener('DOMContentLoaded', ensureButton);
  setTimeout(ensureButton, 0);
})();