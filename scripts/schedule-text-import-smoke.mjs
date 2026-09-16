import fs from 'node:fs';
import vm from 'node:vm';

const file = process.argv[2] || 'static/schedule-text-import-ui.js';
const source = fs.readFileSync(file, 'utf8');
const context = { console, globalThis: {} };
context.globalThis = context;
vm.createContext(context);
vm.runInContext(source, context, { filename:file });
const api = context.InformtitScheduleTextImport;
if (!api?.parseScheduleText) throw new Error('No se exportó InformtitScheduleTextImport.parseScheduleText');

const complexive = `**Octubre 2025 a Marzo 2026**
| ActividadFecha inicioFecha fin | | |
| --- | --- | --- |
| Núcleo 1 | 30/3/2026 | 2/4/2026 |
| Núcleo 2 | 6/4/2026 | 9/4/2026 |
| Núcleo 3 | 10/4/2026 | 14/4/2026 |
| Núcleo 4 | 15/4/2026 | 18/4/2026 |
| Examen Complexivo | 20/4/2026 | 24/4/2026 |
| Supletorio | 4/5/2026 | 4/5/2026 |`;

const thesis = `### Fase 1: Inicio y planificación
| ActividadFecha inicioFecha fin | | |
| --- | --- | --- |
| Inducción | 16/12/2025 | 16/12/2025 |
| Clase Redacción eficiente de tesis | 28/1/2026 | 28/1/2026 |
| Elaboración de propuesta de temas | 1/2/2026 | 1/2/2026 |
| Aprobación del tema | 2/2/2026 | 4/2/2026 |
| Elaboración del plan de titulación | 8/2/2026 | 8/2/2026 |
| Aprobación del plan | 9/2/2026 | 11/2/2026 |
### Fase 2: Desarrollo y tutorías
| ActividadFecha inicioFecha fin | | |
| --- | --- | --- |
| Desarrollo del trabajo (redacción) | 11/2/2026 | 28/2/2026 |
| Borrador 1 | 1/3/2026 | 1/3/2026 |
| Revisión del borrador 1 con el estudiante | 2/3/2026 | 5/3/2026 |
| Borrador 2 | 8/3/2026 | 8/3/2026 |
| Revisión del borrador 2 con el estudiante | 9/3/2026 | 13/3/2026 |
| Ajustes finales del trabajo | 14/3/2026 | 19/3/2026 |
| Entrega de trabajo de titulación | 22/3/2026 | 22/3/2026 |
| Aprobación del tutor e informe antiplagio | 23/3/2026 | 25/3/2026 |
| Fin de clases | 27/3/2026 | 27/3/2026 |
### Fase 3: Defensa final
| ActividadFecha inicioFecha fin | | |
| --- | --- | --- |
| Preparación de defensa | 25/3/2026 | 8/4/2026 |
| Defensa de tesis | 14/4/2026 | 15/4/2026 |
| Tutoría extra de supletorio | 14/4/2026 | 15/4/2026 |
| Supletorio defensa | 16/4/2026 | 18/4/2026 |
| Cierre del proceso | 20/4/2026 | 20/4/2026 |`;

const a = api.parseScheduleText(complexive, 'complexive');
if (a.errors.length) throw new Error(`Complexivo produjo errores: ${a.errors.join(' | ')}`);
if (a.entries.length !== 6) throw new Error(`Se esperaban 6 actividades Complexivo y llegaron ${a.entries.length}`);
if (a.entries[0].start_date !== '2026-03-30' || a.entries[5].end_date !== '2026-05-04') throw new Error('Normalización de fechas Complexivo incorrecta');

const b = api.parseScheduleText(thesis, 'thesis');
if (b.errors.length) throw new Error(`Trabajo de Titulación produjo errores: ${b.errors.join(' | ')}`);
if (b.entries.length !== 20) throw new Error(`Se esperaban 20 actividades de Trabajo de Titulación y llegaron ${b.entries.length}`);
const counts = new Map();
for (const row of b.entries) counts.set(row.phase, (counts.get(row.phase) || 0) + 1);
if (counts.get('Fase 1: Inicio y planificación') !== 6) throw new Error('Fase 1 debe contener 6 actividades');
if (counts.get('Fase 2: Desarrollo y tutorías') !== 9) throw new Error('Fase 2 debe contener 9 actividades');
if (counts.get('Fase 3: Defensa final') !== 5) throw new Error('Fase 3 debe contener 5 actividades');

const invalid = api.parseScheduleText('| Actividad X | 31/2/2026 | 1/3/2026 |', 'complexive');
if (!invalid.errors.length) throw new Error('El parser debe rechazar fechas imposibles');

console.log('schedule-text-import smoke: OK · 6 Complexivo · 20 Trabajo de Titulación');