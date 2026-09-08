(() => {
  'use strict';

  const XLSX_SRC = 'https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js';
  const PASS = new Set(['CUMPLE', 'SI', 'SÍ', 'APROBADO', 'OK', 'TRUE', '1']);
  const REQUIREMENT_KEYS = [
    ['academico', 'Académico'],
    ['documentacion', 'Documentación'],
    ['financiero', 'Financiero'],
    ['titulacion', 'Titulación'],
    ['practicas', 'Prácticas/Vinculación'],
    ['vinculacion', 'Vinculación'],
    ['seguimientoGraduados', 'Seguimiento a Graduados'],
    ['ingles', 'Inglés'],
    ['actualizacionDatos', 'Actualización de Datos'],
  ];

  const pvcState = {
    periodId: '',
    periodLabel: '',
    requirementsFile: null,
    resultsFile: null,
    requirements: [],
    results: [],
    merged: [],
    selectedCedula: '',
    filter: 'all',
    query: '',
  };

  const $ = (s, root = document) => root.querySelector(s);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const norm = value => String(value ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toUpperCase().replace(/[^A-Z0-9]+/g,' ').replace(/\s+/g,' ').trim();
  const cedula = value => String(value ?? '').replace(/\D/g, '').trim();
  const num = value => {
    if (value === null || value === undefined) return null;
    const text = String(value).trim();
    if (!text || norm(text) === 'NULL' || text === '—' || text === '-') return null;
    const n = Number(text.replace(',', '.'));
    return Number.isFinite(n) ? n : null;
  };
  const fmt = value => Number.isFinite(Number(value)) ? Number(value).toFixed(2).replace('.', ',') : '—';
  const truthyRequirement = value => PASS.has(norm(value));
  const first = (row, keys) => {
    const map = new Map(Object.entries(row || {}).map(([k,v]) => [norm(k).replace(/ /g,''), v]));
    for (const key of keys) {
      const value = map.get(norm(key).replace(/ /g,''));
      if (value !== undefined && value !== '') return value;
    }
    return '';
  };
  const isPvc = () => String(state?.activeReport?.report_type || state?.activeReport?.project_summary?.report_type || '').toLowerCase() === 'pvc';

  function injectStyles() {
    if ($('#pvc-workspace-style')) return;
    const style = document.createElement('style');
    style.id = 'pvc-workspace-style';
    style.textContent = `
      .pvcw{display:grid;gap:14px}.pvcw-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}.pvcw-head h2{margin:0 0 4px}.pvcw-muted{color:#60758a;font-size:12px}.pvcw-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.pvcw-card{border:1px solid #dce6ef;border-radius:12px;background:#fff;padding:14px}.pvcw-card h3{font-size:14px;margin:0 0 5px}.pvcw-upload{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:10px}.pvcw-upload input{max-width:100%;font-size:12px}.pvcw-kpis{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));border:1px solid #dce6ef;border-radius:12px;overflow:hidden;background:#fff}.pvcw-kpi{padding:11px 12px;border-right:1px solid #e7edf3}.pvcw-kpi:last-child{border-right:0}.pvcw-kpi span{display:block;font-size:10px;color:#64788a}.pvcw-kpi strong{font-size:18px}.pvcw-ok{color:#08783e}.pvcw-warn{color:#b86200}.pvcw-bad{color:#a92f2f}.pvcw-toolbar{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.pvcw-toolbar input{min-width:240px;max-width:360px;padding:8px 10px;border:1px solid #cdd9e4;border-radius:8px}.pvcw-filter{border:1px solid #d5e0ea;background:white;border-radius:8px;padding:7px 10px;font-size:11px;cursor:pointer}.pvcw-filter.active{background:#eaf3fb;border-color:#abc7e2;color:#174b7a;font-weight:700}.pvcw-table-wrap{border:1px solid #dce6ef;border-radius:12px;overflow:auto;max-height:560px;background:white}.pvcw-table{width:100%;border-collapse:collapse;font-size:11px}.pvcw-table th{position:sticky;top:0;background:#f6f9fc;text-align:left;padding:9px;border-bottom:1px solid #dce6ef;z-index:2}.pvcw-table td{padding:9px;border-bottom:1px solid #edf2f6;vertical-align:middle}.pvcw-table tr{cursor:pointer}.pvcw-table tr:hover{background:#f9fbfd}.pvcw-pill{display:inline-flex;padding:3px 7px;border-radius:999px;font-size:10px;font-weight:700;background:#eef3f7;color:#49647c}.pvcw-pill.ok{background:#e9f8ef;color:#08783e}.pvcw-pill.warn{background:#fff3df;color:#9a5a00}.pvcw-pill.bad{background:#fdecec;color:#9d2727}.pvcw-drawer{position:fixed;inset:0;background:rgba(10,25,42,.28);z-index:9999;display:flex;justify-content:flex-end}.pvcw-drawer[hidden]{display:none}.pvcw-sheet{width:min(760px,95vw);height:100%;background:white;box-shadow:-8px 0 24px rgba(0,0,0,.12);overflow:auto;padding:18px}.pvcw-sheet-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;border-bottom:1px solid #e5ecf3;padding-bottom:12px}.pvcw-sheet-head h2{margin:0}.pvcw-close{border:0;background:#f0f4f7;border-radius:8px;padding:7px 10px;cursor:pointer}.pvcw-section{margin-top:16px}.pvcw-section h3{font-size:13px;margin:0 0 8px}.pvcw-info{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.pvcw-info>div{padding:9px;background:#f7f9fb;border-radius:8px;font-size:11px}.pvcw-req{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px}.pvcw-req>div{display:flex;justify-content:space-between;gap:8px;padding:8px;border:1px solid #e3eaf0;border-radius:8px;font-size:11px}.pvcw-tribunal{width:100%;border-collapse:collapse;font-size:11px}.pvcw-tribunal th,.pvcw-tribunal td{border:1px solid #e3eaf0;padding:7px;text-align:left}.pvcw-alert{border:1px solid #f1d4a2;background:#fff9ef;color:#7a5a22;border-radius:9px;padding:9px 11px;font-size:11px}.pvcw-source-status{margin-top:8px;font-size:11px}.pvcw-actions{display:flex;justify-content:flex-end;gap:8px}.pvcw-save{border:0;background:#1f67a6;color:white;border-radius:8px;padding:8px 12px;font-weight:700;cursor:pointer}.pvcw-save:disabled{opacity:.5;cursor:wait}@media(max-width:900px){.pvcw-grid{grid-template-columns:1fr}.pvcw-kpis{grid-template-columns:repeat(2,1fr)}.pvcw-info,.pvcw-req{grid-template-columns:1fr}}`;
    document.head.appendChild(style);
  }

  async function loadXlsx() {
    if (window.XLSX) return window.XLSX;
    await new Promise((resolve,reject) => {
      const s = document.createElement('script');
      s.src = XLSX_SRC; s.onload = resolve; s.onerror = () => reject(new Error('No se pudo cargar el lector de Excel.'));
      document.head.appendChild(s);
    });
    return window.XLSX;
  }

  async function readWorkbook(file) {
    const XLSX = await loadXlsx();
    const buffer = await file.arrayBuffer();
    return XLSX.read(buffer, {type:'array', cellDates:false});
  }

  function rowsFromWorkbook(workbook) {
    const firstSheet = workbook.SheetNames[0];
    return window.XLSX.utils.sheet_to_json(workbook.Sheets[firstSheet], {defval:'', raw:false});
  }

  function parseRequirements(rows) {
    const map = new Map();
    rows.forEach(row => {
      const id = cedula(first(row,['numeroIdentificacion','cedula','identificacion','numero identificacion']));
      if (!id) return;
      const record = {
        cedula:id,
        nombre:String(first(row,['Nombres','nombre','nombre_estudiante'])||'').trim(),
        codigoCarrera:String(first(row,['CodigoCarrera','codigo carrera','codigoCarrera'])||'').trim(),
        carrera:String(first(row,['NombreCarrera','carrera','nombre_carrera'])||'').trim(),
        academico:first(row,['Academico']), documentacion:first(row,['Documentacion']), financiero:first(row,['Financiero']),
        titulacion:first(row,['Titulacion']), practicas:first(row,['PrácticasVinculacion','PracticasVinculacion','Practicas']),
        vinculacion:first(row,['Vinculacion']), seguimientoGraduados:first(row,['SeguimientoGraduados']), ingles:first(row,['Ingles']),
        actualizacionDatos:first(row,['ActualizaciónDatos','ActualizacionDatos']), aprobacionGeneral:first(row,['AprobacionTitulacion']),
      };
      record.pending = REQUIREMENT_KEYS.filter(([key]) => !truthyRequirement(record[key])).map(([,label]) => label);
      record.habilitado = record.pending.length === 0;
      map.set(id, record);
    });
    return [...map.values()];
  }

  function parseResults(rows) {
    const map = new Map();
    rows.forEach(row => {
      const id = cedula(first(row,['cedula','numeroIdentificacion','identificacion']));
      if (!id) return;
      const result = {
        cedula:id,
        nombre:String(first(row,['nombre_estudiante','Nombres','nombre'])||'').trim(),
        periodoFuente:String(first(row,['periodoAcademico','periodo_academico','periodo'])||'').trim(),
        modalidad:String(first(row,['trabajoTitulacion','modalidad'])||'Artículo académico').trim(),
        acta:String(first(row,['numeroActaGrado','numero_acta_grado','acta','numeroActa'])||'').trim(),
        fechaActa:String(first(row,['fechaActaGrado','fecha_acta_grado','fechaActa'])||'').trim(),
        tutor:String(first(row,['nombreTutor','tutor','tutor_name'])||'').trim(),
        lector:String(first(row,['nombreLector','lector','reader_name'])||'').trim(),
        vocal1:String(first(row,['nombreVocal1','vocal1','primerVocal'])||'').trim(),
        vocal2:String(first(row,['nombreVocal2','vocal2','segundoVocal'])||'').trim(),
        vocal3:String(first(row,['nombreVocal3','vocal3','tercerVocal'])||'').trim(),
        evaluacionTutor:num(first(row,['evaluacionTutor','notaTutor','calificacionTutor'])),
        evaluacionLector:num(first(row,['evaluacionLector','notaLector','calificacionLector'])),
        promedioEscrito:num(first(row,['promedio_trabajo_escrito','promedioTrabajoEscrito','promedioEscrito'])),
        practica1:num(first(row,['evaluacionPracticaVocal1','evaluacionPractica1','practicoVocal1'])),
        practica2:num(first(row,['evaluacionPracticaVocal2','evaluacionPractica2','practicoVocal2'])),
        practica3:num(first(row,['evaluacionPracticaVocal3','evaluacionPractica3','practicoVocal3'])),
        defensa1:num(first(row,['evaluacionDefensaVocal1','evaluacionDefensa1','defensaVocal1'])),
        defensa2:num(first(row,['evaluacionDefensaVocal2','evaluacionDefensa2','defensaVocal2'])),
        defensa3:num(first(row,['evaluacionDefensaVocal3','evaluacionDefensa3','defensaVocal3'])),
        defensaOral:num(first(row,['notaDefensaOral','defensaOral','promedioDefensa'])),
        notaFinal:num(first(row,['notaTrabajoTitulacion','notaFinal','calificacionFinal'])),
        promedioAcumulado:num(first(row,['notaPromedioAcumulado','promedioAcumulado'])),
        raw:row,
      };
      map.set(id, result);
    });
    return [...map.values()];
  }

  function computeStatus(req, res) {
    if (!req && res) return {key:'incomplete', label:'Información incompleta', cls:'warn'};
    if (req && !req.habilitado) return {key:'not_eligible', label:'No habilitado', cls:'bad'};
    if (req?.habilitado && !res) return {key:'pending', label:'Habilitado pendiente', cls:'warn'};
    if (req?.habilitado && res) {
      if (!Number.isFinite(Number(res.notaFinal))) return {key:'pending', label:'Habilitado pendiente', cls:'warn'};
      return Number(res.notaFinal) >= 7
        ? {key:'approved', label:'Habilitado y aprobado', cls:'ok'}
        : {key:'failed', label:'Reprobado', cls:'bad'};
    }
    return {key:'incomplete', label:'Información incompleta', cls:'warn'};
  }

  function rebuildMerged() {
    const req = new Map(pvcState.requirements.map(r => [r.cedula,r]));
    const res = new Map(pvcState.results.map(r => [r.cedula,r]));
    const ids = new Set([...req.keys(), ...res.keys()]);
    pvcState.merged = [...ids].map(id => {
      const requirement = req.get(id) || null;
      const result = res.get(id) || null;
      return {cedula:id, requirement, result, status:computeStatus(requirement,result)};
    }).sort((a,b) => String(a.requirement?.nombre || a.result?.nombre || '').localeCompare(String(b.requirement?.nombre || b.result?.nombre || ''),'es'));
  }

  function metrics() {
    const requirements = pvcState.requirements.length;
    const results = pvcState.results.length;
    const matched = pvcState.merged.filter(r => r.requirement && r.result).length;
    const onlyReq = pvcState.merged.filter(r => r.requirement && !r.result).length;
    const onlyRes = pvcState.merged.filter(r => !r.requirement && r.result).length;
    const eligible = pvcState.requirements.filter(r => r.habilitado).length;
    const pendingReq = requirements - eligible;
    return {requirements,results,matched,onlyReq,onlyRes,eligible,pendingReq};
  }

  function setPvcTabs() {
    const tabs = $('#report-tabs');
    if (!tabs || !isPvc()) return;
    const labels = {summary:'Control del Informe', students:'Estudiantes', requirements:'Requisitos', projects:'Resultados', schedules:'Cronogramas'};
    Object.entries(labels).forEach(([name,label]) => { const b = tabs.querySelector(`[data-tab="${name}"]`); if (b) {b.hidden=false;b.textContent=label;} });
    ['nuclei','careers','imports'].forEach(name => { const b=tabs.querySelector(`[data-tab="${name}"]`); if(b)b.hidden=true; const c=$(`#tab-${name}`); if(c)c.hidden=true; });
    const modality = $('#report-modality'); if(modality) modality.textContent='PVC · Artículo Académico';
  }

  function renderControl() {
    const tab = $('#tab-summary'); if (!tab || !isPvc()) return;
    const m = metrics();
    tab.innerHTML = `<div class="pvcw">
      <div class="pvcw-head"><div><h2>Fuentes de datos del período</h2><div class="pvcw-muted">Primero cargue los dos Excel. Informtit cruza los estudiantes únicamente por cédula.</div></div><span class="pvcw-pill">Google Sheets · base principal</span></div>
      <div class="pvcw-grid">
        <section class="pvcw-card"><h3>Excel 1 — Requisitos de Titulación</h3><div class="pvcw-muted">Cédula, nombre, carrera y estado de los requisitos.</div><div class="pvcw-upload"><input id="pvcw-req-file" type="file" accept=".xls,.xlsx"><span id="pvcw-req-state" class="pvcw-source-status">${pvcState.requirementsFile ? esc(pvcState.requirementsFile.name) : 'Sin archivo'}</span></div>${m.requirements ? `<div class="pvcw-source-status pvcw-ok"><strong>Archivo cargado ✓</strong> · ${m.requirements} estudiantes · ${m.eligible} habilitados · ${m.pendingReq} con pendientes</div>`:''}</section>
        <section class="pvcw-card"><h3>Excel 2 — Resultados del Proceso de Titulación</h3><div class="pvcw-muted">Acta, tutor, lector, tribunal, evaluaciones y resultado final.</div><div class="pvcw-upload"><input id="pvcw-results-file" type="file" accept=".xlsx,.xls"><span id="pvcw-results-state" class="pvcw-source-status">${pvcState.resultsFile ? esc(pvcState.resultsFile.name) : 'Sin archivo'}</span></div>${m.results ? `<div class="pvcw-source-status pvcw-ok"><strong>Archivo cargado ✓</strong> · ${m.results} estudiantes con resultados</div>`:''}</section>
      </div>
      <div class="pvcw-kpis"><div class="pvcw-kpi"><span>Requisitos</span><strong>${m.requirements}</strong></div><div class="pvcw-kpi"><span>Resultados</span><strong>${m.results}</strong></div><div class="pvcw-kpi"><span>Coincidencias por cédula</span><strong class="pvcw-ok">${m.matched}</strong></div><div class="pvcw-kpi"><span>Solo requisitos</span><strong class="pvcw-warn">${m.onlyReq}</strong></div><div class="pvcw-kpi"><span>Solo resultados</span><strong class="${m.onlyRes?'pvcw-bad':''}">${m.onlyRes}</strong></div></div>
      <div class="pvcw-actions"><button class="pvcw-filter" id="pvcw-view-inconsistencies">Ver inconsistencias</button><button class="pvcw-save" id="pvcw-save-all" ${(!m.requirements || !m.results)?'disabled':''}>Guardar en Google Sheets</button></div>
    </div>`;
    bindControlEvents();
  }

  function bindControlEvents() {
    $('#pvcw-req-file')?.addEventListener('change', async e => {
      const file=e.currentTarget.files?.[0]; if(!file)return;
      try { const wb=await readWorkbook(file); pvcState.requirements=parseRequirements(rowsFromWorkbook(wb)); pvcState.requirementsFile=file; rebuildMerged(); renderAllPvc(); }
      catch(error){ toast(error.message||'No se pudo leer el Excel de requisitos.',true); }
    });
    $('#pvcw-results-file')?.addEventListener('change', async e => {
      const file=e.currentTarget.files?.[0]; if(!file)return;
      try { const wb=await readWorkbook(file); pvcState.results=parseResults(rowsFromWorkbook(wb)); pvcState.resultsFile=file; rebuildMerged(); renderAllPvc(); }
      catch(error){ toast(error.message||'No se pudo leer el Excel de resultados.',true); }
    });
    $('#pvcw-view-inconsistencies')?.addEventListener('click',()=>{ pvcState.filter='incomplete'; activateTab('students'); renderStudents(); });
    $('#pvcw-save-all')?.addEventListener('click', saveToSheets);
  }

  async function saveToSheets() {
    if (!window.InformtitSheets) return toast('No está disponible la conexión con Google Sheets.',true);
    const button=$('#pvcw-save-all'); if(button)button.disabled=true;
    try {
      const periodId = pvcState.periodId || activePeriodId();
      if (!periodId) throw new Error('No se pudo identificar el período del informe.');
      const items=[];
      pvcState.requirements.forEach(r => items.push({action:'guardar_requisito',data:{periodoId,cedula:r.cedula,academico:r.academico,documentacion:r.documentacion,financiero:r.financiero,titulacion:r.titulacion,practicas:r.practicas,vinculacion:r.vinculacion,seguimientoGraduados:r.seguimientoGraduados,ingles:r.ingles,actualizacionDatos:r.actualizacionDatos,updatedAt:new Date().toISOString()}}));
      pvcState.results.forEach(r => {
        const req=pvcState.requirements.find(x=>x.cedula===r.cedula);
        items.push({action:'guardar_trabajo_titulacion',data:{periodoId,cedula:r.cedula,nombre:req?.nombre||r.nombre,carrera:req?.carrera||'',modalidad:'Articulo academico',notaTutor:r.evaluacionTutor,notaLector:r.evaluacionLector,promedioEscrito:r.promedioEscrito,promedioDefensa:r.defensaOral,notaFinal:r.notaFinal,estado:Number(r.notaFinal)>=7?'APROBADO':'REPROBADO',titulo:'Artículo académico',updatedAt:new Date().toISOString()}});
      });
      const response=await window.InformtitSheets.postMany(items,{concurrency:3});
      const failed=response.filter(r=>!r.ok);
      if(failed.length) throw new Error(`${failed.length} registros no pudieron guardarse.`);
      toast(`PVC guardado: ${items.length} registros actualizados en Google Sheets.`);
    } catch(error){ toast(error.message||'No se pudo guardar el PVC.',true); }
    finally{ if(button)button.disabled=false; }
  }

  function activePeriodId() {
    const report=state?.activeReport||{};
    return String(report.firebase_period_id||report.periodoId||report.period_id||report.id||'');
  }

  function renderStudents() {
    const tab=$('#tab-students'); if(!tab||!isPvc())return;
    const rows=pvcState.merged.filter(row => {
      const name=norm(row.requirement?.nombre||row.result?.nombre||'');
      const q=norm(pvcState.query);
      if(q && !name.includes(q) && !row.cedula.includes(pvcState.query.replace(/\D/g,''))) return false;
      if(pvcState.filter==='all') return true;
      if(pvcState.filter==='eligible') return row.requirement?.habilitado;
      if(pvcState.filter==='requirements') return row.requirement && !row.requirement.habilitado;
      if(pvcState.filter==='approved') return row.status.key==='approved';
      if(pvcState.filter==='failed') return row.status.key==='failed';
      if(pvcState.filter==='pending') return row.status.key==='pending';
      if(pvcState.filter==='incomplete') return !row.requirement || !row.result;
      return true;
    });
    tab.innerHTML=`<div class="pvcw"><div class="pvcw-head"><div><h2>Estudiantes</h2><div class="pvcw-muted">Una fila por cédula. Requisitos y resultado se consolidan sin unir por nombre.</div></div><span class="pvcw-pill">${pvcState.merged.length} consolidados</span></div><div class="pvcw-toolbar"><input id="pvcw-search" placeholder="Buscar por nombre o cédula" value="${esc(pvcState.query)}">${[['all','Todos'],['eligible','Cumplen requisitos'],['requirements','Con pendientes'],['approved','Aprobados'],['failed','Reprobados'],['pending','Sin resultado'],['incomplete','Inconsistencias']].map(([k,l])=>`<button class="pvcw-filter ${pvcState.filter===k?'active':''}" data-pvcw-filter="${k}">${l}</button>`).join('')}</div><div class="pvcw-table-wrap"><table class="pvcw-table"><thead><tr><th>Estudiante</th><th>Cédula</th><th>Carrera</th><th>Requisitos</th><th>Resultado</th><th>Nota final</th><th>Estado</th></tr></thead><tbody>${rows.map(row=>{const req=row.requirement,res=row.result;return `<tr data-pvcw-student="${row.cedula}"><td>${esc(req?.nombre||res?.nombre||'')}</td><td>${row.cedula}</td><td>${esc(req?.carrera||'—')}</td><td><span class="pvcw-pill ${req?.habilitado?'ok':'bad'}">${req?(req.habilitado?'Cumple':'Pendiente'):'No encontrado'}</span></td><td>${res?'Con resultado':'Sin resultado'}</td><td>${fmt(res?.notaFinal)}</td><td><span class="pvcw-pill ${row.status.cls}">${esc(row.status.label)}</span></td></tr>`}).join('')}</tbody></table></div></div>`;
    $('#pvcw-search')?.addEventListener('input',e=>{pvcState.query=e.currentTarget.value;renderStudents();});
    tab.querySelectorAll('[data-pvcw-filter]').forEach(b=>b.onclick=()=>{pvcState.filter=b.dataset.pvcwFilter;renderStudents();});
    tab.querySelectorAll('[data-pvcw-student]').forEach(tr=>tr.onclick=()=>openStudent(tr.dataset.pvcwStudent));
  }

  function renderRequirements() {
    const tab=$('#tab-requirements'); if(!tab||!isPvc())return;
    const total=pvcState.requirements.length, eligible=pvcState.requirements.filter(r=>r.habilitado).length;
    const cards=REQUIREMENT_KEYS.map(([key,label])=>{const pending=pvcState.requirements.filter(r=>!truthyRequirement(r[key])).length;return `<button class="pvcw-card pvcw-filter" data-req-key="${key}" style="text-align:left"><h3>${esc(label)}</h3><strong>${pending}</strong> pendientes</button>`}).join('');
    tab.innerHTML=`<div class="pvcw"><div class="pvcw-head"><div><h2>Requisitos de Titulación</h2><div class="pvcw-muted">${total} estudiantes · ${eligible} habilitados · ${total-eligible} con pendientes</div></div></div><div class="pvcw-grid">${cards}</div><div id="pvcw-req-list"></div></div>`;
    tab.querySelectorAll('[data-req-key]').forEach(btn=>btn.onclick=()=>{const key=btn.dataset.reqKey;const label=REQUIREMENT_KEYS.find(x=>x[0]===key)?.[1]||key;const pending=pvcState.requirements.filter(r=>!truthyRequirement(r[key]));$('#pvcw-req-list').innerHTML=`<section class="pvcw-card"><h3>${esc(label)} — ${pending.length} pendientes</h3><div class="pvcw-table-wrap"><table class="pvcw-table"><thead><tr><th>Estudiante</th><th>Cédula</th><th>Carrera</th><th>Estado</th></tr></thead><tbody>${pending.map(r=>`<tr data-pvcw-student="${r.cedula}"><td>${esc(r.nombre)}</td><td>${r.cedula}</td><td>${esc(r.carrera)}</td><td>${esc(r[key]||'Pendiente')}</td></tr>`).join('')}</tbody></table></div></section>`;$('#pvcw-req-list').querySelectorAll('[data-pvcw-student]').forEach(tr=>tr.onclick=()=>openStudent(tr.dataset.pvcwStudent));});
  }

  function renderResults() {
    const tab=$('#tab-projects'); if(!tab||!isPvc())return;
    const evaluated=pvcState.results.filter(r=>Number.isFinite(Number(r.notaFinal))).length;
    const approved=pvcState.merged.filter(r=>r.status.key==='approved').length;
    const failed=pvcState.merged.filter(r=>r.status.key==='failed').length;
    const avg=arr=>{const xs=arr.filter(x=>Number.isFinite(Number(x))).map(Number);return xs.length?xs.reduce((a,b)=>a+b,0)/xs.length:null};
    tab.innerHTML=`<div class="pvcw"><div class="pvcw-head"><div><h2>Resultados de Titulación</h2><div class="pvcw-muted">Artículo Académico. La carga se realiza en Control del Informe.</div></div></div><div class="pvcw-kpis"><div class="pvcw-kpi"><span>Evaluados</span><strong>${evaluated}</strong></div><div class="pvcw-kpi"><span>Aprobados</span><strong class="pvcw-ok">${approved}</strong></div><div class="pvcw-kpi"><span>Reprobados</span><strong class="pvcw-bad">${failed}</strong></div><div class="pvcw-kpi"><span>Promedio escrito</span><strong>${fmt(avg(pvcState.results.map(r=>r.promedioEscrito)))}</strong></div><div class="pvcw-kpi"><span>Promedio final</span><strong>${fmt(avg(pvcState.results.map(r=>r.notaFinal)))}</strong></div></div><div class="pvcw-table-wrap"><table class="pvcw-table"><thead><tr><th>Estudiante</th><th>Cédula</th><th>Carrera</th><th>Tutor</th><th>Lector</th><th>Escrito</th><th>Defensa</th><th>Final</th><th>Estado</th></tr></thead><tbody>${pvcState.merged.filter(r=>r.result).map(r=>`<tr data-pvcw-student="${r.cedula}"><td>${esc(r.requirement?.nombre||r.result.nombre)}</td><td>${r.cedula}</td><td>${esc(r.requirement?.carrera||'—')}</td><td>${esc(r.result.tutor||'—')}</td><td>${esc(r.result.lector||'—')}</td><td>${fmt(r.result.promedioEscrito)}</td><td>${fmt(r.result.defensaOral)}</td><td>${fmt(r.result.notaFinal)}</td><td><span class="pvcw-pill ${r.status.cls}">${esc(r.status.label)}</span></td></tr>`).join('')}</tbody></table></div></div>`;
    tab.querySelectorAll('[data-pvcw-student]').forEach(tr=>tr.onclick=()=>openStudent(tr.dataset.pvcwStudent));
  }

  function detailCriteria(raw, vocal) {
    const v=String(vocal);
    const get=(...keys)=>first(raw,keys);
    return [
      ['Diseño',get(`diseño_vocal${v}`,`diseno_vocal${v}`)],['Construcción',get(`construccion_vocal${v}`)],['Funcionamiento',get(`funcionamiento_vocal${v}`)],['Aplicación',get(`aplicacion_vocal${v}`)],
      ['Sustento marco teórico',get(`sustentoMarcoTeorico_vocal${v}`,`sustentoMarcoTeorico${v}`)],['Sustento propuesta',get(`sustentoPropuesta_vocal${v}`,`sustentoPropuesta${v}`)],['Utilización de recursos',get(`utilizacionRecursos_vocal${v}`,`utilizacionRecursos${v}`)],['Solvencia en preguntas',get(`solvenciaPreguntas_vocal${v}`,`solvenciaPreguntas${v}`)],
    ].filter(([,value])=>String(value??'').trim()!=='');
  }

  function openStudent(id) {
    const row=pvcState.merged.find(r=>r.cedula===id); if(!row)return;
    const req=row.requirement,res=row.result;
    let drawer=$('#pvcw-drawer'); if(!drawer){drawer=document.createElement('div');drawer.id='pvcw-drawer';drawer.className='pvcw-drawer';document.body.appendChild(drawer);}
    drawer.hidden=false;
    const reqMarkup=req?REQUIREMENT_KEYS.map(([key,label])=>`<div><span>${esc(label)}</span><strong class="${truthyRequirement(req[key])?'pvcw-ok':'pvcw-bad'}">${truthyRequirement(req[key])?'✓ Cumple':'Pendiente'}</strong></div>`).join(''):'<div>Sin registro de requisitos</div>';
    const tribunal=res?[1,2,3].map(v=>{const name=res[`vocal${v}`]||'—';const practice=res[`practica${v}`];const defense=res[`defensa${v}`];const criteria=detailCriteria(res.raw,v);return `<tr><td>Vocal ${v}</td><td>${esc(name)}</td><td>${fmt(practice)}</td><td>${fmt(defense)}</td></tr>${criteria.length?`<tr><td colspan="4"><details><summary>Ver detalle del vocal ${v}</summary><div class="pvcw-req">${criteria.map(([l,val])=>`<div><span>${esc(l)}</span><strong>${esc(val)}</strong></div>`).join('')}</div></details></td></tr>`:''}`}).join(''):'';
    drawer.innerHTML=`<aside class="pvcw-sheet"><div class="pvcw-sheet-head"><div><h2>${esc(req?.nombre||res?.nombre||'Estudiante')}</h2><div class="pvcw-muted">${id} · ${esc(req?.codigoCarrera||'')} · ${esc(req?.carrera||'')}</div></div><button class="pvcw-close" id="pvcw-close">Cerrar</button></div><section class="pvcw-section"><h3>1. Información general</h3><div class="pvcw-info"><div><strong>Cédula</strong><br>${id}</div><div><strong>Carrera</strong><br>${esc(req?.carrera||'—')}</div><div><strong>Período fuente</strong><br>${esc(res?.periodoFuente||pvcState.periodLabel||'—')}</div><div><strong>Modalidad</strong><br>${esc(res?.modalidad||'Artículo académico')}</div></div></section><section class="pvcw-section"><h3>2. Requisitos de titulación</h3><div class="pvcw-alert"><strong>Estado de requisitos:</strong> ${req?(req.habilitado?'HABILITADO':`NO HABILITADO · ${req.pending.length} pendientes`):'SIN INFORMACIÓN'}</div><div class="pvcw-req" style="margin-top:8px">${reqMarkup}</div></section><section class="pvcw-section"><h3>3. Trabajo de titulación</h3><div class="pvcw-info"><div><strong>Tutor</strong><br>${esc(res?.tutor||'—')}</div><div><strong>Lector</strong><br>${esc(res?.lector||'—')}</div><div><strong>Acta de grado</strong><br>${esc(res?.acta||'—')}</div><div><strong>Fecha de acta</strong><br>${esc(res?.fechaActa||'—')}</div></div></section><section class="pvcw-section"><h3>4. Tribunal</h3>${res?`<table class="pvcw-tribunal"><thead><tr><th>Rol</th><th>Nombre</th><th>Práctica</th><th>Defensa</th></tr></thead><tbody>${tribunal}</tbody></table>`:'Sin resultado cargado'}</section><section class="pvcw-section"><h3>5. Evaluaciones</h3><div class="pvcw-info"><div><strong>Evaluación tutor</strong><br>${fmt(res?.evaluacionTutor)}</div><div><strong>Evaluación lector</strong><br>${fmt(res?.evaluacionLector)}</div><div><strong>Promedio trabajo escrito</strong><br>${fmt(res?.promedioEscrito)}</div><div><strong>Defensa oral</strong><br>${fmt(res?.defensaOral)}</div><div><strong>Nota trabajo de titulación</strong><br>${fmt(res?.notaFinal)}</div><div><strong>Promedio acumulado</strong><br>${fmt(res?.promedioAcumulado)}</div></div></section><section class="pvcw-section"><div class="pvcw-alert"><strong>Estado automático:</strong> ${esc(row.status.label)}</div></section></aside>`;
    $('#pvcw-close',drawer).onclick=()=>drawer.hidden=true; drawer.onclick=e=>{if(e.target===drawer)drawer.hidden=true;};
  }

  function renderAllPvc() { if(!isPvc())return; injectStyles(); setPvcTabs(); renderControl(); renderStudents(); renderRequirements(); renderResults(); }

  function activateTab(name) {
    const tabs=$('#report-tabs'); if(!tabs)return;
    tabs.querySelectorAll('.tab').forEach(b=>b.classList.toggle('active',b.dataset.tab===name));
    document.querySelectorAll('.tab-content').forEach(c=>c.classList.toggle('active',c.id===`tab-${name}`));
  }

  async function hydrateFromSheets() {
    if (!isPvc() || !window.InformtitSheets) return;
    pvcState.periodId=activePeriodId(); pvcState.periodLabel=($('#report-period')?.textContent||'').trim();
    try {
      const [reqData,workData]=await Promise.all([
        window.InformtitSheets.requisitos ? window.InformtitSheets.requisitos(pvcState.periodId) : window.InformtitSheets.get('requisitos',{periodoId:pvcState.periodId}),
        window.InformtitSheets.trabajoTitulacion(pvcState.periodId),
      ]);
      pvcState.requirements=(reqData.requisitos||[]).map(r=>{const rec={...r,cedula:cedula(r.cedula)};rec.pending=REQUIREMENT_KEYS.filter(([k])=>!truthyRequirement(rec[k])).map(([,l])=>l);rec.habilitado=rec.pending.length===0;return rec;}).filter(r=>r.cedula);
      pvcState.results=(workData.trabajoTitulacion||[]).filter(r=>norm(r.modalidad||r.titulo).includes('ARTICULO')).map(r=>({cedula:cedula(r.cedula),nombre:r.nombre||'',modalidad:r.modalidad||'Artículo académico',tutor:r.tutor||'',lector:r.lector||'',evaluacionTutor:num(r.notaTutor),evaluacionLector:num(r.notaLector),promedioEscrito:num(r.promedioEscrito),defensaOral:num(r.promedioDefensa),notaFinal:num(r.notaFinal),raw:r})).filter(r=>r.cedula);
      rebuildMerged(); renderAllPvc();
    } catch(error) { console.warn('[PVC] No se pudo hidratar desde Sheets:',error); renderAllPvc(); }
  }

  const originalRenderReport=window.renderReport;
  if(typeof originalRenderReport==='function') window.renderReport=async function(...args){const out=await originalRenderReport.apply(this,args);setTimeout(()=>{if(isPvc()){renderAllPvc();hydrateFromSheets();}},80);return out;};
  document.addEventListener('click',e=>{const tab=e.target.closest?.('.tab');if(tab&&isPvc())setTimeout(renderAllPvc,20);});
  const observer=new MutationObserver(()=>{if(isPvc())setPvcTabs();});
  observer.observe(document.body,{childList:true,subtree:true});
})();
