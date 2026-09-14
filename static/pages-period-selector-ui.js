(() => {
  'use strict';

  if (!/(^|\.)github\.io$/i.test(location.hostname)) return;
  const reportForm = document.getElementById('report-form');
  if (!reportForm) return;

  const ACTIVE_KEY = 'informtit.activePeriod.v2';
  const MONTHS = ['Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'];
  const clean = value => String(value ?? '').replace(/\u00a0/g, ' ').trim().replace(/\s+/g, ' ');
  const fold = value => clean(value).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toUpperCase();
  const pad2 = value => String(Number(value || 0)).padStart(2, '0');
  const typeOf = value => clean(value).toLowerCase() === 'pvc' ? 'pvc' : 'normal';
  let periods = [];
  let selectedPeriod = null;
  let pendingReportType = '';
  let loadingPeriods = null;
  let switchingPeriod = false;

  function provider() {
    const api = window.InformtitSheets;
    if (!api || api.provider !== 'NEON') throw new Error('Neon PostgreSQL no está disponible.');
    return api;
  }

  function canonicalId(value) {
    const raw = clean(value);
    const match = raw.match(/^(\d{4})-(\d{2})_+(\d{4})-(\d{2})$/);
    return match ? `${match[1]}-${match[2]}_${match[3]}-${match[4]}` : raw;
  }
  function idFromParts(sm, sy, em, ey) { return `${sy}-${pad2(sm)}_${ey}-${pad2(em)}`; }
  function labelFromParts(sm, sy, em, ey) { return `${MONTHS[sm - 1]} ${sy} - ${MONTHS[em - 1]} ${ey}`; }
  function parseId(value) {
    const match = canonicalId(value).match(/^(\d{4})-(\d{2})_(\d{4})-(\d{2})$/);
    return match ? { sm:Number(match[2]), sy:Number(match[1]), em:Number(match[4]), ey:Number(match[3]) } : null;
  }
  function parseLabel(value) {
    const match = clean(value).match(/^([A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+)\s+(\d{4})\s*-\s*([A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+)\s+(\d{4})$/);
    if (!match) return null;
    const sm = MONTHS.findIndex(month => fold(month) === fold(match[1])) + 1;
    const em = MONTHS.findIndex(month => fold(month) === fold(match[3])) + 1;
    return sm && em ? { sm, sy:Number(match[2]), em, ey:Number(match[4]) } : null;
  }
  function normalizePeriod(raw = {}, source = 'neon') {
    const sourceId = clean(raw.periodoId || raw.firebase_period_id || raw.period_id || raw.id);
    const name = clean(raw.nombre || raw.name || raw.label || raw.period);
    const parts = parseId(sourceId) || parseLabel(name);
    const id = canonicalId(sourceId) || (parts ? idFromParts(parts.sm, parts.sy, parts.em, parts.ey) : '');
    const label = name || (parts ? labelFromParts(parts.sm, parts.sy, parts.em, parts.ey) : id);
    if (!id && !label) return null;
    return { id:id || fold(label), sourceId:sourceId || id, name:label, source, ...(parts || {}) };
  }
  function keyOf(period) { return canonicalId(period?.id || period?.sourceId) || fold(period?.name); }
  function periodFromReport(report) {
    return normalizePeriod({ id:report?.firebase_period_id || report?.periodoId || report?.period_id, period:report?.period }, 'neon');
  }
  function reportInPeriod(report, period) {
    const candidate = periodFromReport(report);
    return Boolean(candidate && period && (keyOf(candidate) === keyOf(period) || fold(candidate.name) === fold(period.name)));
  }
  function activePeriod() { return selectedPeriod; }
  function setActivePeriod(period) {
    const normalized = normalizePeriod(period, 'neon');
    if (!normalized) return null;
    selectedPeriod = normalized;
    try { localStorage.setItem(ACTIVE_KEY, JSON.stringify(normalized)); } catch (_) {}
    state.activePeriod = normalized;
    return normalized;
  }
  function clearStoredActivePeriod() {
    selectedPeriod = null;
    try { localStorage.removeItem(ACTIVE_KEY); } catch (_) {}
    if (typeof state !== 'undefined') {
      state.activePeriod = null;
      state.activeReport = null;
    }
  }

  function mergePeriods(rows = []) {
    const map = new Map();
    rows.filter(Boolean).forEach(raw => {
      const period = normalizePeriod(raw, 'neon');
      if (period) map.set(keyOf(period), period);
    });
    return [...map.values()].sort((a,b) => ((b.sy||0)*100+(b.sm||0))-((a.sy||0)*100+(a.sm||0)) || a.name.localeCompare(b.name,'es'));
  }

  async function loadPeriods(force = false) {
    if (!force && periods.length) return periods;
    if (loadingPeriods) return loadingPeriods;
    loadingPeriods = (async () => {
      const data = await provider().periodos();
      if (!Array.isArray(data?.periodos)) throw new Error('Neon no devolvió el catálogo de períodos.');
      periods = mergePeriods(data.periodos);
      return periods;
    })().finally(() => { loadingPeriods = null; });
    return loadingPeriods;
  }

  function academicDefaults() {
    const now = new Date(), month = now.getMonth()+1, year = now.getFullYear();
    if (month >= 4 && month <= 9) return { sm:4, sy:year, em:9, ey:year };
    if (month >= 10) return { sm:10, sy:year, em:3, ey:year+1 };
    return { sm:10, sy:year-1, em:3, ey:year };
  }

  function ensureBar() {
    let bar = document.getElementById('global-period-context');
    if (bar) return bar;
    const titleBlock = document.querySelector('.topbar')?.firstElementChild;
    if (!titleBlock) return null;
    bar = document.createElement('div');
    bar.id = 'global-period-context';
    bar.className = 'global-period-context';
    bar.innerHTML = `<label><span>Período activo</span><select id="global-period-select" aria-label="Seleccionar período"><option value="">Seleccionar período</option></select></label><button type="button" class="button secondary small" id="new-period-btn" aria-label="Crear período">+ Nuevo período</button>`;
    titleBlock.prepend(bar);
    bar.querySelector('#new-period-btn').onclick = () => openPeriodDialog(true);
    bar.querySelector('#global-period-select').onchange = async event => {
      const id = canonicalId(event.currentTarget.value);
      if (!id) { clearActiveContext(); return; }
      const period = periods.find(item => keyOf(item) === id);
      if (period) await activatePeriod(period);
    };
    return bar;
  }

  function syncBar(period = activePeriod()) {
    const select = ensureBar()?.querySelector('#global-period-select');
    if (!select) return;
    const value = period ? keyOf(period) : '';
    if (period && ![...select.options].some(option => option.value === value)) {
      select.insertAdjacentHTML('beforeend', `<option value="${escapeHtml(value)}">${escapeHtml(period.name)}</option>`);
    }
    select.value = value;
  }

  function showPeriodLoadError(message) {
    const select = ensureBar()?.querySelector('#global-period-select');
    if (select) select.innerHTML = '<option value="">No se pudo cargar el catálogo</option>';
    const empty = document.getElementById('empty-report');
    if (empty) {
      empty.hidden = false;
      const h2 = empty.querySelector('h2');
      const p = empty.querySelector('p');
      if (h2) h2.textContent = 'No se pudo cargar los períodos';
      if (p) p.textContent = `${clean(message)} · Reintente con Actualizar.`;
    }
  }

  async function refreshPeriodOptions(force = false) {
    const select = ensureBar()?.querySelector('#global-period-select');
    if (!select) return;
    try {
      const rows = await loadPeriods(force);
      select.innerHTML = '<option value="">Seleccionar período</option>' + rows.map(period => `<option value="${escapeHtml(keyOf(period))}">${escapeHtml(period.name)}</option>`).join('');
      syncBar(activePeriod());
      updateCreateButtons();
    } catch (error) {
      showPeriodLoadError(error?.message || error);
      updateCreateButtons();
    }
  }

  function ensurePeriodDialog() {
    let dialog = document.getElementById('period-dialog');
    if (dialog) return dialog;
    dialog = document.createElement('dialog');
    dialog.id = 'period-dialog';
    dialog.innerHTML = `<form id="period-form" class="dialog-form">
      <div class="dialog-head"><div><h2>Crear período</h2><p>Primero se guarda en Neon; después queda disponible para trabajar.</p></div><button type="button" class="icon-button" data-close-period>×</button></div>
      <div class="period-create-grid">
        <label>Mes de inicio<select name="sm"></select></label>
        <label>Año de inicio<div class="period-stepper"><button type="button" data-step="sy" data-delta="-1">−</button><input type="number" name="sy" min="2000" max="2100"><button type="button" data-step="sy" data-delta="1">+</button></div></label>
        <label>Mes de fin<select name="em"></select></label>
        <label>Año de fin<div class="period-stepper"><button type="button" data-step="ey" data-delta="-1">−</button><input type="number" name="ey" min="2000" max="2100"><button type="button" data-step="ey" data-delta="1">+</button></div></label>
      </div>
      <div class="report-derived-preview"><span>Período generado</span><strong id="period-preview">—</strong></div>
      <div class="report-derived-preview"><span>periodId</span><strong id="period-id-preview">—</strong></div>
      <p id="period-error" class="period-error" hidden></p>
      <div class="dialog-actions"><button type="button" class="button secondary" data-close-period>Cancelar</button><button type="submit" class="button primary" id="period-submit">Crear período</button></div>
    </form>`;
    document.body.appendChild(dialog);
    const pf = dialog.querySelector('#period-form');
    const options = MONTHS.map((month,i) => `<option value="${i+1}">${month}</option>`).join('');
    pf.elements.sm.innerHTML = options; pf.elements.em.innerHTML = options;
    dialog.querySelectorAll('[data-close-period]').forEach(button => button.onclick = () => { pendingReportType=''; dialog.close(); });
    dialog.querySelectorAll('[data-step]').forEach(button => button.onclick = () => {
      const input = pf.elements[button.dataset.step];
      input.value = String(Math.max(2000, Math.min(2100, Number(input.value || new Date().getFullYear()) + Number(button.dataset.delta))));
      updatePeriodPreview();
    });
    ['sm','sy','em','ey'].forEach(name => { pf.elements[name].oninput = updatePeriodPreview; pf.elements[name].onchange = updatePeriodPreview; });
    pf.onsubmit = event => { event.preventDefault(); void createPeriod(); };
    return dialog;
  }

  function updatePeriodPreview() {
    const pf = ensurePeriodDialog().querySelector('#period-form');
    const sm=Number(pf.elements.sm.value), sy=Number(pf.elements.sy.value), em=Number(pf.elements.em.value), ey=Number(pf.elements.ey.value);
    const valid = sm>=1&&sm<=12&&em>=1&&em<=12&&sy>=2000&&ey>=2000;
    const chronological = valid && ey*12+em >= sy*12+sm;
    const preview = document.getElementById('period-preview'), idPreview = document.getElementById('period-id-preview'), error = document.getElementById('period-error'), submit = document.getElementById('period-submit');
    preview.textContent = chronological ? labelFromParts(sm,sy,em,ey) : (valid ? 'El final no puede ser anterior al inicio.' : '—');
    idPreview.textContent = chronological ? idFromParts(sm,sy,em,ey) : '—';
    submit.disabled = !chronological;
    error.hidden = chronological || !valid;
    error.textContent = chronological ? '' : 'Revise el mes y año final del período.';
  }

  function openPeriodDialog(reset = false) {
    const dialog = ensurePeriodDialog(), pf = dialog.querySelector('#period-form'), defaults = academicDefaults();
    if (reset || !pf.elements.sy.value) {
      pf.elements.sm.value=defaults.sm; pf.elements.sy.value=defaults.sy; pf.elements.em.value=defaults.em; pf.elements.ey.value=defaults.ey;
    }
    const error = document.getElementById('period-error');
    if (error) { error.hidden = true; error.textContent = ''; }
    updatePeriodPreview();
    if (!dialog.open) dialog.showModal();
  }

  async function createPeriod() {
    const dialog = ensurePeriodDialog(), pf = dialog.querySelector('#period-form');
    const sm=Number(pf.elements.sm.value), sy=Number(pf.elements.sy.value), em=Number(pf.elements.em.value), ey=Number(pf.elements.ey.value);
    if (!(sm&&em&&sy>=2000&&ey>=2000&&ey*12+em>=sy*12+sm)) return;
    const id=idFromParts(sm,sy,em,ey), name=labelFromParts(sm,sy,em,ey);
    const submit=document.getElementById('period-submit'), error=document.getElementById('period-error');
    submit.disabled=true; submit.textContent='Guardando…';
    if(error){error.hidden=true;error.textContent='';}
    try {
      const rows=await loadPeriods(true);
      let period=rows.find(item => keyOf(item)===id || fold(item.name)===fold(name));
      if (!period) {
        const result=await provider().guardarPeriodo({periodoId:id,id,nombre:name,label:name,mesInicio:sm,anioInicio:sy,mesFin:em,anioFin:ey,estado:'ACTIVE',activo:true});
        period=normalizePeriod(result?.period || {id,nombre:name},'neon');
        periods=mergePeriods([...periods,period]);
      }
      dialog.close();
      await activatePeriod(period);
      if (typeof toast === 'function') toast(rows.some(item=>keyOf(item)===id) ? 'El período ya existía y fue seleccionado.' : `Período ${name} guardado en Neon.`);
      const type=pendingReportType; pendingReportType='';
      if(type) setTimeout(()=>openReportDialog(type),0);
    } catch (err) {
      if(error){error.hidden=false;error.textContent=`No se pudo crear el período: ${clean(err?.message||err)}`;}
    } finally {
      if(submit?.isConnected){submit.disabled=false;submit.textContent='Crear período';updatePeriodPreview();}
    }
  }

  function hasUnsavedChanges() {
    const root=document.getElementById('report-workspace');
    if (!root || root.hidden) return false;
    return [...root.querySelectorAll('input,textarea,select')].some(control => {
      if (control.disabled || control.readOnly || control.type==='hidden') return false;
      if (control.type==='checkbox'||control.type==='radio') return control.checked!==control.defaultChecked;
      if (control.tagName==='SELECT') { const i=[...control.options].findIndex(option=>option.defaultSelected); return i>=0 && control.selectedIndex!==i; }
      return control.value!==control.defaultValue;
    });
  }

  function clearActiveContext() {
    clearStoredActivePeriod();
    state.reports=[];
    document.getElementById('report-workspace')?.setAttribute('hidden','');
    const empty=document.getElementById('empty-report');
    if(empty){empty.hidden=false;const h2=empty.querySelector('h2'),p=empty.querySelector('p');if(h2)h2.textContent='Selecciona un período para continuar';if(p)p.textContent='No se cargarán documentos ni datos hasta que selecciones un período.';}
    syncBar(null); updateCreateButtons(); renderDashboard();
    document.dispatchEvent(new CustomEvent('informtit:period-cleared'));
  }

  async function activatePeriod(period) {
    if (switchingPeriod) return;
    const current=activePeriod();
    if (current && keyOf(current)!==keyOf(period) && hasUnsavedChanges() && !confirm('Hay cambios sin guardar. Acepte para descartarlos y cambiar de período; Cancelar para permanecer.')) { syncBar(current); return; }
    switchingPeriod=true;
    const active=setActivePeriod(period);
    state.activeReport=null;
    state.reports=[];
    document.getElementById('report-workspace')?.setAttribute('hidden','');
    const empty=document.getElementById('empty-report');
    if(empty){empty.hidden=false;const h2=empty.querySelector('h2'),p=empty.querySelector('p');if(h2)h2.textContent='Cargando…';if(p)p.textContent=`Recuperando únicamente ${active.name} desde Neon.`;}
    syncBar(active); updateCreateButtons();
    document.dispatchEvent(new CustomEvent('informtit:period-changed',{detail:active}));
    try {
      await loadReports();
      renderDashboard();
    } catch (error) {
      state.reports=[];
      if(empty){empty.hidden=false;const h2=empty.querySelector('h2'),p=empty.querySelector('p');if(h2)h2.textContent='No se pudo cargar el período';if(p)p.textContent=`${clean(error?.message||error)} · Reintentar con Actualizar.`;}
      if(typeof toast==='function')toast(`No se pudo cargar el período: ${clean(error?.message||error)}`,true);
    } finally { switchingPeriod=false; }
  }

  function updateCreateButtons() {
    const disabled=!activePeriod();
    ['new-report-btn','new-pvc-report-btn'].forEach(id => { const button=document.getElementById(id); if(button){button.disabled=disabled; button.title=disabled?'Seleccione o cree un período primero.':'';} });
  }
  function hiddenInput(name) {
    let input=reportForm.elements.namedItem(name);
    if (!input) { input=document.createElement('input'); input.type='hidden'; input.name=name; reportForm.appendChild(input); }
    return input;
  }
  function applyActivePeriodToReportForm(type=typeOf(reportForm.elements.report_type?.value)) {
    const active=activePeriod(), parts=active && (parseId(active.id)||parseLabel(active.name));
    if (!active || !parts) return false;
    reportForm.elements.period_start_month.value=parts.sm; reportForm.elements.period_start_year.value=parts.sy;
    reportForm.elements.period_end_month.value=parts.em; reportForm.elements.period_end_year.value=parts.ey;
    reportForm.elements.code_month.value=`${parts.ey}-${pad2(parts.em)}`;
    const codeP=`UTET-INF-01-PRO-95-${parts.ey}-${pad2(parts.em)}`, codeO=`UTET-INF-02-PRO-95-${parts.ey}-${pad2(parts.em)}`;
    const name=`Informe Final del Proceso de Titulación - ${active.name}`;
    reportForm.elements.period.value=active.name; reportForm.elements.name.value=name; reportForm.elements.code.value=codeP;
    hiddenInput('firebase_period_id').value=active.id; hiddenInput('periodoId').value=active.id; hiddenInput('period_context_id').value=active.id;
    hiddenInput('code_presencial').value=codeP; hiddenInput('code_online').value=type==='pvc'?'':codeO;
    document.getElementById('report-period-preview').textContent=active.name;
    document.getElementById('report-name-preview').textContent=name;
    document.getElementById('report-code-preview').innerHTML=type==='pvc'?codeP:`Presencial: ${codeP}<br>Online: ${codeO}`;
    const dialog=document.getElementById('report-dialog'); dialog?.classList.add('period-context-locked');
    let summary=document.getElementById('report-active-period-summary');
    if(!summary){summary=document.createElement('div');summary.id='report-active-period-summary';summary.className='report-active-period-summary';reportForm.querySelector('.form-grid')?.insertAdjacentElement('afterend',summary);}
    summary.innerHTML=`<span>Período activo</span><strong>${escapeHtml(active.name)}</strong><small>${escapeHtml(active.id)}</small>`;
    const subtitle=dialog?.querySelector('.dialog-head p'); if(subtitle) subtitle.textContent='El informe usa el período activo. Para cambiarlo, use el selector global.';
    return true;
  }

  function renderDocumentCatalog(active, reports) {
    const dashboard=document.getElementById('view-dashboard'); if(!dashboard) return;
    let catalog=document.getElementById('period-document-catalog');
    if(!catalog){catalog=document.createElement('section');catalog.id='period-document-catalog';catalog.className='panel period-document-catalog';const reportsPanel=document.getElementById('reports-grid')?.closest('.panel');reportsPanel?dashboard.insertBefore(catalog,reportsPanel):dashboard.appendChild(catalog);}
    if(!active){catalog.innerHTML='<div class="panel-head"><div><h2>Documentos</h2><p>Selecciona un período para continuar.</p></div></div><div class="empty-mini">La aplicación no carga contenido documental antes de elegir el período.</div>';return;}
    const regular=reports.find(report=>typeOf(report.report_type)==='normal'), pvc=reports.find(report=>typeOf(report.report_type)==='pvc');
    const card=(title,desc,report,type)=>`<article class="period-document-card ${report?'ready':'pending'}"><div><span>${report?'Creado':'Pendiente'}</span><h3>${title}</h3><p>${desc}</p></div><button class="button ${report?'primary':'secondary'}" ${report?`data-open-period-document="${report.id}"`:`data-create-period-document="${type}"`}>${report?'Abrir documento':'Crear documento'}</button></article>`;
    catalog.innerHTML=`<div class="panel-head"><div><h2>Documentos del período</h2><p>${escapeHtml(active.name)}</p></div></div><div class="period-document-grid">${card('Informe Final de Titulación','Salidas Presencial + Online.',regular,'normal')}${card('PVC · Artículo Académico','Documento independiente para Artículo Académico.',pvc,'pvc')}</div>`;
    catalog.querySelectorAll('[data-open-period-document]').forEach(button=>button.onclick=()=>openReport(Number(button.dataset.openPeriodDocument)));
    catalog.querySelectorAll('[data-create-period-document]').forEach(button=>button.onclick=()=>openReportDialog(button.dataset.createPeriodDocument));
  }

  const baseRenderDashboard=renderDashboard;
  renderDashboard=function periodScopedDashboard(...args){
    const all=state.reports, active=activePeriod(), visible=active?all.filter(report=>reportInPeriod(report,active)):[];
    state.reports=visible; let result; try{result=baseRenderDashboard.apply(this,args);}finally{state.reports=all;}
    const grid=document.getElementById('reports-grid');
    if(grid&&!active)grid.innerHTML='<div class="empty-mini">Selecciona un período para continuar.</div>';
    else if(grid&&active&&!visible.length)grid.innerHTML='<div class="empty-mini">Todavía no hay documentos creados para este período.</div>';
    renderDocumentCatalog(active,visible); updateCreateButtons();
    if(document.getElementById('view-dashboard')?.classList.contains('active')){document.getElementById('page-title').textContent=active?'Documentos del período':'Informtit';document.getElementById('page-subtitle').textContent=active?`${active.name} · seleccione un documento para continuar.`:'Selecciona un período para continuar.';}
    return result;
  };

  const baseLoadReports=loadReports;
  loadReports=async function periodAwareLoadReports(...args){const result=await baseLoadReports.apply(this,args);renderDashboard();return result;};
  const baseShowView=showView;
  showView=function periodAwareShowView(name,...args){const result=baseShowView.call(this,name,...args);if(name==='dashboard')renderDashboard();return result;};
  const baseOpenReport=openReport;
  openReport=async function periodAwareOpenReport(id,...args){const result=await baseOpenReport.call(this,id,...args);const period=periodFromReport(state.activeReport);if(period&&activePeriod()){const known=periods.find(item=>keyOf(item)===keyOf(period)||fold(item.name)===fold(period.name));if(known)setActivePeriod(known);syncBar(activePeriod());}return result;};
  const baseOpenReportDialog=openReportDialog;
  openReportDialog=function periodAwareOpenReportDialog(type='normal'){
    const active=activePeriod();
    if(!active){pendingReportType=typeOf(type);openPeriodDialog(true);if(typeof toast==='function')toast('Primero seleccione o cree el período activo.');return;}
    baseOpenReportDialog(typeOf(type));applyActivePeriodToReportForm(typeOf(type));setTimeout(()=>applyActivePeriodToReportForm(typeOf(type)),0);
  };
  reportForm.elements.report_type?.addEventListener('change',()=>setTimeout(()=>applyActivePeriodToReportForm(typeOf(reportForm.elements.report_type.value)),0));

  function injectStyles(){
    if(document.getElementById('global-period-context-style'))return;
    const style=document.createElement('style');style.id='global-period-context-style';style.textContent=`
      .global-period-context{display:flex;align-items:end;gap:8px;flex-wrap:wrap;margin-bottom:12px;padding:10px 12px;border:1px solid #dce5ee;border-radius:12px;background:#fff}.global-period-context label{min-width:min(360px,100%);gap:4px}.global-period-context label span{font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:.05em;color:#65758a}.global-period-context select{height:36px;padding:7px 9px;font-weight:700;color:#18364f}
      #period-dialog{width:min(760px,calc(100vw - 28px));max-width:760px;border:0;border-radius:16px;padding:0}.period-create-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.period-stepper{display:grid;grid-template-columns:34px minmax(0,1fr) 34px;gap:5px}.period-stepper button{height:38px;border:1px solid #cbd8e4;border-radius:8px;background:#f7f9fc;color:#102b46;font-weight:800;font-size:17px}.period-error{margin:0;padding:10px 12px;border-radius:9px;background:#fff0f0;color:#9a2d2d;font-weight:700}
      #report-dialog.report-dialog-compact.period-context-locked .report-period-builder,#report-dialog.period-context-locked .report-period-builder{display:none!important}.report-active-period-summary{margin:14px 20px 0;padding:11px 12px;border:1px solid #dce5ee;border-radius:11px;background:#f7fafc;display:grid;gap:3px}.report-active-period-summary span{font-size:10px;text-transform:uppercase;color:#64748b;font-weight:800}.report-active-period-summary strong{color:#18364f}.report-active-period-summary small{color:#64748b}
      .period-document-catalog{margin-bottom:20px}.period-document-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.period-document-card{display:flex;justify-content:space-between;gap:16px;align-items:center;padding:16px;border:1px solid #dfe7ee;border-radius:13px;background:#fff}.period-document-card.ready{border-color:#bee7ca}.period-document-card.pending{border-style:dashed}.period-document-card span{font-size:10px;font-weight:800;text-transform:uppercase;color:#64748b}.period-document-card.ready span{color:#237b4b}.period-document-card h3{margin:5px 0 4px;font-size:16px}.period-document-card p{margin:0;color:#64748b;font-size:12px}
      @media(max-width:760px){.period-create-grid,.period-document-grid{grid-template-columns:1fr 1fr}.period-document-card{align-items:flex-start;flex-direction:column}.period-document-card .button{width:100%}}@media(max-width:520px){.period-create-grid,.period-document-grid{grid-template-columns:1fr}.global-period-context>.button{width:100%}.report-active-period-summary{margin-left:14px;margin-right:14px}}
    `;document.head.appendChild(style);
  }

  // SVD21_EMPTY_START: nunca restaurar automáticamente el período anterior.
  clearStoredActivePeriod();
  injectStyles(); ensureBar(); ensurePeriodDialog(); syncBar(null); updateCreateButtons(); renderDashboard(); void refreshPeriodOptions(true);
  window.InformtitPeriodContext=Object.freeze({activePeriod,activatePeriod,clearActiveContext,refreshPeriodOptions,version:'5.0.0',standard:'SVD_2_1'});
})();