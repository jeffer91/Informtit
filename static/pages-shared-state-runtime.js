(() => {
  'use strict';

  if (!/(^|\.)github\.io$/i.test(window.location.hostname)) return;
  if (!window.InformtitSheets || window.InformtitSheets.provider !== 'NEON') return;

  const REPORTS_KEY = 'informtit.githubPages.reports.v1';
  const previousFetch = window.fetch.bind(window);
  let selectedPeriodId = '';

  const clean = value => String(value ?? '').replace(/\u00a0/g, ' ').trim().replace(/\s+/g, ' ');
  const fold = value => clean(value).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toUpperCase();
  const canonicalPeriodId = value => {
    const raw = clean(value);
    const match = /^(\d{4})-(\d{2})_+(\d{4})-(\d{2})$/.exec(raw);
    return match ? `${match[1]}-${match[2]}_${match[3]}-${match[4]}` : raw;
  };
  const pathOf = input => {
    try { return new URL(typeof input === 'string' ? input : input?.url, window.location.href).pathname; }
    catch (_) { return ''; }
  };
  const methodOf = (input, init) => String(init?.method || input?.method || 'GET').toUpperCase();

  async function bodyOf(input, init) {
    if (typeof init?.body === 'string') { try { return JSON.parse(init.body); } catch (_) { return {}; } }
    if (typeof Request !== 'undefined' && input instanceof Request) { try { return await input.clone().json(); } catch (_) {} }
    return {};
  }
  function jsonResponse(payload, status = 200) {
    return Promise.resolve(new Response(JSON.stringify(payload), { status, headers: { 'Content-Type': 'application/json; charset=utf-8' } }));
  }
  function readLocalReports() {
    try { const rows=JSON.parse(localStorage.getItem(REPORTS_KEY)||'[]'); return Array.isArray(rows)?rows:[]; }
    catch (_) { return []; }
  }
  function writeLocalReports(rows) {
    try { localStorage.setItem(REPORTS_KEY, JSON.stringify(Array.isArray(rows)?rows:[])); } catch (_) {}
  }
  function stableId(value) {
    let hash=2166136261; for(const ch of clean(value)){hash^=ch.charCodeAt(0);hash=Math.imul(hash,16777619);} return Math.abs(hash>>>0)||Date.now();
  }
  function reportType(row) { return clean(row?.report_type||row?.tipo||row?.type).toLowerCase()==='pvc'?'pvc':'normal'; }
  function periodIdOf(row) { return canonicalPeriodId(row?.periodoId||row?.firebase_period_id||row?.period_id||row?.periodId||''); }
  function reportKey(row) { return `${periodIdOf(row)||fold(row?.period||row?.periodo||'')}::${reportType(row)}`; }
  function normalizeSharedReport(raw={}) {
    const periodId=periodIdOf(raw), type=reportType(raw), id=Number(raw.id||raw.reportId||raw.report_id)||stableId(`${periodId}:${type}`);
    return {
      ...raw,id,report_type:type,periodoId:periodId,firebase_period_id:periodId,
      period:clean(raw.period||raw.periodo||raw.periodName||raw.nombrePeriodo),
      name:clean(raw.name||raw.nombre||raw.title)||(type==='pvc'?'Informe PVC':'Informe Final del Proceso de Titulación'),
      code:clean(raw.code||raw.codigo||raw.code_presencial),code_presencial:clean(raw.code_presencial||raw.code||raw.codigo),code_online:clean(raw.code_online||raw.codigo_online),
      version:clean(raw.version||raw.versionDocumento)||'1.0',status:clean(raw.status||raw.estado)||'DRAFT',
      created_at:clean(raw.created_at||raw.createdAt||raw.fechaCreacion),updated_at:clean(raw.updated_at||raw.updatedAt||raw.fechaActualizacion),
      careers:Array.isArray(raw.careers)?raw.careers:[],images:Array.isArray(raw.images)?raw.images:[],sections:Array.isArray(raw.sections)?raw.sections:[],
      legacy_report_ids:Array.isArray(raw.legacy_report_ids)?raw.legacy_report_ids:[id],storage_mode:'neon_shared'
    };
  }
  function mergeReports(localRows, sharedRows) {
    const map=new Map();
    (localRows||[]).forEach(row=>map.set(reportKey(row),row));
    (sharedRows||[]).forEach(raw=>{
      const shared=normalizeSharedReport(raw); if(!periodIdOf(shared)||['ELIMINADO','DELETED'].includes(fold(shared.status)))return;
      const key=reportKey(shared), local=map.get(key)||{};
      map.set(key,{...local,...shared,careers:shared.careers.length?shared.careers:(Array.isArray(local.careers)?local.careers:[]),images:shared.images.length?shared.images:(Array.isArray(local.images)?local.images:[]),sections:shared.sections.length?shared.sections:(Array.isArray(local.sections)?local.sections:[]),legacy_report_ids:[...new Set([...(local.legacy_report_ids||[]),...(shared.legacy_report_ids||[]),local.id,shared.id].filter(Boolean).map(Number))]});
    });
    return [...map.values()].sort((a,b)=>clean(b.updated_at).localeCompare(clean(a.updated_at)));
  }

  async function loadSharedReports(periodId = selectedPeriodId) {
    const id=canonicalPeriodId(periodId);
    if(!id) return [];
    const payload=await window.InformtitSheets.informes(id);
    const rows=Array.isArray(payload?.informes)?payload.informes:Array.isArray(payload?.reports)?payload.reports:Array.isArray(payload?.rows)?payload.rows:[];
    return rows.map(row=>({...row,periodoId:periodIdOf(row)||id}));
  }
  function reportPayload(report, extra={}) {
    const periodId=periodIdOf(report);
    return {reportId:Number(report.id||report.reportId||0)||undefined,id:Number(report.id||report.reportId||0)||undefined,periodoId:periodId,report_type:reportType(report),tipo:reportType(report),name:clean(report.name||report.nombre),nombre:clean(report.name||report.nombre),period:clean(report.period||report.periodo),periodo:clean(report.period||report.periodo),code:clean(report.code||report.code_presencial),code_presencial:clean(report.code_presencial||report.code),code_online:clean(report.code_online),version:clean(report.version)||'1.0',elaboration_date:clean(report.elaboration_date),prepared_by:clean(report.prepared_by),prepared_role:clean(report.prepared_role),reviewed_by:clean(report.reviewed_by),reviewed_role:clean(report.reviewed_role),approved_by:clean(report.approved_by),approved_role:clean(report.approved_role),status:clean(report.status)||'DRAFT',updatedAt:new Date().toISOString(),...extra};
  }
  async function persistPeriod(period) {
    if(!period)return null;
    const periodId=canonicalPeriodId(period.id||period.periodoId||period.sourceId); if(!periodId)throw new Error('Período requerido.');
    const match=/^(\d{4})-(\d{2})_(\d{4})-(\d{2})$/.exec(periodId);
    return window.InformtitSheets.guardarPeriodo({periodoId:periodId,id:periodId,nombre:clean(period.name||period.nombre||period.label||periodId),label:clean(period.name||period.nombre||period.label||periodId),anioInicio:match?Number(match[1]):undefined,mesInicio:match?Number(match[2]):undefined,anioFin:match?Number(match[3]):undefined,mesFin:match?Number(match[4]):undefined,estado:'ACTIVE',activo:true,updatedAt:new Date().toISOString()});
  }
  async function deleteSharedReport(report) {
    if(!report)return;
    if(window.InformtitNeon?.getClient){const client=await window.InformtitNeon.getClient();const result=await client.from('reports').delete().eq('period_id',periodIdOf(report)).eq('report_type',reportType(report));if(result?.error)throw result.error;return;}
    await window.InformtitSheets.guardarInforme(reportPayload(report,{status:'ELIMINADO',deleted:true}));
  }

  document.addEventListener('informtit:period-changed',event=>{selectedPeriodId=canonicalPeriodId(event.detail?.id||event.detail?.periodoId||event.detail?.sourceId);});
  document.addEventListener('informtit:period-cleared',()=>{selectedPeriodId='';});

  window.fetch=async function pagesSharedStateFetch(input,init={}){
    const path=pathOf(input),method=methodOf(input,init);
    if(path==='/api/reports'&&method==='GET'){
      const response=await previousFetch(input,init);const payload=await response.clone().json().catch(()=>({}));
      if(!response.ok||payload?.ok===false)return response;
      if(!selectedPeriodId)return jsonResponse({...payload,reports:[],storage:'Neon PostgreSQL · seleccione un período'},response.status);
      try{
        const shared=await loadSharedReports(selectedPeriodId);
        const local=(payload.reports||readLocalReports()).filter(row=>periodIdOf(row)===selectedPeriodId);
        const merged=mergeReports(local,shared);
        const others=readLocalReports().filter(row=>periodIdOf(row)!==selectedPeriodId);
        writeLocalReports([...others,...merged]);
        return jsonResponse({...payload,reports:merged,storage:'Neon PostgreSQL'},response.status);
      }catch(error){return jsonResponse({ok:false,error:`No se pudo cargar el período desde Neon: ${clean(error?.message||error)}`},502);}
    }
    if(path==='/api/reports'&&method==='POST'){
      if(!selectedPeriodId)return jsonResponse({ok:false,error:'Seleccione un período antes de crear documentos.'},409);
      const before=readLocalReports(),response=await previousFetch(input,init),payload=await response.clone().json().catch(()=>({}));
      if(!response.ok||payload?.ok===false)return response;
      const created=payload?.reports?.[0]||readLocalReports().find(row=>Number(row.id)===Number(payload.report_id));
      try{if(!created)throw new Error('No se pudo identificar el informe creado.');await window.InformtitSheets.guardarInforme(reportPayload(created));return jsonResponse({...payload,storage:'neon_shared'},response.status);}catch(error){writeLocalReports(before);return jsonResponse({ok:false,error:`No se guardó el informe en Neon: ${clean(error?.message||error)}`},502);}
    }
    let match=path.match(/^\/api\/reports\/(\d+)$/);
    if(match&&method==='PUT'){
      const before=readLocalReports(),response=await previousFetch(input,init),payload=await response.clone().json().catch(()=>({}));
      if(!response.ok||payload?.ok===false)return response;
      try{if(!payload.report)throw new Error('No se pudo identificar el informe actualizado.');await window.InformtitSheets.guardarInforme(reportPayload(payload.report));return jsonResponse({...payload,storage:'neon_shared'},response.status);}catch(error){writeLocalReports(before);return jsonResponse({ok:false,error:`No se guardaron los cambios en Neon: ${clean(error?.message||error)}`},502);}
    }
    if(match&&method==='DELETE'){
      const before=readLocalReports(),target=before.find(row=>Number(row.id)===Number(match[1])||(row.legacy_report_ids||[]).some(id=>Number(id)===Number(match[1]))),response=await previousFetch(input,init),payload=await response.clone().json().catch(()=>({}));
      if(!response.ok||payload?.ok===false)return response;
      try{if(target)await deleteSharedReport(target);return response;}catch(error){writeLocalReports(before);return jsonResponse({ok:false,error:`No se pudo eliminar el informe de Neon: ${clean(error?.message||error)}`},502);}
    }
    return previousFetch(input,init);
  };

  window.InformtitSharedState=Object.freeze({loadSharedReports,mergeReports,persistPeriod,get selectedPeriodId(){return selectedPeriodId;},version:'3.0.0',provider:'NEON',standard:'SVD_2_1'});
})();