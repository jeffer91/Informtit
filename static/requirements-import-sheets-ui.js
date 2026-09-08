(() => {
  'use strict';

  if (!/(^|\.)github\.io$/i.test(location.hostname) || !window.InformtitSheets) return;
  const XLSX_SRC = 'https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js';
  const PASS = new Set(['CUMPLE','SI','SÍ','APROBADO','OK','TRUE','1']);
  const REQS = [
    ['academico','Académico'],['documentacion','Documentación'],['financiero','Financiero'],['titulacion','Titulación'],
    ['practicas','Prácticas/Vinculación'],['vinculacion','Vinculación'],['seguimientoGraduados','Seguimiento a Graduados'],
    ['ingles','Inglés'],['actualizacionDatos','Actualización de Datos'],
  ];
  const local = { rows: [], file: null, existingIds: new Set(), saving: false };
  const $ = (s,r=document) => r.querySelector(s);
  const $$ = (s,r=document) => [...r.querySelectorAll(s)];
  const clean = v => String(v ?? '').replace(/\u00a0/g,' ').trim().replace(/\s+/g,' ');
  const fold = v => clean(v).normalize('NFD').replace(/[\u0300-\u036f]/g,'').toUpperCase();
  const esc = v => clean(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const id = v => clean(v).replace(/\D/g,'');
  const isPass = v => PASS.has(fold(v));
  const isPvc = () => clean(window.state?.activeReport?.report_type || window.state?.activeReport?.project_summary?.report_type).toLowerCase() === 'pvc';
  const canonicalCareer = value => window.InformtitPagesData?.canonicalCareer ? window.InformtitPagesData.canonicalCareer(value) : clean(value).toUpperCase();
  const modality = (career, code) => window.InformtitPagesData?.inferModality ? window.InformtitPagesData.inferModality(career, code) : (/ONLINE|EN LINEA|VIRTUAL/i.test(fold(career)) || /-L-/i.test(code) ? 'en_linea':'presencial');

  function first(row, aliases) {
    const index = new Map(Object.entries(row || {}).map(([key,value]) => [fold(key).replace(/[^A-Z0-9]/g,''), value]));
    for (const alias of aliases) {
      const value = index.get(fold(alias).replace(/[^A-Z0-9]/g,''));
      if (value !== undefined && clean(value) !== '') return value;
    }
    return '';
  }

  function parseRows(rows) {
    const map = new Map();
    rows.forEach(raw => {
      const cedula = id(first(raw,['numeroIdentificacion','cedula','identificacion','numero_identificacion']));
      if (!cedula) return;
      const careerRaw = clean(first(raw,['NombreCarrera','carrera','nombre_carrera']));
      const code = clean(first(raw,['CodigoCarrera','codigoCarrera','codigo_carrera']));
      const row = {
        cedula,
        nombre: clean(first(raw,['Nombres','nombre','nombre_estudiante'])),
        codigoCarrera: code,
        carreraRaw: careerRaw,
        carrera: canonicalCareer(careerRaw),
        modalidad: modality(careerRaw, code),
        jornada: clean(first(raw,['HorarioComplexivo','horario','jornada'])),
        correoPersonal: clean(first(raw,['CorreoPersonal','correoPersonal'])).toLowerCase(),
        correoInstitucional: clean(first(raw,['CorreoInstitucional','correoInstitucional','correo'])).toLowerCase(),
        celular: clean(first(raw,['Celular','celular','telefono'])),
        sede: clean(first(raw,['Sede','sede'])),
        academico: clean(first(raw,['Academico','académico'])),
        documentacion: clean(first(raw,['Documentacion','documentación'])),
        financiero: clean(first(raw,['Financiero'])),
        titulacion: clean(first(raw,['Titulacion','titulación'])),
        practicas: clean(first(raw,['PrácticasVinculacion','PracticasVinculacion','Prácticas/Vinculación'])),
        vinculacion: clean(first(raw,['Vinculacion','vinculación'])),
        seguimientoGraduados: clean(first(raw,['SeguimientoGraduados','Seguimiento a Graduados'])),
        ingles: clean(first(raw,['Ingles','Inglés'])),
        actualizacionDatos: clean(first(raw,['ActualizaciónDatos','ActualizacionDatos','Actualización de Datos'])),
        aprobacionTitulacion: clean(first(raw,['AprobacionTitulacion','AprobaciónTitulacion'])),
        aprobacionComplexivo: clean(first(raw,['AprobacionComplexivoProyecto','AprobacionComplexivo'])),
      };
      row.pending = REQS.filter(([key]) => !isPass(row[key])).map(([,label]) => label);
      row.habilitado = row.pending.length === 0;
      map.set(cedula,row);
    });
    return [...map.values()];
  }

  async function loadXlsx() {
    if (window.XLSX) return window.XLSX;
    await new Promise((resolve,reject) => {
      const script=document.createElement('script'); script.src=XLSX_SRC; script.onload=resolve;
      script.onerror=()=>reject(new Error('No se pudo cargar el lector de Excel.')); document.head.appendChild(script);
    });
    return window.XLSX;
  }

  function htmlRows(text) {
    if (!/<table[\s>]/i.test(text)) return [];
    const doc = new DOMParser().parseFromString(text,'text/html');
    const matrix=[...doc.querySelectorAll('table tr')].map(tr=>[...tr.querySelectorAll('th,td')].map(td=>clean(td.textContent)));
    if (!matrix.length) return [];
    let headerIndex = matrix.findIndex(row => row.some(cell => /numeroIdentificacion|Nombres|NombreCarrera/i.test(cell)));
    if (headerIndex < 0) headerIndex = 0;
    const headers=matrix[headerIndex];
    return matrix.slice(headerIndex+1).filter(row=>row.some(Boolean)).map(row=>Object.fromEntries(headers.map((h,i)=>[h || `col${i+1}`,row[i] ?? ''])));
  }

  async function readFile(file) {
    const lower=file.name.toLowerCase();
    if (/\.(html?|xls)$/.test(lower)) {
      const text=await file.text();
      const rows=htmlRows(text);
      if (rows.length) return rows;
    }
    const XLSX=await loadXlsx();
    const workbook=XLSX.read(await file.arrayBuffer(),{type:'array',cellDates:false});
    const sheet=workbook.Sheets[workbook.SheetNames[0]];
    return XLSX.utils.sheet_to_json(sheet,{defval:'',raw:false});
  }

  function ensureStyles() {
    if ($('#req-sheets-style')) return;
    const style=document.createElement('style'); style.id='req-sheets-style';
    style.textContent=`
      .reqs-shell{display:grid;gap:14px}.reqs-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.reqs-head h2{margin:0 0 4px}.reqs-muted{font-size:12px;color:#64748b}.reqs-kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));border:1px solid #dce5ed;border-radius:12px;overflow:hidden;background:#fff}.reqs-kpi{padding:12px;border-right:1px solid #e7edf3}.reqs-kpi:last-child{border-right:0}.reqs-kpi span{display:block;color:#64748b;font-size:10px}.reqs-kpi strong{font-size:19px}.reqs-toolbar{display:flex;gap:8px;align-items:end;flex-wrap:wrap}.reqs-toolbar input{min-width:260px;padding:8px 10px;border:1px solid #cbd8e4;border-radius:8px}.reqs-table-wrap{max-height:580px;overflow:auto;border:1px solid #dce5ed;border-radius:12px}.reqs-table{width:100%;border-collapse:collapse;font-size:11px}.reqs-table th{position:sticky;top:0;background:#f7f9fc;padding:8px;text-align:left;border-bottom:1px solid #dce5ed}.reqs-table td{padding:8px;border-bottom:1px solid #edf2f6}.req-pill{display:inline-flex;padding:3px 7px;border-radius:999px;background:#eef3f7;font-size:10px;font-weight:700}.req-pill.ok{background:#e9f8ef;color:#08783e}.req-pill.bad{background:#fdecec;color:#9d2727}.req-dialog-grid{display:grid;gap:12px}.req-drop{border:1px dashed #9db8d1;border-radius:12px;background:#f9fcff;padding:18px}.req-preview{display:grid;gap:10px}.req-actions{display:flex;justify-content:flex-end;gap:8px}.req-warning{padding:9px 11px;border-radius:9px;background:#fff7ed;color:#8a4a00;font-size:11px}@media(max-width:800px){.reqs-kpis{grid-template-columns:repeat(2,1fr)}}`;
    document.head.appendChild(style);
  }

  function dialog() {
    let node=$('#sheets-requirements-dialog'); if (node) return node;
    node=document.createElement('dialog'); node.id='sheets-requirements-dialog'; node.className='wide-dialog';
    node.innerHTML=`<div class="dialog-form req-dialog-grid">
      <div class="dialog-head"><div><h2>Importar estudiantes y requisitos</h2><p>El archivo se analiza en este navegador. No se usa Firebase ni un servidor local.</p></div><button type="button" class="icon-button" data-req-close>×</button></div>
      <label class="req-drop">Archivo de requisitos
        <input id="sheets-req-file" type="file" accept=".xls,.xlsx,.csv,.tsv,.html,.htm,.xml">
      </label>
      <div id="sheets-req-preview" class="req-preview reqs-muted">Seleccione un archivo para analizarlo.</div>
      <div class="req-actions"><button type="button" class="button secondary" data-req-close>Cancelar</button><button type="button" class="button primary" id="sheets-req-save" disabled>Guardar requisitos en Google Sheets</button></div>
    </div>`;
    document.body.appendChild(node);
    $$('[data-req-close]',node).forEach(button=>button.onclick=()=>node.close());
    $('#sheets-req-file',node).addEventListener('change', async event => {
      const file=event.currentTarget.files?.[0]; if(!file) return;
      const preview=$('#sheets-req-preview',node); preview.textContent='Analizando localmente…';
      try {
        const rows=parseRows(await readFile(file));
        if(!rows.length) throw new Error('No se detectaron estudiantes con cédula en el archivo.');
        local.rows=rows; local.file=file;
        const [studentData] = await Promise.all([window.InformtitSheets.estudiantes().catch(()=>({estudiantes:[]}))]);
        local.existingIds=new Set((studentData.estudiantes||[]).map(row=>id(row.cedula)).filter(Boolean));
        renderPreview();
      } catch(error) { local.rows=[]; local.file=null; preview.innerHTML=`<div class="req-warning">${esc(error.message||error)}</div>`; $('#sheets-req-save',node).disabled=true; }
    });
    $('#sheets-req-save',node).onclick=save;
    return node;
  }

  function renderPreview() {
    const node=$('#sheets-req-preview'); if(!node) return;
    const rows=local.rows, eligible=rows.filter(row=>row.habilitado).length;
    const careers=new Set(rows.map(row=>fold(row.carrera)).filter(Boolean));
    const newIds=rows.filter(row=>!local.existingIds.has(row.cedula));
    node.innerHTML=`<div class="reqs-kpis">
      <div class="reqs-kpi"><span>Estudiantes</span><strong>${rows.length}</strong></div>
      <div class="reqs-kpi"><span>Habilitados</span><strong>${eligible}</strong></div>
      <div class="reqs-kpi"><span>Con pendientes</span><strong>${rows.length-eligible}</strong></div>
      <div class="reqs-kpi"><span>Carreras</span><strong>${careers.size}</strong></div></div>
      ${newIds.length ? `<div class="req-warning"><strong>${newIds.length} cédula(s) no existen todavía en la hoja ESTUDIANTES.</strong> Los requisitos sí pueden guardarse; la identidad maestra deberá incorporarse a Google Sheets cuando Apps Script tenga habilitada esa escritura.</div>`:''}
      <div class="reqs-muted">${esc(local.file?.name||'')} · ${rows.length} cédulas únicas · análisis realizado únicamente en el navegador.</div>`;
    $('#sheets-req-save').disabled=false;
  }

  async function currentPeriodId() {
    const report=window.state?.activeReport;
    if(!report) return '';
    return await window.InformtitPagesData?.resolvePeriodId?.(report) || clean(report.firebase_period_id || report.periodoId);
  }

  async function save() {
    if(local.saving || !local.rows.length) return;
    local.saving=true; const button=$('#sheets-req-save'); button.disabled=true; button.textContent='Guardando…';
    try {
      const periodoId=await currentPeriodId(); if(!periodoId) throw new Error('No se pudo identificar el período académico.');
      const jobs=local.rows.map(row=>({action:'guardar_requisito',data:{
        periodoId,cedula:row.cedula,academico:row.academico,documentacion:row.documentacion,financiero:row.financiero,
        titulacion:row.titulacion,practicas:row.practicas,vinculacion:row.vinculacion,seguimientoGraduados:row.seguimientoGraduados,
        ingles:row.ingles,actualizacionDatos:row.actualizacionDatos,aprobacionTitulacion:row.aprobacionTitulacion,
        aprobacionComplexivo:row.aprobacionComplexivo,updatedAt:new Date().toISOString()
      }}));
      const responses=await window.InformtitSheets.postMany(jobs,{concurrency:3});
      const failed=responses.filter(row=>!row.ok); if(failed.length) throw new Error(`${failed.length} de ${jobs.length} requisitos no pudieron guardarse.`);
      window.InformtitPagesData?.invalidate?.(periodoId);
      nodeClose();
      if(typeof toast==='function') toast(`${jobs.length} estudiantes actualizados en Requisitos de Google Sheets.`);
      if(typeof openReport==='function' && window.state?.activeReport?.id) await openReport(window.state.activeReport.id);
    } catch(error) { if(typeof toast==='function') toast(error.message||String(error),true); }
    finally { local.saving=false; if(button?.isConnected){button.disabled=false;button.textContent='Guardar requisitos en Google Sheets';} }
  }
  function nodeClose(){ $('#sheets-requirements-dialog')?.close(); }

  function renderRoster() {
    if(isPvc()) return;
    const host=$('#tab-roster'); const report=window.state?.activeReport; if(!host||!report?.id) return;
    host.innerHTML='<div class="panel"><div class="empty-mini">Cargando estudiantes y requisitos desde Google Sheets…</div></div>';
    api(`/api/reports/${report.id}/roster`).then(data=>{
      if(Number(window.state?.activeReport?.id)!==Number(report.id)||isPvc()) return;
      const s=data.summary||{}, rows=data.students||[];
      host.innerHTML=`<div class="panel reqs-shell">
        <div class="reqs-head"><div><h2>Estudiantes y Requisitos</h2><div class="reqs-muted">Google Sheets es la fuente principal del período.</div></div><button type="button" class="button primary" id="sheets-req-open">Importar estudiantes y requisitos</button></div>
        <div class="reqs-kpis"><div class="reqs-kpi"><span>Estudiantes</span><strong>${s.students||0}</strong></div><div class="reqs-kpi"><span>Carreras</span><strong>${s.careers||0}</strong></div><div class="reqs-kpi"><span>Habilitados</span><strong>${s.requirements_complete||0}</strong></div><div class="reqs-kpi"><span>Con pendientes</span><strong>${s.requirements_pending||0}</strong></div></div>
        <div class="reqs-toolbar"><label>Buscar<br><input id="reqs-search" placeholder="Nombre, cédula o carrera"></label><span class="reqs-muted">Una fila por cédula.</span></div>
        <div class="reqs-table-wrap"><table class="reqs-table"><thead><tr><th>Estudiante</th><th>Cédula</th><th>Carrera</th><th>Modalidad</th><th>Estado requisitos</th><th>Pendientes</th></tr></thead><tbody id="reqs-body"></tbody></table></div>
      </div>`;
      const draw=()=>{
        const q=fold($('#reqs-search')?.value||'');
        const visible=rows.filter(row=>!q||fold(`${row.full_name} ${row.identification} ${row.career_name}`).includes(q));
        $('#reqs-body').innerHTML=visible.length?visible.map(row=>`<tr><td><strong>${esc(row.full_name)}</strong></td><td>${esc(row.identification)}</td><td>${esc(row.career_name)}</td><td>${row.modality==='en_linea'?'Online':'Presencial'}</td><td><span class="req-pill ${row.requirements_complete?'ok':'bad'}">${row.requirements_complete?'Habilitado':'Pendiente'}</span></td><td>${esc((row.missing_requirement_labels||[]).join(' · ')||'—')}</td></tr>`).join(''):'<tr><td colspan="6">Sin coincidencias.</td></tr>';
      };
      $('#sheets-req-open').onclick=()=>openDialog(); $('#reqs-search').addEventListener('input',draw); draw();
    }).catch(error=>{host.innerHTML=`<div class="panel"><div class="empty-mini">${esc(error.message||error)}</div></div>`;});
  }

  function openDialog(){ local.rows=[];local.file=null; const node=dialog(); $('#sheets-req-file',node).value=''; $('#sheets-req-preview',node).textContent='Seleccione un archivo para analizarlo.'; $('#sheets-req-save',node).disabled=true; node.showModal(); }

  ensureStyles();
  const previousRender=window.renderReport;
  if(typeof previousRender==='function') window.renderReport=function(...args){ const result=previousRender.apply(this,args); if(!isPvc()) setTimeout(renderRoster,0); return result; };
  document.addEventListener('click',event=>{ if(event.target.closest?.('[data-tab="roster"]')&&!isPvc()) setTimeout(renderRoster,0); });
  setTimeout(()=>{if(window.state?.activeReport&&!isPvc())renderRoster();},0);
})();
