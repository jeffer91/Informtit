(() => {
  'use strict';

  if (!/(^|\.)github\.io$/i.test(window.location.hostname)) return;

  const AUTH_URL = 'https://ep-super-resonance-aveu4z1n.neonauth.c-11.us-east-1.aws.neon.tech/informtit/auth';
  const DATA_API_URL = 'https://ep-super-resonance-aveu4z1n.apirest.c-11.us-east-1.aws.neon.tech/informtit/rest/v1';
  const SDK_URL = 'https://esm.sh/@neondatabase/neon-js@0.7.0-beta?bundle';
  const clean = value => String(value ?? '').replace(/\u00a0/g, ' ').trim().replace(/\s+/g, ' ');
  const digits = value => clean(value).replace(/\D/g, '');
  const now = () => new Date().toISOString();

  let clientInstance = null;
  let accessResolved = false;
  let resolveAccess;
  const accessPromise = new Promise(resolve => { resolveAccess = resolve; });

  async function getClient() {
    if (clientInstance) return clientInstance;
    const mod = await import(SDK_URL);
    if (typeof mod.createClient !== 'function') throw new Error('No se pudo cargar el cliente oficial de Neon.');
    clientInstance = mod.createClient({
      auth: { url: AUTH_URL },
      dataApi: { url: DATA_API_URL },
    });
    return clientInstance;
  }

  function resultData(result, fallback = []) {
    if (result?.error) throw result.error;
    return result?.data ?? fallback;
  }

  async function getSession() {
    const client = await getClient();
    const result = await client.auth.getSession();
    if (result?.error) return null;
    return result?.data ?? result ?? null;
  }

  async function currentMember() {
    const client = await getClient();
    const result = await client.from('app_members').select('user_id,role,active,display_name').limit(1);
    const rows = resultData(result, []);
    return Array.isArray(rows) && rows.length ? rows[0] : null;
  }

  function unlock(member) {
    if (accessResolved) return;
    accessResolved = true;
    resolveAccess(member || true);
    window.dispatchEvent(new CustomEvent('informtit:neon-ready', { detail: { member } }));
  }

  async function requireAccess() {
    if (!accessResolved) await accessPromise;
    return getClient();
  }

  function injectAuthStyles() {
    if (document.getElementById('informtit-neon-auth-style')) return;
    const style = document.createElement('style');
    style.id = 'informtit-neon-auth-style';
    style.textContent = `
      #informtit-neon-auth-gate{position:fixed;inset:0;z-index:100000;background:#eef3f7;display:grid;place-items:center;padding:20px}
      .neon-auth-card{width:min(430px,100%);background:#fff;border:1px solid #dce5ed;border-radius:18px;padding:24px;box-shadow:0 18px 60px rgba(15,23,42,.18);display:grid;gap:14px}
      .neon-auth-card h1{margin:0;font-size:22px}.neon-auth-card p{margin:0;color:#64748b;font-size:13px;line-height:1.45}
      .neon-auth-card label{display:grid;gap:5px;font-size:12px;font-weight:700;color:#334155}.neon-auth-card input{padding:10px 12px;border:1px solid #cbd5e1;border-radius:9px;font:inherit}
      .neon-auth-actions{display:flex;gap:8px;justify-content:flex-end;flex-wrap:wrap}.neon-auth-status{min-height:18px;font-size:12px;color:#64748b}.neon-auth-status.error{color:#b42318}
      .neon-auth-note{padding:10px 12px;border-radius:10px;background:#fff7ed;color:#8a4a00;font-size:12px}
    `;
    document.head.appendChild(style);
  }

  function status(gate, text, error = false) {
    const node = gate.querySelector('#neon-auth-status');
    if (!node) return;
    node.textContent = clean(text);
    node.classList.toggle('error', Boolean(error));
  }

  async function confirmAccess(gate) {
    const member = await currentMember();
    if (member?.active) {
      gate.remove();
      unlock(member);
      return true;
    }
    gate.querySelector('#neon-bootstrap-wrap').hidden = false;
    gate.querySelector('#neon-auth-claim').hidden = false;
    gate.querySelector('#neon-auth-signout').hidden = false;
    gate.querySelector('#neon-auth-signin').hidden = true;
    gate.querySelector('#neon-auth-signup').hidden = true;
    status(gate, 'Cuenta autenticada sin acceso. Si es la primera cuenta de Informtit, use el código de activación inicial.');
    return false;
  }

  function bindGate(gate) {
    const form = gate.querySelector('#informtit-neon-auth-form');
    const signin = gate.querySelector('#neon-auth-signin');
    const signup = gate.querySelector('#neon-auth-signup');
    const claim = gate.querySelector('#neon-auth-claim');
    const signout = gate.querySelector('#neon-auth-signout');

    form.addEventListener('submit', async event => {
      event.preventDefault();
      signin.disabled = true;
      status(gate, 'Ingresando…');
      try {
        const client = await getClient();
        const result = await client.auth.signIn.email({ email: clean(form.email.value).toLowerCase(), password: form.password.value });
        if (result?.error) throw result.error;
        await confirmAccess(gate);
      } catch (error) { status(gate, error?.message || error, true); }
      finally { if (signin.isConnected) signin.disabled = false; }
    });

    signup.addEventListener('click', async () => {
      signup.disabled = true;
      status(gate, 'Creando cuenta…');
      try {
        const email = clean(form.email.value).toLowerCase();
        const password = form.password.value;
        if (!email || !password) throw new Error('Ingrese correo y contraseña.');
        const client = await getClient();
        const result = await client.auth.signUp.email({ email, password, name: email.split('@')[0] || 'Informtit' });
        if (result?.error) throw result.error;
        status(gate, 'Cuenta creada. Verificando acceso…');
        await confirmAccess(gate);
      } catch (error) { status(gate, error?.message || error, true); }
      finally { if (signup.isConnected) signup.disabled = false; }
    });

    claim.addEventListener('click', async () => {
      claim.disabled = true;
      status(gate, 'Activando administrador…');
      try {
        const code = clean(form.bootstrap_code.value);
        if (!code) throw new Error('Ingrese el código de activación.');
        const client = await getClient();
        const result = await client.rpc('claim_first_admin', { p_code: code });
        if (result?.error) throw result.error;
        const member = await currentMember();
        if (!member?.active) throw new Error('No se pudo confirmar el acceso.');
        gate.remove();
        unlock(member);
        location.reload();
      } catch (error) { status(gate, error?.message || error, true); }
      finally { if (claim.isConnected) claim.disabled = false; }
    });

    signout.addEventListener('click', async () => {
      try { const client = await getClient(); await client.auth.signOut(); location.reload(); }
      catch (error) { status(gate, error?.message || error, true); }
    });
  }

  function ensureGate() {
    let gate = document.getElementById('informtit-neon-auth-gate');
    if (gate) return gate;
    injectAuthStyles();
    gate = document.createElement('div');
    gate.id = 'informtit-neon-auth-gate';
    gate.innerHTML = `<form class="neon-auth-card" id="informtit-neon-auth-form">
      <div><h1>Informtit</h1><p>Acceso institucional · Neon PostgreSQL</p></div>
      <label>Correo<input type="email" name="email" autocomplete="email" required></label>
      <label>Contraseña<input type="password" name="password" autocomplete="current-password" minlength="8" required></label>
      <label id="neon-bootstrap-wrap" hidden>Código de activación<input type="text" name="bootstrap_code" autocomplete="off"></label>
      <div class="neon-auth-note">Los datos académicos se almacenan de forma compartida en Neon. La primera cuenta debe activar el administrador inicial.</div>
      <div class="neon-auth-status" id="neon-auth-status"></div>
      <div class="neon-auth-actions">
        <button type="button" class="button secondary" id="neon-auth-signup">Crear cuenta</button>
        <button type="button" class="button secondary" id="neon-auth-signout" hidden>Salir</button>
        <button type="submit" class="button primary" id="neon-auth-signin">Ingresar</button>
        <button type="button" class="button primary" id="neon-auth-claim" hidden>Activar administrador</button>
      </div>
    </form>`;
    document.body.appendChild(gate);
    bindGate(gate);
    return gate;
  }

  async function initializeAuth() {
    if (!document.body) await new Promise(resolve => document.addEventListener('DOMContentLoaded', resolve, { once:true }));
    const gate = ensureGate();
    status(gate, 'Verificando sesión…');
    try {
      const session = await getSession();
      const user = session?.user || session?.session?.user || session?.data?.user;
      if (user) await confirmAccess(gate);
      else status(gate, 'Ingrese con su cuenta de Informtit.');
    } catch (error) {
      status(gate, `No se pudo iniciar Neon: ${clean(error?.message || error)}`, true);
    }
  }

  async function rowsFor(table, select = '*', apply = null) {
    const client = await requireAccess();
    let query = client.from(table).select(select);
    if (typeof apply === 'function') query = apply(query);
    return resultData(await query, []);
  }

  async function studentMap(studentIds = []) {
    const ids = [...new Set(studentIds.map(Number).filter(Number.isFinite))];
    if (!ids.length) return new Map();
    const rows = await rowsFor('students', 'id,identification,full_name,personal_email,institutional_email,phone', q => q.in('id', ids));
    return new Map(rows.map(row => [Number(row.id), row]));
  }

  function periodParts(id) {
    const match = /^(\d{4})-(\d{2})_(\d{4})-(\d{2})$/.exec(clean(id));
    return match ? { start_year:Number(match[1]), start_month:Number(match[2]), end_year:Number(match[3]), end_month:Number(match[4]) } : {};
  }

  function periodLabel(id) {
    const months = ['','Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'];
    const p = periodParts(id);
    return p.start_month ? `${months[p.start_month]} ${p.start_year} - ${months[p.end_month]} ${p.end_year}` : id;
  }

  async function periodos() {
    const rows = await rowsFor('periods', '*', q => q.order('start_year',{ascending:false}).order('start_month',{ascending:false}));
    return { ok:true, periodos:rows.map(row => ({ periodoId:row.id,id:row.id,nombre:row.name,label:row.name,estado:row.status,activo:row.is_active,mesInicio:row.start_month,anioInicio:row.start_year,mesFin:row.end_month,anioFin:row.end_year })) };
  }

  async function estudiantes() {
    const rows = await rowsFor('students');
    return { ok:true, estudiantes:rows.map(row => ({ cedula:row.identification,identificacion:row.identification,nombre:row.full_name,correoPersonal:row.personal_email,correoInstitucional:row.institutional_email,celular:row.phone,source:'NEON' })) };
  }

  async function matriculas(periodoId) {
    const rows = await rowsFor('enrollments', '*', q => q.eq('period_id',periodoId));
    const map = await studentMap(rows.map(row => row.student_id));
    return { ok:true, matriculas:rows.map(row => { const s=map.get(Number(row.student_id))||{}; return { cedula:s.identification||'',identificacion:s.identification||'',nombre:s.full_name||'',codigoCarrera:row.career_code,carrera:row.career_name,nombreCarrera:row.career_name,modalidad:row.modality,sede:row.campus,jornada:row.shift,retirado:false,route:row.titulation_route||'UNDEFINED',source:'NEON' }; }) };
  }

  async function requisitos(periodoId) {
    const rows = await rowsFor('requirements','*',q=>q.eq('period_id',periodoId));
    const map = await studentMap(rows.map(row=>row.student_id));
    return {ok:true,requisitos:rows.map(row=>({cedula:map.get(Number(row.student_id))?.identification||'',academico:row.academic_status,documentacion:row.documentation_status,financiero:row.financial_status,titulacion:row.titulation_status,practicas:row.practices_linkage_status,vinculacion:row.linkage_status,seguimientoGraduados:row.graduate_followup_status,ingles:row.english_status,actualizacionDatos:row.data_update_status,aprobacionTitulacion:row.titulation_approval,aprobacionComplexivo:row.complexive_approval,source:'NEON'}))};
  }

  async function nucleos(periodoId) {
    const rows=await rowsFor('nuclei_results','*',q=>q.eq('period_id',periodoId)); const map=await studentMap(rows.map(row=>row.student_id));
    return {ok:true,nucleos:rows.map(row=>{const s=map.get(Number(row.student_id))||{};return{cedula:s.identification||'',nombre:s.full_name||'',carrera:row.career_name,nucleo:row.nucleus_number,curso:row.course_name,notaFinal:row.grade,estado:row.final_status,source:'NEON'};})};
  }

  async function complexivo(periodoId) {
    const rows=await rowsFor('complexive_results','*',q=>q.eq('period_id',periodoId)); const map=await studentMap(rows.map(row=>row.student_id));
    return {ok:true,complexivo:rows.map(row=>{const s=map.get(Number(row.student_id))||{};return{cedula:s.identification||'',nombre:s.full_name||'',notaTeorico:row.theoretical_grade,notaPractico:row.practical_grade,notaSupletorio:row.supplementary_theoretical??row.supplementary_practical,notaFinal:row.final_grade,estado:row.final_status,source:'NEON'};})};
  }

  async function trabajoTitulacion(periodoId) {
    const rows=await rowsFor('thesis_results','*',q=>q.eq('period_id',periodoId)); const map=await studentMap(rows.map(row=>row.student_id));
    return {ok:true,trabajoTitulacion:rows.map(row=>{const s=map.get(Number(row.student_id))||{};return{cedula:s.identification||'',nombre:s.full_name||'',titulo:row.title,tutor:row.tutor,notaFinal:row.final_grade,estado:row.final_status,source:'NEON'};})};
  }

  async function informes(periodoId) {
    const rows=await rowsFor('reports','*',q=>q.eq('period_id',periodoId));
    return {ok:true,informes:rows.map(row=>({...row,periodoId:row.period_id,firebase_period_id:row.period_id,document_config:row.document_config,document_config_json:JSON.stringify(row.document_config||{}),storage_mode:'neon_shared'}))};
  }

  async function ensurePeriod(periodoId, name = '') {
    const id=clean(periodoId); if(!id) throw new Error('Período requerido.');
    const existing=await rowsFor('periods','id,name',q=>q.eq('id',id).limit(1));
    if(existing.length) return existing[0];
    return (await guardarPeriodo({periodoId:id,nombre:name||periodLabel(id),estado:'ACTIVE',activo:true})).period;
  }

  async function guardarPeriodo(data={}) {
    const client=await requireAccess(); const id=clean(data.periodoId||data.id); if(!id) throw new Error('Período requerido.');
    const p=periodParts(id); let state=clean(data.estado||data.status||'ACTIVE').toUpperCase();
    if(state==='ACTIVO')state='ACTIVE'; if(state==='CERRADO')state='CLOSED'; if(state==='ARCHIVADO')state='ARCHIVED';
    if(!['ACTIVE','CLOSED','ARCHIVED'].includes(state))state='ACTIVE';
    const payload={id,name:clean(data.nombre||data.name||data.label||periodLabel(id)),start_month:Number(data.mesInicio||data.start_month||p.start_month),start_year:Number(data.anioInicio||data.start_year||p.start_year),end_month:Number(data.mesFin||data.end_month||p.end_month),end_year:Number(data.anioFin||data.end_year||p.end_year),status:state,is_active:Boolean(data.activo??data.is_active??(state==='ACTIVE')),updated_at:now()};
    const result=await client.from('periods').upsert(payload,{onConflict:'id'}).select();
    return {ok:true,period:resultData(result,[payload])[0]||payload,source:'NEON'};
  }

  async function guardarInforme(data={}) {
    const client=await requireAccess(); const periodId=clean(data.periodoId||data.period_id||data.firebase_period_id); if(!periodId) throw new Error('Período requerido para el informe.');
    await ensurePeriod(periodId,clean(data.period||data.periodo));
    const type=clean(data.report_type||data.tipo).toLowerCase()==='pvc'?'pvc':'normal';
    if(data.deleted===true||['ELIMINADO','DELETED'].includes(clean(data.status).toUpperCase())){
      const deleted=await client.from('reports').delete().eq('period_id',periodId).eq('report_type',type); if(deleted?.error)throw deleted.error; return {ok:true,deleted:true,source:'NEON'};
    }
    let config=data.document_config||data.documentConfig||data.document_config_json||{}; if(typeof config==='string'){try{config=JSON.parse(config);}catch(_){config={};}}
    let state=clean(data.status).toUpperCase(); if(!['DRAFT','READY','FINAL','ARCHIVED'].includes(state))state='DRAFT';
    const payload={period_id:periodId,report_type:type,name:clean(data.name||data.nombre||(type==='pvc'?'Informe PVC':'Informe Final del Proceso de Titulación')),status:state,code:clean(data.code),code_presencial:clean(data.code_presencial),code_online:clean(data.code_online),version:clean(data.version||'1.0'),elaboration_date:clean(data.elaboration_date)||null,prepared_by:clean(data.prepared_by),prepared_role:clean(data.prepared_role),reviewed_by:clean(data.reviewed_by),reviewed_role:clean(data.reviewed_role),approved_by:clean(data.approved_by),approved_role:clean(data.approved_role),document_config:config,updated_at:now()};
    const result=await client.from('reports').upsert(payload,{onConflict:'period_id,report_type'}).select();
    return {ok:true,report:resultData(result,[payload])[0]||payload,source:'NEON'};
  }

  async function findOrCreateStudent(data={}) {
    const client=await requireAccess(); const identification=digits(data.cedula||data.identificacion||data.identification); if(!identification)throw new Error('Cédula requerida.');
    let rows=await rowsFor('students','id,identification',q=>q.eq('identification',identification).limit(1)); if(rows.length)return rows[0];
    const result=await client.from('students').insert({identification,full_name:clean(data.nombre||data.full_name||identification),personal_email:clean(data.correoPersonal).toLowerCase(),institutional_email:clean(data.correoInstitucional||data.correo).toLowerCase(),phone:clean(data.celular||data.telefono),source:'NEON_IMPORT',raw_data:data}).select('id,identification');
    rows=resultData(result,[]); return rows[0];
  }

  async function ensureEnrollment(periodId,student,data={},route='UNDEFINED') {
    const client=await requireAccess(); await ensurePeriod(periodId);
    const payload={period_id:periodId,student_id:Number(student.id),career_code:clean(data.codigoCarrera),career_name:clean(data.carrera||data.career_name),modality:['presencial','en_linea','otra'].includes(clean(data.modalidad))?clean(data.modalidad):'otra',campus:clean(data.sede),shift:clean(data.jornada),titulation_route:route,source:'NEON_IMPORT',raw_data:data,updated_at:now()};
    const result=await client.from('enrollments').upsert(payload,{onConflict:'period_id,student_id'}).select(); resultData(result,[]); return payload;
  }

  async function guardarRequisito(data={}) {
    const client=await requireAccess(); const periodId=clean(data.periodoId); const student=await findOrCreateStudent(data); await ensureEnrollment(periodId,student,data);
    const payload={period_id:periodId,student_id:Number(student.id),academic_status:clean(data.academico),documentation_status:clean(data.documentacion),financial_status:clean(data.financiero),titulation_status:clean(data.titulacion),practices_linkage_status:clean(data.practicas),linkage_status:clean(data.vinculacion),graduate_followup_status:clean(data.seguimientoGraduados),english_status:clean(data.ingles),data_update_status:clean(data.actualizacionDatos),titulation_approval:clean(data.aprobacionTitulacion),complexive_approval:clean(data.aprobacionComplexivo),source:'NEON_IMPORT',raw_data:data,updated_at:now()};
    const result=await client.from('requirements').upsert(payload,{onConflict:'period_id,student_id'}).select(); return {ok:true,requisito:resultData(result,[payload])[0]||payload,source:'NEON'};
  }

  async function guardarNucleo(data={}) {
    const client=await requireAccess(); const periodId=clean(data.periodoId),student=await findOrCreateStudent(data); await ensureEnrollment(periodId,student,data,'COMPLEXIVO');
    const payload={period_id:periodId,student_id:Number(student.id),nucleus_number:Number(data.nucleo||data.nucleus_number),career_name:clean(data.carrera),course_name:clean(data.curso||`Núcleo ${data.nucleo||''}`),grade:data.notaFinal===''||data.notaFinal==null?null:Number(data.notaFinal),final_status:clean(data.estado),source:'NEON_IMPORT',raw_data:data,updated_at:now()};
    const result=await client.from('nuclei_results').upsert(payload,{onConflict:'period_id,student_id,nucleus_number'}).select(); return {ok:true,nucleo:resultData(result,[payload])[0]||payload,source:'NEON'};
  }

  async function guardarComplexivo(data={}) {
    const client=await requireAccess(); const periodId=clean(data.periodoId),student=await findOrCreateStudent(data); await ensureEnrollment(periodId,student,data,'COMPLEXIVO'); const n=v=>v===''||v==null?null:Number(v);
    const payload={period_id:periodId,student_id:Number(student.id),theoretical_grade:n(data.notaTeorico??data.theoretical_grade),practical_grade:n(data.notaPractico??data.practical_grade),supplementary_theoretical:n(data.notaSupletorio??data.supplementary_theoretical),supplementary_practical:n(data.supplementary_practical),final_grade:n(data.notaFinal??data.final_grade),final_status:clean(data.estado||data.final_status),source:'NEON_IMPORT',raw_data:data,updated_at:now()};
    const result=await client.from('complexive_results').upsert(payload,{onConflict:'period_id,student_id'}).select(); return {ok:true,complexivo:resultData(result,[payload])[0]||payload,source:'NEON'};
  }

  async function guardarTrabajoTitulacion(data={}) {
    const client=await requireAccess(); const periodId=clean(data.periodoId),student=await findOrCreateStudent(data); await ensureEnrollment(periodId,student,data,'TRABAJO_TITULACION');
    const payload={period_id:periodId,student_id:Number(student.id),title:clean(data.titulo||data.title),tutor:clean(data.tutor),final_grade:data.notaFinal===''||data.notaFinal==null?null:Number(data.notaFinal??data.final_grade),final_status:clean(data.estado||data.final_status),source:'NEON_IMPORT',raw_data:data,updated_at:now()};
    const result=await client.from('thesis_results').upsert(payload,{onConflict:'period_id,student_id'}).select(); return {ok:true,trabajo:resultData(result,[payload])[0]||payload,source:'NEON'};
  }

  async function postMany(items=[],options={}) {
    const queue=Array.from(items),results=new Array(queue.length);let cursor=0,completed=0;const concurrency=Math.max(1,Math.min(8,Number(options.concurrency||4)));
    const handlers={guardar_requisito:guardarRequisito,guardar_nucleo:guardarNucleo,guardar_complexivo:guardarComplexivo,guardar_trabajo_titulacion:guardarTrabajoTitulacion};
    async function worker(){while(true){const index=cursor++;if(index>=queue.length)return;const item=queue[index];try{const fn=handlers[item.action];if(!fn)throw new Error(`Acción Neon no soportada: ${item.action}`);results[index]={ok:true,result:await fn(item.data),item};}catch(error){results[index]={ok:false,error:clean(error?.message||error),item};}completed+=1;if(typeof options.onProgress==='function')options.onProgress(completed,queue.length,results[index]);}}
    await Promise.all(Array.from({length:concurrency},()=>worker()));return results;
  }

  async function bulkUpsertStudentsRequirements(rows,periodId,fileName='',onProgress=null) {
    const client=await requireAccess();const source=Array.isArray(rows)?rows.filter(row=>digits(row.cedula)):[];if(!source.length)return{ok:true,total:0,inserted:0,updated:0,source:'NEON'};
    const progress=(done,label)=>{if(typeof onProgress==='function')onProgress(done,source.length,label);};
    await ensurePeriod(periodId);progress(Math.ceil(source.length*.05),'Período verificado');
    const existing=await rowsFor('students','id,identification',q=>q.in('identification',source.map(row=>digits(row.cedula))));const beforeIds=new Set(existing.map(row=>digits(row.identification)));
    const studentPayload=source.map(row=>({identification:digits(row.cedula),full_name:clean(row.nombre||row.cedula),personal_email:clean(row.correoPersonal).toLowerCase(),institutional_email:clean(row.correoInstitucional).toLowerCase(),phone:clean(row.celular),source:'IMPORT',raw_data:row,updated_at:now()}));
    let result=await client.from('students').upsert(studentPayload,{onConflict:'identification'}).select('id,identification');const students=resultData(result,[]);const idMap=new Map(students.map(row=>[digits(row.identification),Number(row.id)]));progress(Math.ceil(source.length*.35),'Estudiantes guardados');
    if(idMap.size<source.length){const all=await rowsFor('students','id,identification',q=>q.in('identification',source.map(row=>digits(row.cedula))));all.forEach(row=>idMap.set(digits(row.identification),Number(row.id)));}
    const enrollmentPayload=source.map(row=>({period_id:periodId,student_id:idMap.get(digits(row.cedula)),career_code:clean(row.codigoCarrera),career_name:clean(row.carrera),modality:['presencial','en_linea','otra'].includes(row.modalidad)?row.modalidad:'otra',campus:clean(row.sede),shift:clean(row.jornada),source:'IMPORT',raw_data:row,updated_at:now()})).filter(row=>row.student_id);
    result=await client.from('enrollments').upsert(enrollmentPayload,{onConflict:'period_id,student_id'}).select('student_id');resultData(result,[]);progress(Math.ceil(source.length*.62),'Matrículas guardadas');
    const reqPayload=source.map(row=>({period_id:periodId,student_id:idMap.get(digits(row.cedula)),academic_status:clean(row.academico),documentation_status:clean(row.documentacion),financial_status:clean(row.financiero),titulation_status:clean(row.titulacion),practices_linkage_status:clean(row.practicas),linkage_status:clean(row.vinculacion),graduate_followup_status:clean(row.seguimientoGraduados),english_status:clean(row.ingles),data_update_status:clean(row.actualizacionDatos),titulation_approval:clean(row.aprobacionTitulacion),complexive_approval:clean(row.aprobacionComplexivo),source:'IMPORT',source_file:clean(fileName),raw_data:row,updated_at:now()})).filter(row=>row.student_id);
    result=await client.from('requirements').upsert(reqPayload,{onConflict:'period_id,student_id'}).select('student_id');resultData(result,[]);progress(Math.ceil(source.length*.9),'Requisitos guardados');
    const inserted=source.filter(row=>!beforeIds.has(digits(row.cedula))).length,updated=source.length-inserted;
    await client.from('import_batches').insert({period_id:periodId,import_type:'STUDENTS_REQUIREMENTS',file_name:clean(fileName),total_rows:source.length,inserted_rows:inserted,updated_rows:updated,failed_rows:0,status:'COMPLETED',details:{provider:'NEON'},finished_at:now()});
    await client.from('audit_log').insert({period_id:periodId,entity_type:'IMPORT_BATCH',entity_key:clean(fileName),action:'BULK_UPSERT_STUDENTS_REQUIREMENTS',payload:{total:source.length,inserted,updated,provider:'NEON'}});
    progress(source.length,'Completado');return{ok:true,total:source.length,inserted,updated,source:'NEON'};
  }

  async function schedules(periodId) {
    const rows=await rowsFor('schedules','*',q=>q.eq('period_id',periodId).order('sort_order',{ascending:true}));const out={complexive:[],thesis:[]};
    rows.forEach(row=>{const key=row.process_type==='trabajo_titulacion'?'thesis':row.process_type==='complexivo'?'complexive':'';if(key)out[key].push({id:row.id,activity:row.activity,start_date:row.start_date,end_date:row.end_date,notes:row.notes,sort_order:row.sort_order});});
    return{ok:true,schedules:out,source:'NEON',synced_at:now()};
  }

  async function saveSchedule(periodId,type,entries=[]) {
    const client=await requireAccess();await ensurePeriod(periodId);const processType=type==='thesis'?'trabajo_titulacion':'complexivo';
    const removed=await client.from('schedules').delete().eq('period_id',periodId).eq('process_type',processType);if(removed?.error)throw removed.error;
    const payload=(Array.isArray(entries)?entries:[]).map((entry,index)=>({period_id:periodId,process_type:processType,activity:clean(entry.activity||entry.actividad||entry.name||entry.nombre||'Actividad'),start_date:clean(entry.start_date||entry.fecha_inicio||entry.start||entry.inicio)||null,end_date:clean(entry.end_date||entry.fecha_fin||entry.end||entry.fin)||null,sort_order:index+1,notes:clean(entry.notes||entry.observaciones),source:'MANUAL'}));
    if(payload.length){const inserted=await client.from('schedules').insert(payload).select();resultData(inserted,[]);}return{ok:true,count:payload.length,source:'NEON'};
  }

  window.InformtitNeon=Object.freeze({authUrl:AUTH_URL,dataApiUrl:DATA_API_URL,getClient,getSession,currentMember,requireAccess,bulkUpsertStudentsRequirements,schedules,saveSchedule,provider:'NEON',version:'1.1.0'});
  window.InformtitSheets={baseUrl:DATA_API_URL,provider:'NEON',ping:async()=>{await requireAccess();return{ok:true,provider:'NEON'};},periodos,estudiantes,matriculas,requisitos,nucleos,complexivo,trabajoTitulacion,informes,guardarPeriodo,guardarInforme,guardarRequisito,guardarNucleo,guardarComplexivo,guardarTrabajoTitulacion,postMany};

  initializeAuth();
})();