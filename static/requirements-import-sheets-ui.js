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
  const ALIASES = {
    cedula: ['numeroIdentificacion','cedula','identificacion','numero_identificacion','numero identificacion'],
    nombre: ['Nombres','nombre','nombre_estudiante','estudiante'],
    codigoCarrera: ['CodigoCarrera','codigoCarrera','codigo_carrera','codigo carrera'],
    carrera: ['NombreCarrera','carrera','nombre_carrera','nombre carrera'],
    jornada: ['HorarioComplexivo','horario','jornada','horario complexivo'],
    correoPersonal: ['CorreoPersonal','correoPersonal','correo personal'],
    correoInstitucional: ['CorreoInstitucional','correoInstitucional','correo institucional','correo'],
    celular: ['Celular','celular','telefono','teléfono'],
    sede: ['Sede','sede'],
    academico: ['Academico','académico','academico'],
    documentacion: ['Documentacion','documentación','documentacion'],
    financiero: ['Financiero','financiero'],
    titulacion: ['Titulacion','titulación','titulacion'],
    practicas: ['PrácticasVinculacion','PracticasVinculacion','Prácticas/Vinculación','Practicas/Vinculacion','Prácticas Vinculación','Practicas Vinculacion'],
    vinculacion: ['Vinculacion','vinculación','Vinculación'],
    seguimientoGraduados: ['SeguimientoGraduados','Seguimiento a Graduados','Seguimiento Graduados'],
    ingles: ['Ingles','Inglés','ingles'],
    actualizacionDatos: ['ActualizaciónDatos','ActualizacionDatos','Actualización de Datos','Actualizacion de Datos'],
    aprobacionTitulacion: ['AprobacionTitulacion','AprobaciónTitulacion','Aprobación Titulación'],
    aprobacionComplexivo: ['AprobacionComplexivoProyecto','AprobacionComplexivo','Aprobación Complexivo Proyecto'],
  };
  const REQUIRED_COLUMNS = [
    ['cedula','Cédula'],['academico','Académico'],['documentacion','Documentación'],['financiero','Financiero'],
    ['titulacion','Titulación'],['practicas','Prácticas/Vinculación'],['vinculacion','Vinculación'],
    ['seguimientoGraduados','Seguimiento a Graduados'],['ingles','Inglés'],['actualizacionDatos','Actualización de Datos'],
  ];

  const local = { rows: [], file: null, fileInfo: null, existingIds: new Set(), saving: false };
  const $ = (s,r=document) => r.querySelector(s);
  const $$ = (s,r=document) => [...r.querySelectorAll(s)];
  const clean = v => String(v ?? '').replace(/\u00a0/g,' ').trim().replace(/\s+/g,' ');
  const fold = v => clean(v).normalize('NFD').replace(/[\u0300-\u036f]/g,'').toUpperCase();
  const keyOf = v => fold(v).replace(/\uFFFD/g,'').replace(/[^A-Z0-9]/g,'');
  const esc = v => clean(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const id = v => clean(v).replace(/\D/g,'');
  const isPass = v => PASS.has(fold(v));
  const isPvc = () => clean(window.state?.activeReport?.report_type || window.state?.activeReport?.project_summary?.report_type).toLowerCase() === 'pvc';
  const canonicalCareer = value => window.InformtitPagesData?.canonicalCareer ? window.InformtitPagesData.canonicalCareer(value) : clean(value).toUpperCase();
  const modality = (career, code) => window.InformtitPagesData?.inferModality ? window.InformtitPagesData.inferModality(career, code) : (/ONLINE|EN LINEA|VIRTUAL/i.test(fold(career)) || /-L-/i.test(code) ? 'en_linea':'presencial');

  function first(row, aliases) {
    const index = new Map(Object.entries(row || {}).map(([key,value]) => [keyOf(key), value]));
    for (const alias of aliases) {
      const value = index.get(keyOf(alias));
      if (value !== undefined && clean(value) !== '') return value;
    }
    return '';
  }

  function hasColumn(row, aliases) {
    const keys = new Set(Object.keys(row || {}).map(keyOf));
    return aliases.some(alias => keys.has(keyOf(alias)));
  }

  function validateColumns(rows) {
    if (!rows.length) throw new Error('El archivo no contiene filas de datos.');
    const sample = rows[0] || {};
    const missing = REQUIRED_COLUMNS.filter(([key]) => !hasColumn(sample, ALIASES[key])).map(([,label]) => label);
    if (missing.length) {
      throw new Error(`No se reconocieron estas columnas obligatorias: ${missing.join(', ')}. No se guardó nada para evitar marcar requisitos incorrectamente.`);
    }
  }

  function parseRows(rows) {
    validateColumns(rows);
    const map = new Map();
    rows.forEach(raw => {
      const cedula = id(first(raw,ALIASES.cedula));
      if (!cedula) return;
      const careerRaw = clean(first(raw,ALIASES.carrera));
      const code = clean(first(raw,ALIASES.codigoCarrera));
      const row = {
        cedula,
        nombre: clean(first(raw,ALIASES.nombre)),
        codigoCarrera: code,
        carreraRaw: careerRaw,
        carrera: canonicalCareer(careerRaw),
        modalidad: modality(careerRaw, code),
        jornada: clean(first(raw,ALIASES.jornada)),
        correoPersonal: clean(first(raw,ALIASES.correoPersonal)).toLowerCase(),
        correoInstitucional: clean(first(raw,ALIASES.correoInstitucional)).toLowerCase(),
        celular: clean(first(raw,ALIASES.celular)),
        sede: clean(first(raw,ALIASES.sede)),
        academico: clean(first(raw,ALIASES.academico)),
        documentacion: clean(first(raw,ALIASES.documentacion)),
        financiero: clean(first(raw,ALIASES.financiero)),
        titulacion: clean(first(raw,ALIASES.titulacion)),
        practicas: clean(first(raw,ALIASES.practicas)),
        vinculacion: clean(first(raw,ALIASES.vinculacion)),
        seguimientoGraduados: clean(first(raw,ALIASES.seguimientoGraduados)),
        ingles: clean(first(raw,ALIASES.ingles)),
        actualizacionDatos: clean(first(raw,ALIASES.actualizacionDatos)),
        aprobacionTitulacion: clean(first(raw,ALIASES.aprobacionTitulacion)),
        aprobacionComplexivo: clean(first(raw,ALIASES.aprobacionComplexivo)),
      };
      row.pending = REQS.filter(([key]) => !isPass(row[key])).map(([,label]) => label);
      row.habilitado = row.pending.length === 0;
      map.set(cedula,row);
    });
    const parsed = [...map.values()];
    const corrupted = parsed.find(row => /�/.test(`${row.nombre} ${row.carreraRaw} ${row.practicas} ${row.actualizacionDatos}`));
    if (corrupted) throw new Error('El archivo contiene texto con codificación dañada. No se guardó nada. Vuelva a seleccionar el archivo para que Informtit detecte su codificación.');
    return parsed;
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
    let headerIndex = matrix.findIndex(row => row.some(cell => ['NUMEROIDENTIFICACION','NOMBRES','NOMBRECARRERA'].includes(keyOf(cell))));
    if (headerIndex < 0) headerIndex = 0;
    const headers=matrix[headerIndex];
    return matrix.slice(headerIndex+1).filter(row=>row.some(Boolean)).map(row=>Object.fromEntries(headers.map((h,i)=>[h || `col${i+1}`,row[i] ?? ''])));
  }

  function decodeHtmlBuffer(buffer) {
    const bytes = new Uint8Array(buffer);
    const previewBytes = bytes.subarray(0, Math.min(bytes.length, 8192));
    const preview1252 = new TextDecoder('windows-1252').decode(previewBytes);
    if (!/<table[\s>]/i.test(preview1252)) return null;

    let encoding = '';
    if (bytes[0] === 0xEF && bytes[1] === 0xBB && bytes[2] === 0xBF) encoding = 'utf-8';
    else if (bytes[0] === 0xFF && bytes[1] === 0xFE) encoding = 'utf-16le';
    else if (bytes[0] === 0xFE && bytes[1] === 0xFF) encoding = 'utf-16be';

    const meta = preview1252.match(/charset\s*=\s*["']?\s*([a-z0-9._-]+)/i)?.[1]?.toLowerCase() || '';
    if (!encoding && /^(utf-8|utf8)$/.test(meta)) encoding = 'utf-8';
    if (!encoding && /^(windows-1252|cp1252|iso-8859-1|latin1|latin-1)$/.test(meta)) encoding = 'windows-1252';

    let text = '';
    if (encoding) {
      text = new TextDecoder(encoding).decode(bytes);
    } else {
      try {
        text = new TextDecoder('utf-8',{fatal:true}).decode(bytes);
        encoding = 'utf-8';
      } catch (_) {
        text = new TextDecoder('windows-1252').decode(bytes);
        encoding = 'windows-1252';
      }
    }

    if (/�/.test(text)) {
      const fallback = new TextDecoder('windows-1252').decode(bytes);
      if (!/�/.test(fallback)) {
        text = fallback;
        encoding = 'windows-1252';
      }
    }
    return { text, encoding };
  }

  async function readFile(file) {
    const lower=file.name.toLowerCase();
    const buffer=await file.arrayBuffer();

    if (/\.(html?|xls)$/.test(lower)) {
      const legacy=decodeHtmlBuffer(buffer);
      if (legacy) {
        const rows=htmlRows(legacy.text);
        if (rows.length) return {rows,format:'HTML heredado (.xls)',encoding:legacy.encoding};
      }
    }

    const XLSX=await loadXlsx();
    const workbook=XLSX.read(buffer,{type:'array',cellDates:false});
    const sheet=workbook.Sheets[workbook.SheetNames[0]];
    return {rows:XLSX.utils.sheet_to_json(sheet,{defval:'',raw:false}),format:'Excel',encoding:'binario'};
  }

  function ensureStyles() {
    if ($('#req-neon-style')) return;
    const style=document.createElement('style'); style.id='req-neon-style';
    style.textContent=`
      .reqs-shell{display:grid;gap:14px}.reqs-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.reqs-head h2{margin:0 0 4px}.reqs-muted{font-size:12px;color:#64748b}.reqs-kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));border:1px solid #dce5ed;border-radius:12px;overflow:hidden;background:#fff}.reqs-kpi{padding:12px;border-right:1px solid #e7edf3}.reqs-kpi:last-child{border-right:0}.reqs-kpi span{display:block;color:#64748b;font-size:10px}.reqs-kpi strong{font-size:19px}.reqs-toolbar{display:flex;gap:8px;align-items:end;flex-wrap:wrap}.reqs-toolbar input{min-width:260px;padding:8px 10px;border:1px solid #cbd8e4;border-radius:8px}.reqs-table-wrap{max-height:580px;overflow:auto;border:1px solid #dce5ed;border-radius:12px}.reqs-table{width:100%;border-collapse:collapse;font-size:11px}.reqs-table th{position:sticky;top:0;background:#f7f9fc;padding:8px;text-align:left;border-bottom:1px solid #dce5ed}.reqs-table td{padding:8px;border-bottom:1px solid #edf2f6}.req-pill{display:inline-flex;padding:3px 7px;border-radius:999px;background:#eef3f7;font-size:10px;font-weight:700}.req-pill.ok{background:#e9f8ef;color:#08783e}.req-pill.bad{background:#fdecec;color:#9d2727}.req-dialog-grid{display:grid;gap:12px}.req-drop{border:1px dashed #9db8d1;border-radius:12px;background:#f9fcff;padding:18px}.req-preview{display:grid;gap:10px}.req-actions{display:flex;justify-content:flex-end;gap:8px}.req-warning{padding:9px 11px;border-radius:9px;background:#fff7ed;color:#8a4a00;font-size:11px}.req-success{padding:9px 11px;border-radius:9px;background:#ecfdf3;color:#08783e;font-size:11px}.req-progress{display:grid;gap:5px}.req-progress progress{width:100%;height:10px}@media(max-width:800px){.reqs-kpis{grid-template-columns:repeat(2,1fr)}}`;
    document.head.appendChild(style);
  }

  function dialog() {
    let node=$('#neon-requirements-dialog'); if (node) return node;
    node=document.createElement('dialog'); node.id='neon-requirements-dialog'; node.className='wide-dialog';
    node.innerHTML=`<div class="dialog-form req-dialog-grid">
      <div class="dialog-head"><div><h2>Importar estudiantes y requisitos</h2><p>El archivo se analiza en este navegador y se guarda en Neon.</p></div><button type="button" class="icon-button" data-req-close>×</button></div>
      <label class="req-drop">Archivo de requisitos<input id="neon-req-file" type="file" accept=".xls,.xlsx,.csv,.tsv,.html,.htm,.xml"></label>
      <div id="neon-req-preview" class="req-preview reqs-muted">Seleccione un archivo para analizarlo.</div>
      <div id="neon-req-progress" class="req-progress" hidden><progress max="100" value="0"></progress><span>Preparando…</span></div>
      <div class="req-actions"><button type="button" class="button secondary" data-req-close>Cancelar</button><button type="button" class="button primary" id="neon-req-save" disabled>Guardar en Neon</button></div>
    </div>`;
    document.body.appendChild(node);
    $$('[data-req-close]',node).forEach(button=>button.onclick=()=>{ if(!local.saving) node.close(); });
    $('#neon-req-file',node).addEventListener('change', async event => {
      const file=event.currentTarget.files?.[0]; if(!file) return;
      const preview=$('#neon-req-preview',node); preview.textContent='Analizando localmente…';
      try {
        const result=await readFile(file);
        const rows=parseRows(result.rows);
        if(!rows.length) throw new Error('No se detectaron estudiantes con cédula en el archivo.');
        local.rows=rows; local.file=file; local.fileInfo={format:result.format,encoding:result.encoding};
        const studentData=await window.InformtitSheets.estudiantes().catch(()=>({estudiantes:[]}));
        local.existingIds=new Set((studentData.estudiantes||[]).map(row=>id(row.cedula)).filter(Boolean));
        renderPreview();
      } catch(error) { local.rows=[]; local.file=null; local.fileInfo=null; preview.innerHTML=`<div class="req-warning">${esc(error.message||error)}</div>`; $('#neon-req-save',node).disabled=true; }
    });
    $('#neon-req-save',node).onclick=save;
    return node;
  }

  function renderPreview() {
    const node=$('#neon-req-preview'); if(!node) return;
    const rows=local.rows, eligible=rows.filter(row=>row.habilitado).length;
    const careers=new Set(rows.map(row=>fold(row.carrera)).filter(Boolean));
    const newIds=rows.filter(row=>!local.existingIds.has(row.cedula));
    const sourceInfo=local.fileInfo?.format==='HTML heredado (.xls)'
      ? `<div class="req-success"><strong>Archivo antiguo reconocido correctamente.</strong> ${esc(local.fileInfo.format)} · codificación ${esc(local.fileInfo.encoding)}. Los acentos y encabezados fueron normalizados antes de evaluar requisitos.</div>`
      : '';
    node.innerHTML=`<div class="reqs-kpis">
      <div class="reqs-kpi"><span>Estudiantes</span><strong>${rows.length}</strong></div>
      <div class="reqs-kpi"><span>Habilitados</span><strong>${eligible}</strong></div>
      <div class="reqs-kpi"><span>Con pendientes</span><strong>${rows.length-eligible}</strong></div>
      <div class="reqs-kpi"><span>Carreras</span><strong>${careers.size}</strong></div></div>
      ${sourceInfo}
      ${newIds.length ? `<div class="req-warning"><strong>${newIds.length} estudiante(s) son nuevos.</strong> Se crearán automáticamente en Neon junto con su matrícula y requisitos.</div>`:''}
      <div class="reqs-muted">${esc(local.file?.name||'')} · ${rows.length} cédulas únicas · una importación masiva, sin cientos de solicitudes individuales.</div>`;
    $('#neon-req-save').disabled=false;
  }

  async function currentPeriodId() {
    const report=window.state?.activeReport;
    if(!report) return '';
    return await window.InformtitPagesData?.resolvePeriodId?.(report) || clean(report.firebase_period_id || report.periodoId);
  }

  async function save() {
    if(local.saving || !local.rows.length) return;
    local.saving=true;
    const button=$('#neon-req-save'); const progress=$('#neon-req-progress'); const bar=progress.querySelector('progress'); const label=progress.querySelector('span');
    button.disabled=true; button.textContent='Guardando…'; progress.hidden=false; bar.value=2; label.textContent='Preparando importación…';
    try {
      const periodoId=await currentPeriodId(); if(!periodoId) throw new Error('No se pudo identificar el período académico.');
      if(!window.InformtitNeon?.bulkUpsertStudentsRequirements) throw new Error('El proveedor Neon no está disponible.');
      const total=local.rows.length;
      await window.InformtitNeon.bulkUpsertStudentsRequirements(local.rows,periodoId,local.file?.name||'',(completed,_total,stage)=>{
        const pct=Math.max(2,Math.min(100,Math.round((Number(completed||0)/Math.max(1,total))*100)));
        bar.value=pct; label.textContent=`${stage || 'Guardando'} · ${pct}%`;
      });
      bar.value=100; label.textContent=`Completado · ${total} estudiantes`;
      window.InformtitPagesData?.invalidate?.(periodoId);
      if(typeof toast==='function') toast(`${total} estudiantes, matrículas y requisitos guardados en Neon.`);
      setTimeout(()=>nodeClose(),350);
      if(typeof openReport==='function' && window.state?.activeReport?.id) await openReport(window.state.activeReport.id);
    } catch(error) {
      label.textContent='La importación no se completó.';
      if(typeof toast==='function') toast(error.message||String(error),true);
      else alert(error.message||String(error));
    } finally {
      local.saving=false;
      if(button?.isConnected){button.disabled=false;button.textContent='Guardar en Neon';}
    }
  }
  function nodeClose(){ $('#neon-requirements-dialog')?.close(); }

  function renderRoster() {
    if(isPvc()) return;
    const host=$('#tab-roster'); const report=window.state?.activeReport; if(!host||!report?.id) return;
    host.innerHTML='<div class="panel"><div class="empty-mini">Cargando estudiantes y requisitos desde Neon…</div></div>';
    api(`/api/reports/${report.id}/roster`).then(data=>{
      if(Number(window.state?.activeReport?.id)!==Number(report.id)||isPvc()) return;
      const s=data.summary||{}, rows=data.students||[];
      host.innerHTML=`<div class="panel reqs-shell">
        <div class="reqs-head"><div><h2>Estudiantes y Requisitos</h2><div class="reqs-muted">Neon PostgreSQL es la fuente principal del período.</div></div><button type="button" class="button primary" id="neon-req-open">Importar estudiantes y requisitos</button></div>
        <div class="reqs-kpis"><div class="reqs-kpi"><span>Estudiantes</span><strong>${s.students||0}</strong></div><div class="reqs-kpi"><span>Carreras</span><strong>${s.careers||0}</strong></div><div class="reqs-kpi"><span>Habilitados</span><strong>${s.requirements_complete||0}</strong></div><div class="reqs-kpi"><span>Con pendientes</span><strong>${s.requirements_pending||0}</strong></div></div>
        <div class="reqs-toolbar"><label>Buscar<br><input id="reqs-search" placeholder="Nombre, cédula o carrera"></label><span class="reqs-muted">Una fila por cédula.</span></div>
        <div class="reqs-table-wrap"><table class="reqs-table"><thead><tr><th>Estudiante</th><th>Cédula</th><th>Carrera</th><th>Modalidad</th><th>Estado requisitos</th><th>Pendientes</th></tr></thead><tbody id="reqs-body"></tbody></table></div>
      </div>`;
      const draw=()=>{
        const q=fold($('#reqs-search')?.value||'');
        const visible=rows.filter(row=>!q||fold(`${row.full_name} ${row.identification} ${row.career_name}`).includes(q));
        $('#reqs-body').innerHTML=visible.length?visible.map(row=>`<tr><td><strong>${esc(row.full_name)}</strong></td><td>${esc(row.identification)}</td><td>${esc(row.career_name)}</td><td>${row.modality==='en_linea'?'Online':'Presencial'}</td><td><span class="req-pill ${row.requirements_complete?'ok':'bad'}">${row.requirements_complete?'Habilitado':'Pendiente'}</span></td><td>${esc((row.missing_requirement_labels||[]).join(' · ')||'—')}</td></tr>`).join(''):'<tr><td colspan="6">Sin coincidencias.</td></tr>';
      };
      $('#neon-req-open').onclick=()=>openDialog(); $('#reqs-search').addEventListener('input',draw); draw();
    }).catch(error=>{host.innerHTML=`<div class="panel"><div class="empty-mini">${esc(error.message||error)}</div></div>`;});
  }

  function openDialog(){
    local.rows=[];local.file=null;local.fileInfo=null;
    const node=dialog();
    $('#neon-req-file',node).value='';
    $('#neon-req-preview',node).textContent='Seleccione un archivo para analizarlo.';
    $('#neon-req-progress',node).hidden=true;
    $('#neon-req-save',node).disabled=true;
    node.showModal();
  }

  window.InformtitRequirementsImport = Object.freeze({
    version:'4.1.0',
    decodeHtmlBuffer,
    htmlRows,
    parseRows,
  });

  ensureStyles();
  const previousRender=window.renderReport;
  if(typeof previousRender==='function') window.renderReport=function(...args){ const result=previousRender.apply(this,args); if(!isPvc()) setTimeout(renderRoster,0); return result; };
  document.addEventListener('click',event=>{ if(event.target.closest?.('[data-tab="roster"]')&&!isPvc()) setTimeout(renderRoster,0); });
  setTimeout(()=>{if(window.state?.activeReport&&!isPvc())renderRoster();},0);
})();