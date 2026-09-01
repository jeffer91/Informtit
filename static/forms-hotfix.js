// Informtit 0.4: el reporte general se carga dentro del informe activo.
(function () {
  const css = document.createElement('link');
  css.rel = 'stylesheet';
  css.href = '/import-extra.css';
  document.head.appendChild(css);

  const baseRenderReport = renderReport;
  let preview = null;
  let rosterCache = null;
  let lastOpenedReportId = null;

  const val = (form, name) => form.elements.namedItem(name)?.value || '';
  const normalize = value => String(value || '').trim().toUpperCase();
  const readableModality = modality => modality === 'en_linea' ? 'en línea' : 'presencial';

  function setPage(id, title, subtitle) {
    $$('.view').forEach(view => view.classList.remove('active'));
    document.querySelector(`#${id}`)?.classList.add('active');
    $$('.nav-item').forEach(button => button.classList.remove('active'));
    $('#page-title').textContent = title;
    $('#page-subtitle').textContent = subtitle;
  }

  async function loadSettings() {
    const data = await api('/api/institutional-settings');
    const form = $('#institutional-settings-form');
    if (form) {
      Object.entries(data.settings || {}).forEach(([key, value]) => {
        const input = form.elements.namedItem(key);
        if (input) input.value = value || '';
      });
    }
    return data.settings || {};
  }

  function addSettings() {
    if (document.querySelector('[data-fixed-settings]')) return;
    const nav = document.querySelector('.sidebar nav');
    const button = document.createElement('button');
    button.className = 'nav-item';
    button.textContent = 'Configuración institucional';
    button.dataset.fixedSettings = '1';
    nav.appendChild(button);

    const view = document.createElement('section');
    view.id = 'view-fixed-settings';
    view.className = 'view';
    view.innerHTML = `
      <div class="panel">
        <div class="panel-head">
          <div>
            <h2>Responsables institucionales</h2>
            <p>Se registran una sola vez y se aplican a todos los informes.</p>
          </div>
        </div>
        <form id="institutional-settings-form" class="form-panel">
          <div class="responsible-grid">
            <article class="responsible-card">
              <span class="step-chip">Elaboración</span>
              <label>Elaborado por<input name="prepared_by" required></label>
              <label>Cargo<input name="prepared_role" required></label>
            </article>
            <article class="responsible-card">
              <span class="step-chip">Revisión</span>
              <label>Revisado por<input name="reviewed_by" required></label>
              <label>Cargo<input name="reviewed_role" required></label>
            </article>
            <article class="responsible-card">
              <span class="step-chip">Aprobación</span>
              <label>Aprobado por<input name="approved_by" required></label>
              <label>Cargo<input name="approved_role" required></label>
            </article>
          </div>
          <div class="form-actions">
            <button class="button primary">Guardar configuración institucional</button>
          </div>
        </form>
      </div>`;
    document.querySelector('.main').appendChild(view);

    button.onclick = async () => {
      setPage(
        'view-fixed-settings',
        'Configuración institucional',
        'Responsables permanentes para todos los informes.'
      );
      button.classList.add('active');
      await loadSettings();
    };

    $('#institutional-settings-form').addEventListener('submit', async event => {
      event.preventDefault();
      const form = event.currentTarget;
      try {
        await api('/api/institutional-settings', {
          method: 'PUT',
          body: JSON.stringify(Object.fromEntries(new FormData(form).entries())),
        });
        toast('Configuración institucional guardada.');
      } catch (error) {
        toast(error.message, true);
      }
    });
  }

  function ensureRosterTab() {
    const tabs = $('#report-tabs');
    if (!tabs || $('#tab-roster')) return;

    const tabButton = document.createElement('button');
    tabButton.className = 'tab';
    tabButton.dataset.tab = 'roster';
    tabButton.textContent = 'Base de estudiantes';
    tabs.insertBefore(tabButton, tabs.firstChild);

    const content = document.createElement('div');
    content.id = 'tab-roster';
    content.className = 'tab-content';
    const general = $('#tab-general');
    general.parentNode.insertBefore(content, general);
  }

  function activateRosterTab() {
    const button = document.querySelector('.tab[data-tab="roster"]');
    const content = $('#tab-roster');
    if (!button || !content) return;
    $$('.tab').forEach(tab => tab.classList.remove('active'));
    $$('.tab-content').forEach(tab => tab.classList.remove('active'));
    button.classList.add('active');
    content.classList.add('active');
  }

  function addReportImportButton() {
    const actions = document.querySelector('.report-actions');
    if (!actions || $('#report-import-roster')) return;
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'button secondary';
    button.id = 'report-import-roster';
    button.textContent = 'Subir base .xls';
    actions.insertBefore(button, actions.firstChild);
    button.onclick = openImportDialog;
  }

  function statusBadge(value) {
    const status = normalize(value);
    if (status === 'CUMPLE') return '<span class="status-pill status-ok">CUMPLE</span>';
    if (status === 'NO CUMPLE') return '<span class="status-pill status-bad">NO CUMPLE</span>';
    return `<span class="status-pill status-empty">${escapeHtml(value || '—')}</span>`;
  }

  function notesBadge(row) {
    return row.notes_loaded
      ? '<span class="status-pill status-ok">Cargadas</span>'
      : '<span class="status-pill status-empty">Pendientes</span>';
  }

  function rosterMetric(label, value, hint = '') {
    return `<article class="metric roster-metric"><span>${escapeHtml(label)}</span><strong>${value}</strong>${hint ? `<small>${escapeHtml(hint)}</small>` : ''}</article>`;
  }

  function renderRosterRows() {
    if (!rosterCache) return;
    const search = normalize($('#roster-search')?.value);
    const career = $('#roster-career-filter')?.value || '';
    const campus = $('#roster-campus-filter')?.value || '';
    const requirement = $('#roster-requirement-filter')?.value || 'all';

    const rows = rosterCache.students.filter(row => {
      const haystack = normalize([
        row.identification,
        row.full_name,
        row.email,
        row.personal_email,
        row.career_name,
        row.career_code,
        row.phone,
        row.campus,
      ].join(' '));
      if (search && !haystack.includes(search)) return false;
      if (career && row.career_name !== career) return false;
      if (campus && (row.campus || 'Sin sede') !== campus) return false;
      if (requirement === 'complete' && !row.requirements_complete) return false;
      if (requirement === 'pending' && row.requirements_complete) return false;
      if (requirement === 'notes_pending' && row.notes_loaded) return false;
      return true;
    });

    const body = $('#roster-table-body');
    const count = $('#roster-visible-count');
    if (count) count.textContent = `${rows.length} de ${rosterCache.students.length} estudiantes`;
    if (!body) return;

    if (!rows.length) {
      body.innerHTML = '<tr><td colspan="22" class="table-empty">No hay estudiantes que coincidan con los filtros.</td></tr>';
      return;
    }

    body.innerHTML = rows.map((row, index) => `
      <tr>
        <td>${index + 1}</td>
        <td>${escapeHtml(row.identification || '—')}</td>
        <td class="student-name-cell"><strong>${escapeHtml(row.full_name)}</strong><small>${escapeHtml(row.email || '')}</small></td>
        <td>${escapeHtml(row.career_name || '—')}</td>
        <td>${escapeHtml(row.career_code || row.report_career_code || '—')}</td>
        <td>${escapeHtml(row.schedule || '—')}</td>
        <td>${escapeHtml(row.campus || '—')}</td>
        <td>${statusBadge(row.academic_status)}</td>
        <td>${statusBadge(row.documentation_status)}</td>
        <td>${statusBadge(row.financial_status)}</td>
        <td>${statusBadge(row.titulation_status)}</td>
        <td>${statusBadge(row.practices_linkage_status)}</td>
        <td>${statusBadge(row.linkage_status)}</td>
        <td>${statusBadge(row.graduate_followup_status)}</td>
        <td>${statusBadge(row.english_status)}</td>
        <td>${statusBadge(row.data_update_status)}</td>
        <td>${statusBadge(row.titulation_approval)}</td>
        <td>${statusBadge(row.complexive_approval)}</td>
        <td>${escapeHtml(row.personal_email || '—')}</td>
        <td>${escapeHtml(row.phone || '—')}</td>
        <td>${row.requirements_complete ? '<span class="status-pill status-ok">Completo</span>' : `<span class="status-pill status-bad">${row.pending_requirements.length + row.blank_requirements.length} pendientes</span>`}</td>
        <td>${notesBadge(row)}</td>
      </tr>`).join('');
  }

  function bindRosterFilters() {
    ['roster-search', 'roster-career-filter', 'roster-campus-filter', 'roster-requirement-filter']
      .forEach(id => {
        const node = document.getElementById(id);
        if (!node) return;
        node.addEventListener(node.tagName === 'INPUT' ? 'input' : 'change', renderRosterRows);
      });
  }

  function renderRosterData(data) {
    const tab = $('#tab-roster');
    const summary = data.summary;
    const imported = summary.is_imported;
    const modality = readableModality(data.report.modality);

    tab.innerHTML = `
      <div class="panel roster-panel">
        <div class="panel-head roster-head">
          <div>
            <span class="step-chip">Base oficial</span>
            <h2>Estudiantes, carreras y requisitos</h2>
            <p>Este archivo corresponde únicamente a la modalidad <strong>${modality}</strong> del informe activo.</p>
          </div>
          <button type="button" class="button primary" id="roster-upload-btn">${imported ? 'Actualizar reporte .xls' : 'Subir reporte .xls'}</button>
        </div>

        ${!summary.students ? `
          <div class="roster-empty-state">
            <div class="roster-empty-icon">XLS</div>
            <h3>Primero cargue el reporte general de titulación</h3>
            <p>Informtit analizará el Excel antiguo, tomará solo las carreras ${modality} y mostrará estudiantes, requisitos, sedes, jornadas y correos.</p>
            <button type="button" class="button primary" id="roster-empty-upload">Seleccionar reporte .xls</button>
          </div>` : `
          <div class="metrics roster-metrics">
            ${rosterMetric('Estudiantes', summary.students)}
            ${rosterMetric('Carreras', summary.careers)}
            ${rosterMetric('Requisitos completos', summary.requirements_complete)}
            ${rosterMetric('Con pendientes', summary.requirements_pending)}
            ${rosterMetric('Notas cargadas', summary.notes_loaded)}
          </div>

          <section class="roster-section">
            <div class="section-title-row"><div><h3>Resumen de requisitos</h3><p>Cumplimiento de la base importada.</p></div></div>
            <div class="requirement-summary-grid">
              ${data.requirements.map(item => `
                <article class="requirement-card ${item.does_not_comply ? 'has-pending' : ''}">
                  <strong>${escapeHtml(item.label)}</strong>
                  <div><span class="req-ok">${item.complies} cumplen</span><span class="req-bad">${item.does_not_comply} no cumplen</span></div>
                </article>`).join('')}
            </div>
          </section>

          <section class="roster-section">
            <div class="section-title-row"><div><h3>Carreras importadas</h3><p>Distribución del informe activo.</p></div></div>
            <div class="career-chip-grid">
              ${data.careers.map(item => `<div><span>${escapeHtml(item.name)}</span><strong>${item.students}</strong></div>`).join('')}
            </div>
          </section>

          <section class="roster-section">
            <div class="section-title-row"><div><h3>Listado detallado</h3><p id="roster-visible-count"></p></div></div>
            <div class="roster-filters">
              <label>Buscar<input id="roster-search" placeholder="Nombre, cédula, correo o carrera"></label>
              <label>Carrera<select id="roster-career-filter"><option value="">Todas</option>${data.careers.map(item => `<option value="${escapeHtml(item.name)}">${escapeHtml(item.name)}</option>`).join('')}</select></label>
              <label>Sede<select id="roster-campus-filter"><option value="">Todas</option>${data.campuses.map(item => `<option value="${escapeHtml(item.name)}">${escapeHtml(item.name)}</option>`).join('')}</select></label>
              <label>Estado<select id="roster-requirement-filter"><option value="all">Todos</option><option value="complete">Requisitos completos</option><option value="pending">Con requisitos pendientes</option><option value="notes_pending">Sin notas cargadas</option></select></label>
            </div>
            <div class="roster-table-wrap">
              <table class="roster-table">
                <thead><tr>
                  <th>N.º</th><th>Cédula</th><th>Estudiante</th><th>Carrera</th><th>Código</th><th>Jornada</th><th>Sede</th>
                  <th>Académico</th><th>Documentación</th><th>Financiero</th><th>Titulación</th><th>Prácticas/Vinc.</th>
                  <th>Vinculación</th><th>Seguimiento</th><th>Inglés</th><th>Act. datos</th><th>Aprob. titulación</th>
                  <th>Aprob. complexivo</th><th>Correo personal</th><th>Celular</th><th>Resumen</th><th>Notas</th>
                </tr></thead>
                <tbody id="roster-table-body"></tbody>
              </table>
            </div>
          </section>`}
      </div>`;

    $('#roster-upload-btn').onclick = openImportDialog;
    $('#roster-empty-upload')?.addEventListener('click', openImportDialog);
    if (summary.students) {
      rosterCache = data;
      bindRosterFilters();
      renderRosterRows();
    }
  }

  async function renderRosterTab() {
    const tab = $('#tab-roster');
    const reportId = state.activeReport?.id;
    if (!tab || !reportId) return;
    tab.innerHTML = '<div class="panel"><div class="loading-state">Cargando base de estudiantes...</div></div>';
    try {
      const data = await api(`/api/reports/${reportId}/roster`);
      rosterCache = data;
      renderRosterData(data);
    } catch (error) {
      tab.innerHTML = `<div class="panel"><div class="empty-mini">${escapeHtml(error.message)}</div></div>`;
    }
  }

  function createImportDialog() {
    if ($('#active-report-import-dialog')) return;
    const dialog = document.createElement('dialog');
    dialog.id = 'active-report-import-dialog';
    dialog.className = 'wide-dialog import-dialog';
    dialog.innerHTML = `
      <form id="active-report-import-form" class="dialog-form">
        <div class="dialog-head">
          <div><h2>Cargar base de estudiantes</h2><p>El archivo se incorporará únicamente al informe activo.</p></div>
          <button type="button" class="icon-button" id="close-active-import">×</button>
        </div>
        <div id="active-import-upload-step">
          <div class="active-report-context" id="active-report-context"></div>
          <label class="file-drop" for="active-roster-file">
            <strong>Seleccione el reporte antiguo de Excel</strong>
            <span>.xls, .html o .htm</span>
            <input id="active-roster-file" type="file" accept=".xls,.html,.htm" required>
          </label>
          <div id="active-selected-file" class="selected-file">Ningún archivo seleccionado.</div>
          <div class="dialog-actions">
            <button type="button" class="button secondary" id="cancel-active-import">Cancelar</button>
            <button class="button primary" id="analyze-active-roster">Analizar archivo</button>
          </div>
        </div>
        <div id="active-import-confirm-step" hidden>
          <div class="recognized-banner"><strong>Archivo analizado</strong><span id="active-recognized-file"></span></div>
          <div id="active-import-metrics" class="metrics import-metrics"></div>
          <div class="active-modality-note" id="active-modality-note"></div>
          <div id="active-career-preview" class="career-preview-list active-career-preview"></div>
          <div class="form-grid">
            <label>Periodo académico<input name="period" required></label>
            <label>Versión<input name="version" value="1.0"></label>
            <label>Fecha de elaboración<input type="date" name="elaboration_date"></label>
            <label>Código del informe<input name="code"></label>
          </div>
          <div class="replace-warning">
            <strong>La importación reemplazará la base actual de carreras y estudiantes de este informe.</strong>
            <span>Las notas ya cargadas también se eliminarán si se vuelve a importar la base.</span>
          </div>
          <div class="dialog-actions">
            <button type="button" class="button secondary" id="choose-active-file">Elegir otro archivo</button>
            <button type="button" class="button primary" id="commit-active-roster">Importar al informe activo</button>
          </div>
        </div>
      </form>`;
    document.body.appendChild(dialog);

    $('#close-active-import').onclick = () => dialog.close();
    $('#cancel-active-import').onclick = () => dialog.close();
    $('#choose-active-file').onclick = resetImportDialog;
    $('#active-roster-file').onchange = event => {
      const file = event.target.files[0];
      $('#active-selected-file').textContent = file
        ? `${file.name} · ${(file.size / 1024).toFixed(1)} KB`
        : 'Ningún archivo seleccionado.';
    };

    $('#active-report-import-form').addEventListener('submit', analyzeActiveFile);
    $('#commit-active-roster').onclick = commitActiveFile;
  }

  function resetImportDialog() {
    preview = null;
    const form = $('#active-report-import-form');
    form.reset();
    const report = state.activeReport || {};
    form.elements.namedItem('period').value = report.period || '';
    form.elements.namedItem('version').value = report.version || '1.0';
    form.elements.namedItem('elaboration_date').value = report.elaboration_date || new Date().toISOString().slice(0, 10);
    form.elements.namedItem('code').value = report.code || '';
    $('#active-selected-file').textContent = 'Ningún archivo seleccionado.';
    $('#active-import-upload-step').hidden = false;
    $('#active-import-confirm-step').hidden = true;
    $('#active-report-context').innerHTML = `<strong>${escapeHtml(report.name || '')}</strong><span>Modalidad ${readableModality(report.modality)}</span>`;
  }

  function openImportDialog() {
    if (!state.activeReport?.id) return toast('Primero abra un informe.', true);
    createImportDialog();
    resetImportDialog();
    $('#active-report-import-dialog').showModal();
  }

  async function analyzeActiveFile(event) {
    event.preventDefault();
    const file = $('#active-roster-file').files[0];
    if (!file) return toast('Seleccione primero el archivo .xls.', true);
    const button = $('#analyze-active-roster');
    button.disabled = true;
    button.textContent = 'Analizando...';
    try {
      const dataURL = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = reject;
        reader.readAsDataURL(file);
      });
      const data = await api('/api/imports/preview', {
        method: 'POST',
        body: JSON.stringify({ data_url: dataURL, original_name: file.name }),
      });
      preview = data.preview;
      const modality = state.activeReport.modality;
      const count = modality === 'en_linea' ? preview.en_linea : preview.presencial;
      const careers = preview.careers[modality] || [];
      $('#active-import-upload-step').hidden = true;
      $('#active-import-confirm-step').hidden = false;
      $('#active-recognized-file').textContent = `${preview.filename} · ${preview.file_type}`;
      $('#active-import-metrics').innerHTML = [
        ['Registros del archivo', preview.total],
        [`Estudiantes ${readableModality(modality)}`, count],
        ['Carreras que se importarán', careers.length],
        ['Sedes detectadas', Object.keys(preview.campuses || {}).length],
      ].map(([label, value]) => rosterMetric(label, value)).join('');
      $('#active-modality-note').innerHTML = `Se importarán solamente los registros de modalidad <strong>${readableModality(modality)}</strong>.`;
      $('#active-career-preview').innerHTML = careers.length
        ? careers.map(item => `<div><span>${escapeHtml(item.name)}</span><strong>${item.students}</strong></div>`).join('')
        : '<div class="empty-mini">No se encontraron carreras para esta modalidad.</div>';
      const form = $('#active-report-import-form');
      form.elements.namedItem('period').value = preview.period || state.activeReport.period || '';
    } catch (error) {
      toast(error.message, true);
    } finally {
      button.disabled = false;
      button.textContent = 'Analizar archivo';
    }
  }

  async function commitActiveFile() {
    if (!preview?.token || !state.activeReport?.id) {
      return toast('Primero analice el archivo.', true);
    }
    const reportId = state.activeReport.id;
    const form = $('#active-report-import-form');
    const button = $('#commit-active-roster');
    button.disabled = true;
    button.textContent = 'Importando...';
    try {
      const result = await api(`/api/reports/${reportId}/imports/${preview.token}/commit`, {
        method: 'POST',
        body: JSON.stringify({
          period: val(form, 'period'),
          version: val(form, 'version'),
          elaboration_date: val(form, 'elaboration_date'),
          code: val(form, 'code'),
        }),
      });
      $('#active-report-import-dialog').close();
      toast(`${result.students} estudiantes y ${result.careers} carreras importados.`);
      await loadReports();
      await openReport(reportId);
      activateRosterTab();
    } catch (error) {
      toast(error.message, true);
    } finally {
      button.disabled = false;
      button.textContent = 'Importar al informe activo';
    }
  }

  renderGeneralTab = function () {
    const report = state.activeReport;
    $('#tab-general').innerHTML = `
      <form class="form-panel" id="general-form">
        <div class="panel-head">
          <div><h2>Datos generales</h2><p>Los responsables se toman de la configuración institucional.</p></div>
          <button type="button" class="button secondary small" id="open-fixed-settings">Ver responsables</button>
        </div>
        <div class="form-grid three">
          ${readonlyField('name', 'Nombre del informe', report.name)}
          ${readonlyField('period', 'Periodo', report.period)}
          <label>Modalidad<select name="modality" disabled><option value="presencial" ${report.modality === 'presencial' ? 'selected' : ''}>Presencial</option><option value="en_linea" ${report.modality === 'en_linea' ? 'selected' : ''}>En línea</option></select></label>
          ${readonlyField('code', 'Código', report.code)}
          ${field('version', 'Versión', report.version)}
          ${field('elaboration_date', 'Fecha de elaboración', report.elaboration_date, 'date')}
        </div>
        <div class="fixed-responsibles-note">Elaborado, revisado y aprobado se mantienen iguales para todos los informes.</div>
        <div class="form-actions"><button class="button primary">Guardar cambios</button></div>
      </form>`;
    $('#general-form').onsubmit = saveGeneral;
    $('#open-fixed-settings').onclick = () => document.querySelector('[data-fixed-settings]')?.click();
  };

  renderReport = function () {
    const reportId = state.activeReport?.id;
    const isNewSelection = reportId && reportId !== lastOpenedReportId;
    baseRenderReport();
    ensureRosterTab();
    addReportImportButton();
    renderRosterTab();
    if (isNewSelection) activateRosterTab();
    lastOpenedReportId = reportId || null;
  };

  function fixAsyncForms() {
    const reportForm = $('#report-form');
    reportForm?.addEventListener('submit', async event => {
      event.preventDefault();
      event.stopImmediatePropagation();
      const form = event.currentTarget;
      const submit = form.querySelector('#create-report-submit');
      if (submit) submit.disabled = true;
      try {
        const result = await api('/api/reports', {
          method: 'POST',
          body: JSON.stringify(Object.fromEntries(new FormData(form).entries())),
        });
        $('#report-dialog').close();
        form.reset();
        toast('Informe creado. Ahora cargue la base de estudiantes.');
        await loadReports();
        await openReport(result.report_id);
      } catch (error) {
        toast(error.message, true);
      } finally {
        if (submit) submit.disabled = false;
      }
    }, true);

    const careerForm = $('#career-form');
    careerForm?.addEventListener('submit', async event => {
      event.preventDefault();
      event.stopImmediatePropagation();
      const form = event.currentTarget;
      const reportId = state.activeReport?.id;
      if (!reportId) return toast('Primero abra un informe.', true);
      try {
        await api(`/api/reports/${reportId}/careers`, {
          method: 'POST',
          body: JSON.stringify(Object.fromEntries(new FormData(form).entries())),
        });
        $('#career-dialog').close();
        form.reset();
        toast('Carrera agregada.');
        await openReport(reportId);
      } catch (error) {
        toast(error.message, true);
      }
    }, true);
  }

  addSettings();
  ensureRosterTab();
  createImportDialog();
  fixAsyncForms();

  $('#new-report-btn').textContent = 'Nuevo informe';
  $('#new-report-btn').onclick = () => $('#report-dialog').showModal();
})();
