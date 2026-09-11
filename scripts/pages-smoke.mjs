import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';

class LocalStorageMock {
  constructor() { this.map = new Map(); }
  getItem(key) { return this.map.has(key) ? this.map.get(key) : null; }
  setItem(key, value) { this.map.set(key, String(value)); }
  removeItem(key) { this.map.delete(key); }
}

const localStorage = new LocalStorageMock();
const report = {
  id: 1,
  name: 'Informe Final del Proceso de Titulación',
  period: 'Abril 2026 - Septiembre 2026',
  periodoId: '2026-04_2026-09',
  firebase_period_id: '2026-04_2026-09',
  code: 'UTET-INF-01-PRO-95-2026-09',
  code_online: 'UTET-INF-02-PRO-95-2026-09',
  version: '1.0',
  report_type: 'normal',
  images: [],
  careers: [{name:'ENFERMERÍA',students:[{full_name:'Ana Prueba',identification:'0101',final_status:'Aprobado',final_grade:9,modality:'presencial'}]}],
  complexive_records: 1,
};
localStorage.setItem('informtit.githubPages.reports.v1', JSON.stringify([report]));

function json(payload, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(payload), {status, headers:{'Content-Type':'application/json'}}));
}

async function mockFetch(input) {
  const raw = typeof input === 'string' ? input : input?.url;
  const path = new URL(raw, 'https://jeffer91.github.io/Informtit/').pathname;
  if (path === '/api/reports/1') return json({ok:true, report});
  if (path === '/api/reports/1/roster') return json({
    ok:true,
    summary:{students:1,careers:1,requirements_complete:1,requirements_pending:0,presencial:1,online:0},
    requirements:[{label:'Académico',complies:1,does_not_comply:0}],
    careers:[{name:'ENFERMERÍA',students:1}],
    students:[{identification:'0101',full_name:'Ana Prueba',career_name:'ENFERMERÍA',modality:'presencial',route:'COMPLEXIVO',has_nuclei:true}],
    source:'GOOGLE_SHEETS',synced_at:'2026-09-11T12:00:00Z'
  });
  if (path === '/api/reports/1/students-domain') return json({ok:true,students:[]});
  if (path === '/api/reports/1/nuclei') return json({ok:true,courses:[{career_name:'ENFERMERÍA',nucleus_number:1,course_average:9,students:[{modality:'presencial'}]}]});
  if (path === '/api/reports/1/projects') return json({ok:true,projects:[]});
  if (path === '/api/reports/1/schedules') return json({ok:true,schedules:{complexive:[],thesis:[]}});
  return json({ok:false,error:`Unhandled ${path}`},404);
}

globalThis.Element = class Element {};
globalThis.document = { addEventListener() {} };
globalThis.window = {
  location: {hostname:'jeffer91.github.io',href:'https://jeffer91.github.io/Informtit/'},
  fetch: mockFetch,
  localStorage,
};
globalThis.localStorage = localStorage;
globalThis.location = window.location;

const runtimePath = process.argv[2] || new URL('../static/pages-browser-services.js', import.meta.url).pathname;
const source = fs.readFileSync(runtimePath, 'utf8');
vm.runInThisContext(source, {filename: runtimePath});

let response = await window.fetch('/api/health');
assert.equal(response.ok, true);
assert.equal((await response.json()).database, 'Google Sheets');

response = await window.fetch('/api/reports/1/audit');
const auditPayload = await response.json();
assert.equal(auditPayload.ok, true);
assert.equal(auditPayload.audit.can_generate_pdf, true);

const imagePayload = {data_url:'data:image/png;base64,aGVsbG8=',original_name:'evidencia.png',title:'Evidencia',section:'evidencia_general'};
response = await window.fetch('/api/reports/1/images', {method:'POST',body:JSON.stringify(imagePayload)});
assert.equal(response.status, 201);
const storedReports = JSON.parse(localStorage.getItem('informtit.githubPages.reports.v1'));
assert.equal(storedReports[0].images.length, 1);

response = await window.fetch('/api/reports/1/pdf-jobs', {method:'POST',body:JSON.stringify({output_label:'Presencial'})});
assert.equal(response.status, 201);
const job = (await response.json()).job;
assert.equal(job.status, 'completed');

response = await window.fetch(`/api/pdf-jobs/${job.id}`);
assert.equal((await response.json()).job.progress, 100);

response = await window.fetch('/api/reports/1/generated-pdfs');
const list = (await response.json()).generated_pdfs;
assert.equal(list.length, 1);
assert.equal(list[0].modality_label, 'Presencial');

response = await window.fetch(`/api/reports/1/generated-pdfs/${list[0].artifact_id}/download`);
assert.equal(response.headers.get('content-type'), 'application/pdf');
const bytes = new Uint8Array(await response.arrayBuffer());
assert.equal(new TextDecoder('latin1').decode(bytes.slice(0, 8)), '%PDF-1.4');

console.log('Pages browser services smoke test: OK');
