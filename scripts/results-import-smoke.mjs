import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';

const file = process.argv[2];
if (!file) throw new Error('Usage: node results-import-smoke.mjs <results-import-ui.js>');
const source = fs.readFileSync(file, 'utf8');

const document = {
  documentElement: {},
  head: { appendChild() {} },
  querySelector() { return null; },
  querySelectorAll() { return []; },
  createElement(tag) { return { tagName: String(tag).toUpperCase(), id:'', textContent:'', dataset:{}, classList:{ add(){}, remove(){}, toggle(){} } }; },
  addEventListener() {},
};
class MutationObserver { constructor(cb) { this.cb = cb; } observe() {} disconnect() {} }
const window = {
  location: { hostname: 'jeffer91.github.io' },
  state: { activeReport: { id: 1, period: 'Octubre 2025 a Marzo 2026', periodoId: '2025-10_2026-03' } },
};
const context = {
  window,
  document,
  MutationObserver,
  console,
  queueMicrotask() {},
  setTimeout() { return 0; },
  clearTimeout() {},
  structuredClone: globalThis.structuredClone,
  Map, Set, Array, Object, String, Number, Boolean, Math, Date, RegExp, JSON, Error, Promise,
};
window.window = window;
vm.createContext(context);
vm.runInContext(source, context, { filename: file });

const api = window.InformtitResultsImport;
assert.ok(api, 'InformtitResultsImport no se expuso');
assert.equal(api.version, '4.1.0');

const cedulaA = '1711111111';
const cedulaB = '1722222222';
const masterByCedula = new Map([
  [cedulaA, { student:{ id:1, full_name:'ESTUDIANTE A' }, enrollment:{ career_name:'GESTIÓN DEL TALENTO HUMANO', campus:'Matriz', career_code:'550417A01-P-1701' } }],
  [cedulaB, { student:{ id:2, full_name:'ESTUDIANTE B' }, enrollment:{ career_name:'ENFERMERÍA', campus:'Matriz', career_code:'550312A01-P-1701' } }],
]);
const master = { masterByCedula, thesisIds:new Set(), nucleiIds:new Set() };
const rows = [
  { codigo_carrera:'550417A01-P-1701', nombre_carrera:'GESTIÓN DEL TALENTO HUMANO', numeroIdentificacion:cedulaA, nombre_estudiante:'ESTUDIANTE A', modalidad:'HÍBRIDA/PRESENCIAL', sede:'Matriz', cod_materia:'550417A01-P-1701-714', materia:'T-Nucleo - Gestión Estratégica', Pro_nombre:'DOCENTE 1', nota_nucleo:'8,5', resultado_aprobacion:'APROBADO' },
  { codigo_carrera:'550417A01-P-1701', nombre_carrera:'GESTIÓN DEL TALENTO HUMANO', numeroIdentificacion:cedulaA, nombre_estudiante:'ESTUDIANTE A', modalidad:'HÍBRIDA/PRESENCIAL', sede:'Matriz', cod_materia:'550417A01-P-1701-715', materia:'T-Nucleo - Gestión Financiera', Pro_nombre:'DOCENTE 2', nota_nucleo:'8,0', resultado_aprobacion:'APROBADO' },
  { codigo_carrera:'550417A01-P-1701', nombre_carrera:'GESTIÓN DEL TALENTO HUMANO', numeroIdentificacion:cedulaA, nombre_estudiante:'ESTUDIANTE A', modalidad:'HÍBRIDA/PRESENCIAL', sede:'Matriz', cod_materia:'550417A01-P-1701-716', materia:'T-Nucleo - Gestión de Procesos y Calidad', Pro_nombre:'DOCENTE 3', nota_nucleo:'9,0', resultado_aprobacion:'APROBADO' },
  { codigo_carrera:'550417A01-P-1701', nombre_carrera:'GESTIÓN DEL TALENTO HUMANO', numeroIdentificacion:cedulaA, nombre_estudiante:'ESTUDIANTE A', modalidad:'HÍBRIDA/PRESENCIAL', sede:'Matriz', cod_materia:'550417A01-P-1701-717', materia:'T-Nucleo - Gestión Comercial', Pro_nombre:'DOCENTE 4', nota_nucleo:'9,5', resultado_aprobacion:'APROBADO' },
  { codigo_carrera:'550312A01-P-1701', nombre_carrera:'ENFERMERÍA', numeroIdentificacion:cedulaB, nombre_estudiante:'ESTUDIANTE B', modalidad:'HÍBRIDA / EN VIVO', sede:'Matriz', cod_materia:'550312A01-P-1701-701', materia:'T- Nucleo 1 - Enfermería', Pro_nombre:'DOCENTE 1', nota_nucleo:'8', resultado_aprobacion:'APROBADO' },
  { codigo_carrera:'550312A01-P-1701', nombre_carrera:'ENFERMERÍA', numeroIdentificacion:cedulaB, nombre_estudiante:'ESTUDIANTE B', modalidad:'HÍBRIDA / EN VIVO', sede:'Matriz', cod_materia:'550312A01-P-1701-702', materia:'T- Nucleo 2 - Enfermería', Pro_nombre:'DOCENTE 2', nota_nucleo:'8', resultado_aprobacion:'APROBADO' },
  { codigo_carrera:'550312A01-P-1701', nombre_carrera:'ENFERMERÍA', numeroIdentificacion:cedulaB, nombre_estudiante:'ESTUDIANTE B', modalidad:'HÍBRIDA / EN VIVO', sede:'Matriz', cod_materia:'550312A01-P-1701-703', materia:'T- Nucleo 3 - Enfermería', Pro_nombre:'DOCENTE 3', nota_nucleo:'8', resultado_aprobacion:'APROBADO' },
  { codigo_carrera:'550312A01-P-1701', nombre_carrera:'ENFERMERÍA', numeroIdentificacion:cedulaB, nombre_estudiante:'ESTUDIANTE B', modalidad:'HÍBRIDA / EN VIVO', sede:'Matriz', cod_materia:'550312A01-P-1701-704', materia:'T- Nucleo 4 - Enfermería', Pro_nombre:'DOCENTE 4', nota_nucleo:'8', resultado_aprobacion:'APROBADO' },
];
const parsed = api.reconcileNuclei(rows, master);
assert.equal(parsed.length, 8);
for (const cedula of [cedulaA, cedulaB]) {
  const nuclei = parsed.filter(row => row.cedula === cedula).map(row => row.nucleus).sort((a,b)=>a-b);
  assert.deepEqual(nuclei, [1,2,3,4], `${cedula} no quedó con Núcleos 1-4`);
}
assert.equal(parsed.filter(row => row.errors.length).length, 0, `Hay errores inesperados: ${JSON.stringify(parsed.filter(row => row.errors.length).map(row => row.errors))}`);

const legacyWrong = rows.slice(0,4).map(row => String(row.cod_materia).match(/70([1-4])(?:\D|$)/)?.[1] || '0');
assert.deepEqual(legacyWrong, ['1','1','1','1'], 'El caso de regresión ya no reproduce el bug viejo esperado');
console.log('results-import smoke OK: catálogo por carrera asigna 1-4 sin confundir el 1701 del código.');
