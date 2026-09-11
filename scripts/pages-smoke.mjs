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
  document_config: {
    cover: {
      enabled: true,
      institution: 'INSTITUTO QA',
      title: 'PORTADA QA',
      subtitle: 'Prueba documental',
      show_period: true,
      show_code: true,
      show_date: false,
      show_responsibles: false,
    },
    header: {
      enabled: true,
      left_text: 'CABECERA QA',
      center_text: 'Informe Final',
      show_code: true,
      show_version: true,
      show_period: false,
      exclude_cover: true,
    },
    sections: [
      {key:'resultados',title:'RESULTADOS QA',visible:true,order:1},
      {key:'introduccion',title:'INTRODUCCION QA',visible:true,order:2},
      {key:'base_legal',title:'BASE LEGAL QA',visible:false,order:3},
      {key:'metodologia',title:'METODOLOGIA QA',visible:false,order:4},
      {key:'conclusiones',title:'CONCLUSIONES QA',visible:false,order:5},
      {key:'recomendaciones',title:'RECOMENDACIONES QA',visible:false,order:6},
      {key:'anexos',title:'ANEXOS QA',visible:false,order:7},
    ],
  },
  images: [],
  careers: [
    {name:'ENFERMERÍA',students:[
      {full_name:'Ana Presencial',identification:'0101',final_status:'Aprobado',final_grade:9,modality:'presencial'},
      {full_name:'Beto Online',identification:'0202',final_status:'Aprobado',final_grade:8,modality:'en_linea'},
    ]},
  ],
  complexive_records: 2,
};
localStorage.setItem('informtit.githubPages.reports.v1', JSON.stringify([report]));

function json(payload, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(payload), {status, headers:{'Content-Type':'application/json'}}));
}

const rosterStudents = [
  {
    identification:'0101',full_name:'Ana Presencial',career_name:'ENFERMERÍA',modality:'presencial',route:'COMPLEXIVO',has_nuclei:true,
    academic_status:'CUMPLE',documentation_status:'CUMPLE',financial_status:'CUMPLE',titulation_status:'CUMPLE',practices_linkage_status:'CUMPLE',linkage_status:'CUMPLE',graduate_followup_status:'CUMPLE',english_status:'CUMPLE',data_update_status:'CUMPLE',requirements_complete:true,
  },
  {
    identification:'0202',full_name:'Beto Online',career_name:'ENFERMERÍA',modality:'en_linea',route:'COMPLEXIVO',has_nuclei:true,
    academic_status:'NO CUMPLE',documentation_status:'CUMPLE',financial_status:'CUMPLE',titulation_status:'CUMPLE',practices_linkage_status:'CUMPLE',linkage_status:'CUMPLE',graduate_followup_status:'CUMPLE',english_status:'CUMPLE',data_update_status:'CUMPLE',requirements_complete:false,
  },
];

async function mockFetch(input) {
  const raw = typeof input === 'string' ? input : input?.url;
  const path = new URL(raw, 'https://jeffer91.github.io/Informtit/').pathname;
  if (path === '/api/reports/1') return json({ok:true, report});
  if (path === '/api/reports/1/roster') return json({
    ok:true,
    summary:{students:2,careers:1,requirements_complete:1,requirements_pending:1,presencial:1,online:1},
    requirements:[{label:'Académico',complies:1,does_not_comply:1}],
    careers:[{name:'ENFERMERÍA',students:2}],
    students:rosterStudents,
    source:'GOOGLE_SHEETS',synced_at:'2026-09-11T12:00:00Z'
  });
  if (path === '/api/reports/1/students-domain') return json({ok:true,students:rosterStudents});
  if (path === '/api/reports/1/nuclei') return json({ok:true,courses:[{career_name:'ENFERMERÍA',nucleus_number:1,course_average:8.5,students:[{modality:'presencial',final_grade:9},{modality:'en_linea',final_grade:8}]}]});
  if (path === '/api/reports/1/projects') return json({ok:true,projects:[],summary:{total:0}});
  if (path === '/api/reports/1/schedules') return json({ok:true,schedules:{complexive:[],thesis:[]}});
  return json({ok:false,error:`Unhandled ${path}`},404);
}

const sourcePayload = {ok:true};
const InformtitSheets = {
  estudiantes: async () => sourcePayload,
  matriculas: async () => sourcePayload,
  requisitos: async () => sourcePayload,
  nucleos: async () => sourcePayload,
  complexivo: async () => sourcePayload,
  trabajoTitulacion: async () => sourcePayload,
};

globalThis.Element = class Element {};
globalThis.document = {
  addEventListener() {},
  querySelectorAll() { return []; },
  querySelector() { return null; },
  body: null,
};
globalThis.window = {
  location: {hostname:'jeffer91.github.io',href:'https://jeffer91.github.io/Informtit/'},
  fetch: mockFetch,
  localStorage,
  InformtitSheets,
};
globalThis.localStorage = localStorage;
globalThis.location = window.location;
globalThis.MutationObserver = undefined;

const browserRuntimePath = process.argv[2] || new URL('../static/pages-browser-services.js', import.meta.url).pathname;
const stabilityRuntimePath = process.argv[3] || new URL('../static/pages-stability-runtime.js', import.meta.url).pathname;
const documentPdfRuntimePath = process.argv[4] || '';
vm.runInThisContext(fs.readFileSync(browserRuntimePath, 'utf8'), {filename: browserRuntimePath});
vm.runInThisContext(fs.readFileSync(stabilityRuntimePath, 'utf8'), {filename: stabilityRuntimePath});
if (documentPdfRuntimePath) vm.runInThisContext(fs.readFileSync(documentPdfRuntimePath, 'utf8'), {filename: documentPdfRuntimePath});

let response = await window.fetch('/api/health');
assert.equal(response.ok, true);
assert.equal((await response.json()).database, 'Google Sheets');

response = await window.fetch('/api/reports/1/audit');
const auditPayload = await response.json();
assert.equal(auditPayload.ok, true);
assert.equal(auditPayload.audit.can_generate_pdf, true);
assert.equal(auditPayload.audit.traceability.source_errors.length, 0);

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
assert.equal(list[0].output_students, 1);
assert.equal(list[0].output_requirements_complete, 1);
if (documentPdfRuntimePath) {
  assert.equal(list[0].cover_enabled, true);
  assert.equal(list[0].header_enabled, true);
  assert.deepEqual(list[0].sections_applied.map(section => section.key), ['resultados', 'introduccion']);
}

response = await window.fetch(`/api/reports/1/generated-pdfs/${list[0].artifact_id}/download`);
assert.equal(response.headers.get('content-type'), 'application/pdf');
const bytes = new Uint8Array(await response.arrayBuffer());
const pdfText = new TextDecoder('latin1').decode(bytes);
assert.equal(pdfText.slice(0, 8), '%PDF-1.4');
assert.match(pdfText, /Estudiantes: 1/);
assert.match(pdfText, /Requisitos completos: 1/);
assert.doesNotMatch(pdfText, /Requisitos pendientes: 1/);
if (documentPdfRuntimePath) {
  assert.match(pdfText, /PORTADA QA/);
  assert.match(pdfText, /CABECERA QA/);
  assert.match(pdfText, /1\. RESULTADOS QA/);
  assert.match(pdfText, /2\. INTRODUCCION QA/);
  assert.doesNotMatch(pdfText, /CONCLUSIONES QA/);
}

InformtitSheets.complexivo = async () => { throw new Error('Complexivo temporalmente no disponible'); };
response = await window.fetch('/api/reports/1/audit');
const failedAudit = await response.json();
assert.equal(failedAudit.audit.can_generate_pdf, false);
assert.equal(failedAudit.audit.state, 'ERROR DE FUENTE');
assert.ok(failedAudit.audit.traceability.source_errors.some(item => item.includes('Examen Complexivo')));

response = await window.fetch('/api/reports/1/pdf-jobs', {method:'POST',body:JSON.stringify({output_label:'Presencial'})});
assert.equal(response.status, 409);
const blocked = await response.json();
assert.match(blocked.error, /fallaron fuentes institucionales/i);

console.log(documentPdfRuntimePath ? 'Pages browser + document PDF smoke test: OK' : 'Pages browser + stability smoke test: OK');
