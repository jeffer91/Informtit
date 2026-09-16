(() => {
  'use strict';
  if (!/(^|\.)github\.io$/i.test(location.hostname)) return;

  const VERSION = '4.0.0';
  const MARKER = 'REPORT_HEALTH_INDEPENDENT_V4';
  const $ = (selector, root = document) => root.querySelector(selector);
  const clean = value => String(value ?? '').trim();
  const esc = value => clean(value).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const finite = value => value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value));
  const isPvc = () => clean(window.state?.activeReport?.report_type || window.state?.activeReport?.project_summary?.report_type).toLowerCase() === 'pvc';

  function ensure() {
    if (isPvc()) return null;
    const tabs = $('#report-tabs'), workspace = $('#report-workspace');
    if (!tabs || !workspace) return null;
    let button = tabs.querySelector('[data-tab="summary"]');
    if (!button) {
      button = document.createElement('button');
      button.className = 'tab';
      button.dataset.tab = 'summary';
      button.textContent = 'Resumen';
      tabs.prepend(button);
    }
    let content = $('#tab-summary');
    if (!content) {
      content = document.createElement('div');
      content.id = 'tab-summary';
      content.className = 'tab-content';
      $('#tab-roster')?.insertAdjacentElement('beforebegin', content);
    }
    return content;
  }

  function component(title, status, detail, tab = '') {
    const label = status === 'ok' ? 'Correcto' : status === 'warn' ? 'Revisar' : status === 'error' ? 'Error' : 'Sin datos';
    return `<article class="shealth-card ${status}"><div><h3>${esc(title)}</h3><span>${label}</span></div><p>${esc(detail)}</p>${tab ? `<button class="button secondary small" data-shealth-tab="${tab}">Abrir</button>` : ''}</article>`;
  }

  async function safe(path) {
    try {
      const response = await fetch(path, { method:'GET', cache:'no-store' });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || data?.ok === false) throw new Error(data?.error || `Error ${response.status}`);
      return { ok:true, data };
    } catch (error) {
      return { ok:false, error:clean(error?.message || error) || 'No respondió.' };
    }
  }

  async function periodId(report) {
    return clean(await window.InformtitPagesData?.resolvePeriodId?.(report) || report?.periodoId || report?.firebase_period_id || report?.period_id);
  }

  async function complexiveRows(id) {
    if (!id) return { ok:false, error:'No existe período activo.', rows:[] };
    try {
      const db = await window.InformtitNeon.getClient();
      const result = await db.from('complexive_results')
        .select('student_id,theoretical_grade,practical_grade,accumulated_grade,supplementary_theoretical,supplementary_practical,final_grade,final_status')
        .eq('period_id', id);
      if (result?.error) throw result.error;
      return { ok:true, rows:Array.isArray(result?.data) ? result.data : [] };
    } catch (error) {
      return { ok:false, error:clean(error?.message || error) || 'No se pudo consultar Complexivo.', rows:[] };
    }
  }

  async function render() {
    if (isPvc()) return;
    const report = window.state?.activeReport;
    const reportId = Number(report?.id || 0);
    const host = ensure();
    if (!reportId || !host) return;
    host.innerHTML = '<div class="panel"><div class="empty-mini">Validando cada componente del período…</div></div>';

    const pId = await periodId(report);
    const [roster, schedules, nuclei, projects, complexive] = await Promise.all([
      safe(`/api/reports/${reportId}/roster`),
      safe(`/api/reports/${reportId}/schedules`),
      safe(`/api/reports/${reportId}/nuclei`),
      safe(`/api/reports/${reportId}/projects`),
      complexiveRows(pId),
    ]);
    if (Number(window.state?.activeReport?.id || 0) !== reportId || isPvc()) return;

    const students = Array.isArray(roster.data?.students) ? roster.data.students : [];
    const reqSummary = roster.data?.summary || {};
    const missingReq = students.filter(row => Array.isArray(row.blank_requirements) && row.blank_requirements.length).length;
    const noCumple = students.filter(row => Array.isArray(row.pending_requirements) && row.pending_requirements.length).length;
    const courses = Array.isArray(nuclei.data?.courses) ? nuclei.data.courses : [];
    const projectsRows = Array.isArray(projects.data?.projects) ? projects.data.projects : [];
    const scheduleData = schedules.data?.schedules || {};
    const ordinary = complexive.rows.filter(row => finite(row.theoretical_grade) || finite(row.practical_grade) || finite(row.accumulated_grade));
    const supplementary = complexive.rows.filter(row => finite(row.supplementary_theoretical) || finite(row.supplementary_practical));

    const careerNuclei = new Map();
    courses.forEach(course => {
      const key = clean(course.career_name);
      if (!careerNuclei.has(key)) careerNuclei.set(key, new Set());
      careerNuclei.get(key).add(Number(course.nucleus_number));
    });
    const four = [...careerNuclei.values()].filter(set => set.size >= 4).length;

    const cards = [];
    cards.push({
      status: !roster.ok ? 'error' : !students.length ? 'empty' : missingReq ? 'warn' : 'ok',
      html: component('Requisitos', !roster.ok ? 'error' : !students.length ? 'empty' : missingReq ? 'warn' : 'ok',
        !roster.ok ? roster.error : !students.length ? 'No hay población cargada.' : `${students.length} estudiantes · ${Number(reqSummary.requirements_complete || 0)} habilitados · ${noCumple} con uno o más NO CUMPLE${missingReq ? ` · ${missingReq} con datos faltantes` : ''}.`, 'roster')
    });
    const complexScheduleCount = Array.isArray(scheduleData.complexive) ? scheduleData.complexive.length : 0;
    cards.push({ status:!schedules.ok?'error':complexScheduleCount?'ok':'empty', html:component('Cronograma Núcleos / Complexivo', !schedules.ok?'error':complexScheduleCount?'ok':'empty', !schedules.ok?schedules.error:`${complexScheduleCount} actividades registradas.`, 'schedules') });
    cards.push({ status:!nuclei.ok?'error':courses.length?(four===careerNuclei.size?'ok':'warn'):'empty', html:component('Núcleos', !nuclei.ok?'error':courses.length?(four===careerNuclei.size?'ok':'warn'):'empty', !nuclei.ok?nuclei.error:`${careerNuclei.size} carreras · ${courses.length} grupos de Núcleo · ${four} carreras con 4/4.`, 'nuclei') });
    cards.push({ status:!complexive.ok?'error':ordinary.length?'ok':'empty', html:component('Examen Complexivo ordinario', !complexive.ok?'error':ordinary.length?'ok':'empty', !complexive.ok?complexive.error:`${ordinary.length} resultados ordinarios registrados.`, 'careers') });
    cards.push({ status:!complexive.ok?'error':supplementary.length?'ok':'empty', html:component('Examen Complexivo supletorio', !complexive.ok?'error':supplementary.length?'ok':'empty', !complexive.ok?complexive.error:(supplementary.length?`${supplementary.length} resultados supletorios registrados.`:'Sin resultados supletorios; se controla por separado del ordinario.'), 'careers') });
    cards.push({ status:!projects.ok?'error':projectsRows.length?'ok':'empty', html:component('Trabajo de Titulación', !projects.ok?'error':projectsRows.length?'ok':'empty', !projects.ok?projects.error:`${projectsRows.length} estudiantes con registro.`, 'projects') });
    const thesisScheduleCount = Array.isArray(scheduleData.thesis) ? scheduleData.thesis.length : 0;
    cards.push({ status:!schedules.ok?'error':thesisScheduleCount?'ok':'empty', html:component('Cronograma Trabajo de Titulación', !schedules.ok?'error':thesisScheduleCount?'ok':'empty', !schedules.ok?schedules.error:`${thesisScheduleCount} actividades registradas.`, 'schedules') });

    const validCount = cards.filter(item => item.status === 'ok').length;
    const errorCount = cards.filter(item => item.status === 'error').length;
    const reviewCount = cards.filter(item => item.status === 'warn').length;
    const percent = Math.round(validCount / cards.length * 100);
    const neonStatus = errorCount ? 'warn' : 'ok';
    const neonDetail = errorCount ? `${errorCount} componente(s) no pudieron consultarse. Los demás permanecen independientes.` : 'Fuente principal compartida conectada. Cada componente se valida por separado.';

    host.innerHTML = `<div class="shealth">
      <section class="shealth-overview"><div><span class="eyebrow">Validación independiente del período</span><h2>${validCount} de ${cards.length} componentes con información válida</h2><p>Requisitos, Núcleos, ordinario, supletorio, Trabajo de Titulación y ambos cronogramas no dependen entre sí.${reviewCount ? ` ${reviewCount} componente(s) requieren revisión.` : ''}</p></div><strong>${percent}%</strong></section>
      <div class="shealth-grid">${cards.map(item => item.html).join('')}${component('Neon PostgreSQL', neonStatus, neonDetail, '')}</div>
    </div>`;
    host.querySelectorAll('[data-shealth-tab]').forEach(button => button.onclick = () => document.querySelector(`#report-tabs [data-tab="${button.dataset.shealthTab}"]`)?.click());
  }

  if (!$('#shealth-style')) {
    const style = document.createElement('style');
    style.id = 'shealth-style';
    style.textContent = `.shealth{display:grid;gap:14px}.shealth-overview{display:flex;justify-content:space-between;align-items:center;gap:20px;padding:18px;border:1px solid #dfe7ee;border-radius:14px;background:#fff}.shealth-overview h2{margin:4px 0}.shealth-overview p{margin:0;color:#64748b;font-size:12px}.shealth-overview>strong{font-size:28px}.shealth-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px}.shealth-card{padding:13px;border:1px solid #e0e7ee;border-radius:12px;background:#fff;display:flex;flex-direction:column;min-height:125px}.shealth-card>div{display:flex;justify-content:space-between;gap:8px}.shealth-card h3{margin:0;font-size:14px}.shealth-card span{font-size:10px;font-weight:800}.shealth-card p{font-size:11px;color:#64748b;line-height:1.45}.shealth-card button{margin-top:auto;align-self:flex-start}.shealth-card.ok{border-color:#bee7ca}.shealth-card.warn{border-color:#f0d39c}.shealth-card.error{border-color:#e4aaaa;background:#fff7f6}.shealth-card.empty{border-color:#dfe7ee}`;
    document.head.appendChild(style);
  }

  const previous = window.renderReport;
  if (typeof previous === 'function') window.renderReport = function(...args) { const result = previous.apply(this,args); if (!isPvc()) setTimeout(() => void render(), 0); return result; };
  document.addEventListener('click', event => { if (event.target.closest?.('[data-tab="summary"]') && !isPvc()) setTimeout(() => void render(), 0); });
  document.addEventListener('informtit:period-changed', () => setTimeout(() => void render(), 250));
  window.InformtitReportHealth = Object.freeze({ VERSION, MARKER, render });
})();