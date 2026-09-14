import fs from 'node:fs';
import vm from 'node:vm';

const file = process.argv[2] || 'static/report-create-controller.js';
const source = fs.readFileSync(file, 'utf8');

function button({ id = '', value = '', classes = [], text = '' } = {}) {
  const set = new Set(classes);
  return {
    id,
    value,
    type: 'submit',
    textContent: text,
    disabled: false,
    dataset: {},
    attributes: {},
    classList: { contains: name => set.has(name) },
    closest: selector => selector === '#report-dialog' ? dialog : null,
    setAttribute(name, value2) { this.attributes[name] = String(value2); },
  };
}

const listeners = new Map();
const closeButton = button({ value: 'cancel', classes: ['icon-button'], text: '×' });
const cancelButton = button({ value: 'cancel', text: 'Cancelar' });
const submitButton = button({ id: 'create-report-submit', value: 'default', text: 'Crear informe' });

const actions = {};
const form = {
  payload: {
    report_type: 'normal',
    periodoId: '2025-10_2026-03',
    period: 'Octubre 2025 - Marzo 2026',
    name: 'Informe Final del Proceso de Titulación - Octubre 2025 - Marzo 2026',
    code: 'UTET-INF-01-PRO-95-2026-03',
    code_presencial: 'UTET-INF-01-PRO-95-2026-03',
    code_online: 'UTET-INF-02-PRO-95-2026-03',
    version: '1.0',
  },
  addEventListener(type, fn) { listeners.set(`form:${type}`, fn); },
  querySelector(selector) { return selector === '.dialog-actions' ? actions : null; },
  insertBefore() {},
  appendChild() {},
  reportValidity() { return true; },
  resetCalled: false,
  reset() { this.resetCalled = true; },
};

const dialog = {
  open: true,
  lastClose: '',
  querySelectorAll(selector) { return selector === 'button' ? [closeButton, cancelButton, submitButton] : []; },
  addEventListener(type, fn) { listeners.set(`dialog:${type}`, fn); },
  close(value = '') { this.open = false; this.lastClose = value; },
};

const createdNodes = [];
const document = {
  getElementById(id) {
    if (id === 'report-dialog') return dialog;
    if (id === 'report-form') return form;
    if (id === 'create-report-submit') return submitButton;
    if (id === 'report-create-error') return createdNodes.find(node => node.id === id) || null;
    return null;
  },
  createElement() {
    const node = { id: '', hidden: false, textContent: '', style: {}, attrs: {}, setAttribute(name, value) { this.attrs[name] = value; } };
    createdNodes.push(node);
    return node;
  },
};

class FakeFormData {
  constructor(target) { this.target = target; }
  *entries() { yield* Object.entries(this.target.payload); }
}

const localStorage = {
  values: new Map([['informtit.activePeriod.v2', JSON.stringify({ id: '2025-10_2026-03' })]]),
  getItem(key) { return this.values.get(key) ?? null; },
};

let guardarCalls = 0;
let loadCalls = 0;
let openedId = 0;
const window = {
  location: { hostname: 'jeffer91.github.io' },
  localStorage,
  setTimeout,
  clearTimeout,
  InformtitSheets: {
    async informes() { return { ok: true, informes: [] }; },
    async guardarInforme(payload) {
      guardarCalls += 1;
      if (payload.periodoId !== '2025-10_2026-03') throw new Error('periodoId incorrecto');
      return { ok: true, report: { id: 42, period_id: payload.periodoId, report_type: payload.report_type } };
    },
  },
  async loadReports() { loadCalls += 1; },
  async openReport(id) { openedId = id; },
  toast() {},
};

const context = vm.createContext({ window, document, FormData: FakeFormData, Object, Promise, Error, Number, String, Boolean, Array, JSON, Set, Map });
vm.runInContext(source, context, { filename: file });

if (closeButton.type !== 'button' || cancelButton.type !== 'button') throw new Error('Los controles de cierre siguen enviando el formulario.');
if (!window.InformtitReportCreateController) throw new Error('No se publicó el controlador de creación.');

const click = listeners.get('dialog:click');
if (!click) throw new Error('No se enlazó el cierre del modal.');
click({ target: closeButton, preventDefault() {}, stopImmediatePropagation() {} });
if (dialog.open) throw new Error('La X no cerró el modal.');

// Reabrir y comprobar la creación Neon-first.
dialog.open = true;
dialog.lastClose = '';
const submit = listeners.get('form:submit');
if (!submit) throw new Error('No se enlazó el submit del informe.');
await submit({ submitter: submitButton, preventDefault() {}, stopImmediatePropagation() {} });

if (guardarCalls !== 1) throw new Error(`Se esperó 1 escritura Neon y hubo ${guardarCalls}.`);
if (loadCalls !== 1) throw new Error(`Se esperó 1 recarga de informes y hubo ${loadCalls}.`);
if (openedId !== 42) throw new Error(`El informe creado no se abrió: ${openedId}.`);
if (dialog.lastClose !== 'created') throw new Error('El modal no cerró como creación exitosa.');
if (!form.resetCalled) throw new Error('El formulario no se reinició tras crear.');
if (submitButton.textContent !== 'Crear informe' || submitButton.disabled) throw new Error('El botón no recuperó su estado después de crear.');

console.log('report-create-controller smoke: OK');
