const state = { reports: [], activeReport: null, aiProviders: [] };
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  const type = response.headers.get('content-type') || '';
  const data = type.includes('application/json') ? await response.json() : null;
  if (!response.ok || (data && data.ok === false)) throw new Error(data?.error || `Error ${response.status}`);
  return data;
}

function toast(message, error = false) {
  const node = $('#toast');
  node.textContent = message;
  node.className = `toast${error ? ' error' : ''}`;
  node.hidden = false;
  clearTimeout(window.__toastTimer);
  window.__toastTimer = setTimeout(() => node.hidden = true, 3500);
}

function fmt(value) {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'number') return value.toFixed(2).replace('.', ',');
  return String(value);
}

function escapeHtml(value = '') {
  return String(value).replace(/[&<>'"]/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
}

function showView(name) {
  $$('.view').forEach(view => view.classList.remove('active'));
  $(`#view-${name}`).classList.add('active');
  $$('.nav-item').forEach(item => item.classList.toggle('active', item.dataset.view === name));
  const titles = {
    dashboard: ['Panel de informes', 'Cree, procese y exporte informes institucionales.'],
    report: ['Informe activo', 'Gestione carreras, resultados, imágenes y secciones.'],
    ai: ['Inteligencias artificiales', 'Configure la redacción automática antes y después de las tablas.'],
  };
  $('#page-title').textContent = titles[name][0];
  $('#page-subtitle').textContent = titles[name][1];
  if (name === 'ai') loadAIProviders();
}

async function loadReports() {
  const data = await api('/api/reports');
  state.reports = data.reports;
  renderDashboard();
}

function renderDashboard() {
  const reports = state.reports;
  const students = reports.reduce((sum, report) => sum + Number(report.student_count || 0), 0);
  const careers = reports.reduce((sum, report) => sum + Number(report.career_count || 0), 0);
  $('#dashboard-metrics').innerHTML = [
    ['Informes', reports.length],
    ['Carreras', careers],
    ['Estudiantes procesados', students],
    ['Base de datos', 'Local'],
  ].map(([label, value]) => `<article class="metric"><span>${label}</span><strong>${value}</strong></article>`).join('');

  const grid = $('#reports-grid');
  if (!reports.length) {
    grid.innerHTML = '<div class="empty-mini">Todavía no existen informes. Cree el primero para comenzar.</div>';
    return;
  }
  grid.innerHTML = reports.map(report => `
    <article class="report-card">
      <span class="badge">${report.modality === 'en_linea' ? 'En línea' : 'Presencial'}</span>
      <h3>${escapeHtml(report.name)}</h3>
      <p>${escapeHtml(report.period)}</p>
      <p>${escapeHtml(report.code || 'Sin código institucional')}</p>
      <div class="card-meta"><span>${report.career_count} carreras</span><span>${report.student_count} estudiantes</span></div>
      <div class="report-card-actions">
        <button class="button primary small" data-open-report="${report.id}">Abrir</button>
        <button class="button danger small" data-delete-report="${report.id}">Eliminar</button>
      </div>
    </article>`).join('');
  $$('[data-open-report]', grid).forEach(button => button.onclick = () => openReport(Number(button.dataset.openReport)));
  $$('[data-delete-report]', grid).forEach(button => button.onclick = () => deleteReport(Number(button.dataset.deleteReport)));
}

async function openReport(id) {
  const data = await api(`/api/reports/${id}`);
  state.activeReport = data.report;
  renderReport();
  showView('report');
}

function renderReport() {
  const report = state.activeReport;
  $('#empty-report').hidden = !!report;
  $('#report-workspace').hidden = !report;
  if (!report) return;
  $('#report-name').textContent = report.name;
  $('#report-period').textContent = report.period;
  $('#report-modality').textContent = report.modality === 'en_linea' ? 'Modalidad en línea' : 'Modalidad presencial';
  $('#export-docx').href = `/api/reports/${report.id}/export/docx`;
  $('#export-pdf').href = `/api/reports/${report.id}/export/pdf`;
  renderGeneralTab();
  renderCareersTab();
  renderSectionsTab();
  renderImagesTab();
}

function renderGeneralTab() {
  const r = state.activeReport;
  $('#tab-general').innerHTML = `
    <form class="form-panel" id="general-form">
      <div class="panel-head"><div><h2>Datos generales</h2><p>Estos datos se usarán en la portada y encabezados.</p></div></div>
      <div class="form-grid three">
        ${field('name','Nombre del informe',r.name)}
        ${field('period','Periodo',r.period)}
        <label>Modalidad<select name="modality"><option value="presencial" ${r.modality==='presencial'?'selected':''}>Presencial</option><option value="en_linea" ${r.modality==='en_linea'?'selected':''}>En línea</option></select></label>
        ${field('code','Código',r.code)}
        ${field('version','Versión',r.version)}
        ${field('elaboration_date','Fecha de elaboración',r.elaboration_date,'date')}
        ${field('prepared_by','Elaborado por',r.prepared_by)}
        ${field('prepared_role','Cargo',r.prepared_role)}
        ${field('reviewed_by','Revisado por',r.reviewed_by)}
        ${field('reviewed_role','Cargo',r.reviewed_role)}
        ${field('approved_by','Aprobado por',r.approved_by)}
        ${field('approved_role','Cargo',r.approved_role)}
      </div>
      <div class="form-actions"><button class="button primary">Guardar cambios</button></div>
    </form>`;
  $('#general-form').onsubmit = saveGeneral;
}

function field(name, label, value = '', type = 'text') {
  return `<label>${label}<input type="${type}" name="${name}" value="${escapeHtml(value || '')}"></label>`;
}

async function saveGeneral(event) {
  event.preventDefault();
  const payload = Object.fromEntries(new FormData(event.currentTarget).entries());
  await api(`/api/reports/${state.activeReport.id}`, { method: 'PUT', body: JSON.stringify(payload) });
  toast('Datos generales guardados.');
  await openReport(state.activeReport.id);
}

function renderCareersTab() {
  const tab = $('#tab-careers');
  const careers = state.activeReport.careers || [];
  tab.innerHTML = `
    <div class="panel">
      <div class="panel-head"><div><h2>Carreras y calificaciones</h2><p>Pegue las notas de Moodle y revise los resultados ordinarios, supletorios y consolidados.</p></div><button class="button primary" id="add-career-btn">Agregar carrera</button></div>
      <div id="career-list" class="career-list">${careers.length ? careers.map(renderCareerCard).join('') : '<div class="empty-mini">Agregue las carreras que corresponden a esta modalidad.</div>'}</div>
    </div>`;
  $('#add-career-btn').onclick = () => $('#career-dialog').showModal();
  careers.forEach(career => bindCareerCard(career));
}

function renderCareerCard(career) {
  return `<article class="career-card" id="career-${career.id}">
    <div class="career-head">
      <div><h3>${escapeHtml(career.name)}</h3><p id="career-state-${career.id}">Cargando resultados...</p></div>
      <div class="career-buttons">
        <button class="button secondary small" data-notes="${career.id}">Pegar notas</button>
        <button class="button secondary small" data-phase="ordinario" data-analysis="${career.id}">Texto ordinario</button>
        <button class="button secondary small" data-phase="supletorio" data-analysis="${career.id}">Texto supletorio</button>
        <button class="button secondary small" data-phase="consolidado" data-analysis="${career.id}">Texto consolidado</button>
        <button class="button danger small" data-delete-career="${career.id}">Eliminar</button>
      </div>
    </div>
    <div class="summary-grid" id="summary-${career.id}"></div>
    <div class="student-table-wrap"><table class="student-table"><thead><tr><th>Estudiante</th><th>Teórico ord.</th><th>Práctico ord.</th><th>Final ord.</th><th>Teórico sup.</th><th>Práctico sup.</th><th>Final</th><th>Estado</th><th>Diferencia Moodle</th></tr></thead><tbody id="students-${career.id}"><tr><td colspan="9">Cargando...</td></tr></tbody></table></div>
  </article>`;
}

function bindCareerCard(career) {
  const root = $(`#career-${career.id}`);
  $('[data-notes]', root).onclick = () => openNotesDialog(career);
  $$('[data-analysis]', root).forEach(button => button.onclick = () => openAnalysisDialog(career, button.dataset.phase));
  $('[data-delete-career]', root).onclick = () => deleteCareer(career.id);
  loadCareerData(career.id);
}

async function loadCareerData(careerId) {
  const [studentsData, summaryData] = await Promise.all([
    api(`/api/careers/${careerId}/students`),
    api(`/api/careers/${careerId}/summary?phase=consolidado`),
  ]);
  const s = summaryData.summary;
  $(`#career-state-${careerId}`).textContent = `${s.total} estudiantes · ${s.approved_pct.toFixed(2)} % de aprobación final`;
  $(`#summary-${careerId}`).innerHTML = [
    ['Total',s.total],['Aprobados',s.approved],['Reprobados',s.failed],['Supletorios',s.supplementary_count],['Promedio',fmt(s.average_final)]
  ].map(([label,value])=>`<div class="summary-item"><span>${label}</span><strong>${value}</strong></div>`).join('');
  const tbody = $(`#students-${careerId}`);
  tbody.innerHTML = studentsData.students.length ? studentsData.students.map(student => `
    <tr><td>${escapeHtml(student.full_name)}</td><td>${fmt(student.ordinary_theory)}</td><td>${fmt(student.ordinary_practical)}</td><td>${fmt(student.ordinary_final)}</td><td>${fmt(student.supplementary_theory)}</td><td>${fmt(student.supplementary_practical)}</td><td>${fmt(student.final_grade)}</td><td class="${student.final_status==='Aprobado'?'status-approved':'status-failed'}">${student.final_status}</td><td>${fmt(student.source_difference)}</td></tr>`).join('') : '<tr><td colspan="9">Todavía no hay calificaciones cargadas.</td></tr>';
}

function renderSectionsTab() {
  const sections = state.activeReport.sections || [];
  $('#tab-sections').innerHTML = `<div class="panel"><div class="panel-head"><div><h2>Secciones institucionales</h2><p>Edite el contenido fijo y variable del informe.</p></div></div><div class="section-list">${sections.map(section => `
    <article class="section-card" data-section-card="${section.id}">
      <div class="section-head"><div><h3>${escapeHtml(section.title)}</h3><p>${escapeHtml(section.section_key)}</p></div><label class="check"><input type="checkbox" name="visible" ${section.visible?'checked':''}> Visible</label></div>
      <input name="title" value="${escapeHtml(section.title)}">
      <textarea name="content">${escapeHtml(section.content)}</textarea>
      <div class="form-actions"><button class="button primary small" data-save-section="${section.id}">Guardar sección</button></div>
    </article>`).join('')}</div></div>`;
  $$('[data-save-section]').forEach(button => button.onclick = async () => {
    const card = button.closest('[data-section-card]');
    const payload = { title: $('[name=title]', card).value, content: $('[name=content]', card).value, visible: $('[name=visible]', card).checked ? 1 : 0 };
    await api(`/api/reports/${state.activeReport.id}/sections/${button.dataset.saveSection}`, {method:'PUT',body:JSON.stringify(payload)});
    toast('Sección guardada.');
  });
}

function renderImagesTab() {
  const images = state.activeReport.images || [];
  $('#tab-images').innerHTML = `<div class="panel"><div class="panel-head"><div><h2>Banco de imágenes</h2><p>Agregue infografías, evidencias, diagramas y fotografías.</p></div><button class="button primary" id="add-image-btn">Agregar imagen</button></div><div class="image-grid">${images.length ? images.map(image => `
    <article class="image-card"><img src="/uploads/${image.filename}" alt="${escapeHtml(image.title || image.original_name)}"><div class="image-card-body"><h4>${escapeHtml(image.title || image.original_name)}</h4><p>${escapeHtml(image.description || 'Sin descripción')}</p><p>${escapeHtml(image.source || 'Sin fuente')}</p><button class="button danger small" data-delete-image="${image.id}">Eliminar</button></div></article>`).join('') : '<div class="empty-mini">Todavía no se han agregado imágenes.</div>'}</div></div>`;
  $('#add-image-btn').onclick = openImageDialog;
  $$('[data-delete-image]').forEach(button => button.onclick = () => deleteImage(Number(button.dataset.deleteImage)));
}

async function loadAIProviders() {
  const data = await api('/api/ai-providers');
  state.aiProviders = data.providers;
  $('#ai-grid').innerHTML = data.providers.map(provider => `
    <article class="ai-card"><div class="career-head"><div><h3>${escapeHtml(provider.name)}</h3><span class="provider-state">${provider.enabled ? 'Habilitada' : 'Deshabilitada'} · Prioridad ${provider.priority}</span></div><span class="badge">${provider.has_api_key ? 'Clave configurada' : 'Sin clave'}</span></div>
      <form data-ai-form="${provider.id}">
        <label>Endpoint<input name="endpoint" value="${escapeHtml(provider.endpoint)}"></label>
        <label>Modelo<input name="model" value="${escapeHtml(provider.model || '')}" placeholder="Configure el modelo disponible"></label>
        <label>Clave API<input type="password" name="api_key" value="${provider.api_key}" autocomplete="new-password"></label>
        <div class="form-grid"><label>Prioridad<input type="number" name="priority" value="${provider.priority}" min="1" max="9"></label><label>Timeout<input type="number" name="timeout" value="${provider.timeout}" min="10" max="180"></label></div>
        <div class="form-grid"><label>Temperatura<input type="number" step="0.1" name="temperature" value="${provider.temperature}" min="0" max="1"></label><label>Máx. tokens<input type="number" name="max_tokens" value="${provider.max_tokens}" min="300" max="8000"></label></div>
        <label class="check"><input type="checkbox" name="enabled" ${provider.enabled?'checked':''}> Habilitar proveedor</label>
        <button class="button primary">Guardar configuración</button>
      </form>
    </article>`).join('');
  $$('[data-ai-form]').forEach(form => form.onsubmit = saveAIProvider);
}

async function saveAIProvider(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const raw = Object.fromEntries(new FormData(form).entries());
  const payload = { ...raw, enabled: $('[name=enabled]', form).checked ? 1 : 0, priority:Number(raw.priority), timeout:Number(raw.timeout), temperature:Number(raw.temperature), max_tokens:Number(raw.max_tokens) };
  await api(`/api/ai-providers/${form.dataset.aiForm}`, {method:'PUT',body:JSON.stringify(payload)});
  toast('Proveedor de IA actualizado.');
  loadAIProviders();
}

function openNotesDialog(career) {
  const form = $('#notes-form');
  form.reset();
  form.career_id.value = career.id;
  form.replace.checked = true;
  $('#notes-title').textContent = `Cargar notas · ${career.name}`;
  $('#notes-dialog').showModal();
}

function openAnalysisDialog(career, phase) {
  const form = $('#analysis-form');
  form.reset();
  form.career_id.value = career.id;
  form.phase.value = phase;
  $('#analysis-title').textContent = `${phase[0].toUpperCase()+phase.slice(1)} · ${career.name}`;
  $('#analysis-dialog').showModal();
  loadExistingAnalysis(career.id, phase);
}

async function loadExistingAnalysis(careerId, phase) {
  const data = await api(`/api/careers/${careerId}/analyses`);
  const item = data.analyses.find(row => row.section === phase);
  if (item) {
    $('#analysis-form').text_before.value = item.text_before || '';
    $('#analysis-form').text_after.value = item.text_after || '';
    $('#analysis-form').status.value = item.status || 'borrador';
  }
}

function openImageDialog() {
  const form = $('#image-form');
  form.reset();
  const select = form.career_id;
  select.innerHTML = '<option value="">Imagen general</option>' + (state.activeReport.careers || []).map(c => `<option value="${c.id}">${escapeHtml(c.name)}</option>`).join('');
  $('#image-dialog').showModal();
}

async function fileToDataURL(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.onerror = reject; reader.readAsDataURL(file);
  });
}

async function deleteReport(id) {
  if (!confirm('¿Eliminar este informe y todos sus datos locales?')) return;
  await api(`/api/reports/${id}`, {method:'DELETE'});
  if (state.activeReport?.id === id) state.activeReport = null;
  toast('Informe eliminado.');
  loadReports();
}

async function deleteCareer(id) {
  if (!confirm('¿Eliminar la carrera y sus calificaciones?')) return;
  await api(`/api/careers/${id}`, {method:'DELETE'});
  toast('Carrera eliminada.');
  await openReport(state.activeReport.id);
}

async function deleteImage(id) {
  if (!confirm('¿Eliminar esta imagen?')) return;
  await api(`/api/images/${id}`, {method:'DELETE'});
  toast('Imagen eliminada.');
  await openReport(state.activeReport.id);
}

$('#report-form').addEventListener('submit', async event => {
  event.preventDefault();
  const payload = Object.fromEntries(new FormData(event.currentTarget).entries());
  try {
    const result = await api('/api/reports', {method:'POST',body:JSON.stringify(payload)});
    $('#report-dialog').close();
    event.currentTarget.reset();
    toast('Informe creado.');
    await loadReports();
    await openReport(result.report_id);
  } catch (error) { toast(error.message, true); }
});

$('#career-form').addEventListener('submit', async event => {
  event.preventDefault();
  const payload = Object.fromEntries(new FormData(event.currentTarget).entries());
  try {
    await api(`/api/reports/${state.activeReport.id}/careers`, {method:'POST',body:JSON.stringify(payload)});
    $('#career-dialog').close(); event.currentTarget.reset(); toast('Carrera agregada.'); await openReport(state.activeReport.id);
  } catch (error) { toast(error.message, true); }
});

$('#notes-form').addEventListener('submit', async event => {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = { text: form.text.value, replace: form.replace.checked };
  try {
    const result = await api(`/api/careers/${form.career_id.value}/parse`, {method:'POST',body:JSON.stringify(payload)});
    $('#notes-dialog').close();
    toast(`${result.inserted} estudiantes procesados.` + (result.warnings.length ? ` ${result.warnings.join(' ')}` : ''));
    await loadCareerData(Number(form.career_id.value));
    await loadReports();
  } catch (error) { toast(error.message, true); }
});

$('#analysis-form').addEventListener('submit', async event => {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = { text_before: form.text_before.value, text_after: form.text_after.value, status: form.status.value };
  try {
    await api(`/api/careers/${form.career_id.value}/analyses/${form.phase.value}`, {method:'PUT',body:JSON.stringify(payload)});
    $('#analysis-dialog').close(); toast('Texto guardado.');
  } catch (error) { toast(error.message, true); }
});

$('#generate-ai-btn').onclick = async () => {
  const form = $('#analysis-form');
  $('#ai-progress').textContent = 'Analizando datos...';
  $('#generate-ai-btn').disabled = true;
  try {
    const result = await api(`/api/careers/${form.career_id.value}/analysis`, {method:'POST',body:JSON.stringify({phase:form.phase.value,mode:form.mode.value})});
    form.text_before.value = result.analysis.texto_antes;
    form.text_after.value = result.analysis.texto_despues;
    $('#ai-progress').textContent = `Generado con ${result.chain.join(' → ')}`;
    toast('La IA generó el análisis. Revíselo antes de aprobarlo.');
  } catch (error) { $('#ai-progress').textContent = ''; toast(error.message, true); }
  finally { $('#generate-ai-btn').disabled = false; }
};

$('#image-form').addEventListener('submit', async event => {
  event.preventDefault();
  const form = event.currentTarget;
  const file = form.file.files[0];
  try {
    const dataURL = await fileToDataURL(file);
    const payload = { data_url:dataURL, original_name:file.name, title:form.title.value, description:form.description.value, source:form.source.value, career_id:form.career_id.value ? Number(form.career_id.value) : null, section:form.section.value };
    await api(`/api/reports/${state.activeReport.id}/images`, {method:'POST',body:JSON.stringify(payload)});
    $('#image-dialog').close(); toast('Imagen agregada.'); await openReport(state.activeReport.id);
  } catch (error) { toast(error.message, true); }
});

$$('.nav-item').forEach(item => item.onclick = () => showView(item.dataset.view));
$('#new-report-btn').onclick = () => $('#report-dialog').showModal();
$('#refresh-btn').onclick = async () => { await loadReports(); if (state.activeReport) await openReport(state.activeReport.id); toast('Información actualizada.'); };
$('#report-tabs').onclick = event => {
  const button = event.target.closest('.tab'); if (!button) return;
  $$('.tab').forEach(tab => tab.classList.remove('active')); button.classList.add('active');
  $$('.tab-content').forEach(content => content.classList.remove('active')); $(`#tab-${button.dataset.tab}`).classList.add('active');
};

(async function init() {
  try { await api('/api/health'); await loadReports(); }
  catch (error) { toast(`No se pudo iniciar Informtit: ${error.message}`, true); }
})();
