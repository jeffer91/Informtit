// Informtit 0.3: importación inicial del reporte general y responsables institucionales fijos.
(function () {
  const css = document.createElement('link');
  css.rel = 'stylesheet';
  css.href = '/import-extra.css';
  document.head.appendChild(css);

  let preview = null;
  const val = (form, name) => form.elements.namedItem(name)?.value || '';

  function setPage(id, title, subtitle) {
    $$('.view').forEach(v => v.classList.remove('active'));
    document.querySelector(`#${id}`)?.classList.add('active');
    $$('.nav-item').forEach(b => b.classList.remove('active'));
    $('#page-title').textContent = title;
    $('#page-subtitle').textContent = subtitle;
  }

  async function loadSettings() {
    const data = await api('/api/institutional-settings');
    const form = $('#institutional-settings-form');
    if (form) Object.entries(data.settings || {}).forEach(([k, v]) => {
      const input = form.elements.namedItem(k);
      if (input) input.value = v || '';
    });
    return data.settings || {};
  }

  function addSettings() {
    const nav = document.querySelector('.sidebar nav');
    const btn = document.createElement('button');
    btn.className = 'nav-item';
    btn.textContent = 'Configuración institucional';
    btn.dataset.fixedSettings = '1';
    nav.appendChild(btn);

    const view = document.createElement('section');
    view.id = 'view-fixed-settings';
    view.className = 'view';
    view.innerHTML = `<div class="panel"><div class="panel-head"><div><h2>Responsables institucionales</h2><p>Se registran una sola vez y se aplican a todos los informes.</p></div></div><form id="institutional-settings-form" class="form-panel"><div class="responsible-grid"><article class="responsible-card"><span class="step-chip">Elaboración</span><label>Elaborado por<input name="prepared_by" required></label><label>Cargo<input name="prepared_role" required></label></article><article class="responsible-card"><span class="step-chip">Revisión</span><label>Revisado por<input name="reviewed_by" required></label><label>Cargo<input name="reviewed_role" required></label></article><article class="responsible-card"><span class="step-chip">Aprobación</span><label>Aprobado por<input name="approved_by" required></label><label>Cargo<input name="approved_role" required></label></article></div><div class="form-actions"><button class="button primary">Guardar configuración institucional</button></div></form></div>`;
    document.querySelector('.main').appendChild(view);

    btn.onclick = async () => {
      setPage('view-fixed-settings', 'Configuración institucional', 'Responsables permanentes para todos los informes.');
      btn.classList.add('active');
      await loadSettings();
    };

    $('#institutional-settings-form').addEventListener('submit', async e => {
      e.preventDefault();
      const form = e.currentTarget;
      try {
        await api('/api/institutional-settings', { method: 'PUT', body: JSON.stringify(Object.fromEntries(new FormData(form).entries())) });
        toast('Configuración institucional guardada.');
      } catch (error) { toast(error.message, true); }
    });
  }

  function addImporter() {
    const panel = document.createElement('section');
    panel.className = 'import-first-panel';
    panel.innerHTML = `<div><span class="step-chip">Paso 1</span><h2>Subir reporte general de titulación</h2><p>Seleccione el archivo <strong>.xls antiguo</strong>. Informtit reconocerá la tabla HTML, separará las modalidades y creará carreras y estudiantes.</p></div><button class="button primary" id="dashboard-import-btn">Seleccionar reporte .xls</button>`;
    $('#view-dashboard').insertBefore(panel, $('#dashboard-metrics'));

    const dialog = document.createElement('dialog');
    dialog.id = 'import-report-dialog';
    dialog.className = 'wide-dialog import-dialog';
    dialog.innerHTML = `<form id="import-preview-form" class="dialog-form"><div class="dialog-head"><div><h2>Importar reporte general</h2><p>Será la base de estudiantes de los informes presencial y en línea.</p></div><button type="button" class="icon-button" id="close-import-dialog">×</button></div><div id="import-upload-step"><label class="file-drop" for="roster-file"><strong>Seleccione el reporte antiguo de Excel</strong><span>.xls, .html o .htm</span><input id="roster-file" type="file" accept=".xls,.html,.htm" required></label><div id="selected-roster-file" class="selected-file">Ningún archivo seleccionado.</div><div class="dialog-actions"><button type="button" class="button secondary" id="cancel-import-upload">Cancelar</button><button class="button primary" id="analyze-roster-btn">Analizar archivo</button></div></div><div id="import-confirm-step" hidden><div class="recognized-banner"><strong>Archivo reconocido correctamente</strong><span id="recognized-file-type"></span></div><div id="import-preview-metrics" class="metrics import-metrics"></div><div class="career-preview-grid"><article><h3>Carreras presenciales</h3><div id="preview-presencial-careers" class="career-preview-list"></div></article><article><h3>Carreras en línea</h3><div id="preview-online-careers" class="career-preview-list"></div></article></div><div class="form-grid"><label>Nombre del informe<input name="report_name" value="Informe Final del Proceso de Titulación" required></label><label>Periodo académico<input name="period" required></label><label>Versión<input name="version" value="1.0"></label><label>Fecha de elaboración<input type="date" name="elaboration_date"></label><label>Código presencial<input name="code_presencial" placeholder="Opcional"></label><label>Código en línea<input name="code_online" placeholder="Opcional"></label></div><div id="institutional-warning" class="institutional-warning" hidden></div><div class="dialog-actions"><button type="button" class="button secondary" id="choose-another-file">Elegir otro archivo</button><button type="button" class="button primary" id="commit-roster-btn">Importar y crear informes</button></div></div></form>`;
    document.body.appendChild(dialog);

    const reset = () => {
      preview = null;
      const form = $('#import-preview-form');
      form.reset();
      form.elements.namedItem('report_name').value = 'Informe Final del Proceso de Titulación';
      form.elements.namedItem('version').value = '1.0';
      form.elements.namedItem('elaboration_date').value = new Date().toISOString().slice(0, 10);
      $('#selected-roster-file').textContent = 'Ningún archivo seleccionado.';
      $('#import-upload-step').hidden = false;
      $('#import-confirm-step').hidden = true;
    };
    const open = () => { reset(); dialog.showModal(); };
    $('#dashboard-import-btn').onclick = open;
    $('#new-report-btn').textContent = 'Importar reporte';
    $('#new-report-btn').onclick = open;
    $('#close-import-dialog').onclick = () => dialog.close();
    $('#cancel-import-upload').onclick = () => dialog.close();
    $('#choose-another-file').onclick = reset;
    $('#roster-file').onchange = e => {
      const file = e.target.files[0];
      $('#selected-roster-file').textContent = file ? `${file.name} · ${(file.size / 1024).toFixed(1)} KB` : 'Ningún archivo seleccionado.';
    };

    $('#import-preview-form').addEventListener('submit', async e => {
      e.preventDefault();
      const file = $('#roster-file').files[0];
      if (!file) return toast('Seleccione primero el archivo .xls.', true);
      const button = $('#analyze-roster-btn');
      button.disabled = true; button.textContent = 'Analizando...';
      try {
        const dataURL = await new Promise((resolve, reject) => {
          const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.onerror = reject; reader.readAsDataURL(file);
        });
        const data = await api('/api/imports/preview', { method: 'POST', body: JSON.stringify({ data_url: dataURL, original_name: file.name }) });
        preview = data.preview;
        $('#import-upload-step').hidden = true;
        $('#import-confirm-step').hidden = false;
        $('#recognized-file-type').textContent = `${preview.filename} · ${preview.file_type}`;
        $('#import-preview-metrics').innerHTML = [['Estudiantes',preview.total],['Presenciales',preview.presencial],['En línea',preview.en_linea],['Carreras',preview.careers_total]].map(([l,v]) => `<article class="metric"><span>${l}</span><strong>${v}</strong></article>`).join('');
        const rows = items => items.map(i => `<div><span>${escapeHtml(i.name)}</span><strong>${i.students}</strong></div>`).join('');
        $('#preview-presencial-careers').innerHTML = rows(preview.careers.presencial);
        $('#preview-online-careers').innerHTML = rows(preview.careers.en_linea);
        const form = $('#import-preview-form');
        form.elements.namedItem('period').value = preview.period || '';
        const settings = await loadSettings();
        const missing = ['prepared_by','prepared_role','reviewed_by','reviewed_role','approved_by','approved_role'].some(k => !String(settings[k] || '').trim());
        const warning = $('#institutional-warning');
        warning.hidden = !missing;
        if (missing) warning.innerHTML = '<strong>Falta completar la configuración institucional.</strong><span>Puede importar, pero antes de exportar registre los responsables permanentes.</span>';
      } catch (error) { toast(error.message, true); }
      finally { button.disabled = false; button.textContent = 'Analizar archivo'; }
    });

    $('#commit-roster-btn').onclick = async () => {
      if (!preview?.token) return toast('Primero analice el archivo.', true);
      const form = $('#import-preview-form');
      const button = $('#commit-roster-btn');
      const payload = { report_name: val(form,'report_name'), period: val(form,'period'), version: val(form,'version'), elaboration_date: val(form,'elaboration_date'), code_presencial: val(form,'code_presencial'), code_online: val(form,'code_online') };
      button.disabled = true; button.textContent = 'Importando...';
      try {
        const result = await api(`/api/imports/${preview.token}/commit`, { method: 'POST', body: JSON.stringify(payload) });
        dialog.close(); toast(`${result.total} estudiantes importados correctamente.`); await loadReports();
        const id = result.report_ids.presencial || result.report_ids.en_linea; if (id) await openReport(id);
      } catch (error) { toast(error.message, true); }
      finally { button.disabled = false; button.textContent = 'Importar y crear informes'; }
    };
  }

  renderGeneralTab = function () {
    const r = state.activeReport;
    $('#tab-general').innerHTML = `<form class="form-panel" id="general-form"><div class="panel-head"><div><h2>Datos generales</h2><p>Los responsables se toman de la configuración institucional.</p></div><button type="button" class="button secondary small" id="open-fixed-settings">Ver responsables</button></div><div class="form-grid three">${field('name','Nombre del informe',r.name)}${field('period','Periodo',r.period)}<label>Modalidad<select name="modality"><option value="presencial" ${r.modality==='presencial'?'selected':''}>Presencial</option><option value="en_linea" ${r.modality==='en_linea'?'selected':''}>En línea</option></select></label>${field('code','Código',r.code)}${field('version','Versión',r.version)}${field('elaboration_date','Fecha de elaboración',r.elaboration_date,'date')}</div><div class="fixed-responsibles-note">Elaborado, revisado y aprobado se mantienen iguales para todos los informes.</div><div class="form-actions"><button class="button primary">Guardar cambios</button></div></form>`;
    $('#general-form').onsubmit = saveGeneral;
    $('#open-fixed-settings').onclick = () => document.querySelector('[data-fixed-settings]')?.click();
  };

  const reportForm = $('#report-form');
  reportForm?.addEventListener('submit', async e => {
    e.preventDefault(); e.stopImmediatePropagation(); const form = e.currentTarget;
    try { const result = await api('/api/reports', { method:'POST', body:JSON.stringify(Object.fromEntries(new FormData(form).entries())) }); $('#report-dialog').close(); form.reset(); toast('Informe creado.'); await loadReports(); await openReport(result.report_id); } catch (error) { toast(error.message, true); }
  }, true);

  const careerForm = $('#career-form');
  careerForm?.addEventListener('submit', async e => {
    e.preventDefault(); e.stopImmediatePropagation(); const form = e.currentTarget; const id = state.activeReport?.id;
    if (!id) return toast('Primero abra un informe.', true);
    try { await api(`/api/reports/${id}/careers`, { method:'POST', body:JSON.stringify(Object.fromEntries(new FormData(form).entries())) }); $('#career-dialog').close(); form.reset(); toast('Carrera agregada.'); await openReport(id); } catch (error) { toast(error.message, true); }
  }, true);

  addSettings();
  addImporter();
})();
