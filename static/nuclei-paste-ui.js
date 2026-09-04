(() => {
  'use strict';

  if (!/(^|\.)github\.io$/i.test(window.location.hostname)) return;

  const SUMMARY_PREFIX = 'informtit.nucleiPasteSummary.';

  function clean(value) {
    return String(value ?? '').trim();
  }

  function esc(value) {
    if (typeof escapeHtml === 'function') return escapeHtml(clean(value));
    return clean(value).replace(/[&<>"']/g, char => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;',
    }[char]));
  }

  function activeReport() {
    return typeof state !== 'undefined' ? state.activeReport : null;
  }

  function catalog() {
    return Array.isArray(window.informtitNucleiPaste?.catalog) ? window.informtitNucleiPaste.catalog : [];
  }

  function selectedCourseMarkup(report) {
    const items = catalog();
    const grouped = new Map();
    items.forEach(item => {
      const key = item.career || 'Otra carrera';
      if (!grouped.has(key)) grouped.set(key, []);
      grouped.get(key).push(item);
    });
    const options = [...grouped.entries()].map(([career, rows]) => `
      <optgroup label="${esc(career)}">
        ${rows
          .slice()
          .sort((a, b) => Number(a.nucleus) - Number(b.nucleus) || String(a.campus).localeCompare(String(b.campus), 'es'))
          .map(item => `<option value="${Number(item.courseId)}">Núcleo ${Number(item.nucleus)} · ${esc(item.campus)} · ${esc(item.subject)} · Moodle ${Number(item.courseId)}</option>`)
          .join('')}
      </optgroup>`).join('');
    const disabled = clean(report?.firebase_period_id) !== clean(window.informtitNucleiPaste?.periodId);
    return `
      <label class="nuclei-paste-course">Aula / Núcleo de respaldo
        <select name="course_id" ${disabled ? 'disabled' : ''}>
          <option value="">Detectar automáticamente desde el texto</option>
          ${options}
        </select>
        <small>${disabled
          ? 'El catálogo de aulas disponible corresponde a Octubre 2025 - Marzo 2026.'
          : 'Úselo solo si el texto copiado no incluye el enlace o ID del aula Moodle.'}</small>
      </label>`;
  }

  function readStoredSummary(reportId) {
    try {
      return JSON.parse(sessionStorage.getItem(`${SUMMARY_PREFIX}${reportId}`) || 'null');
    } catch (_) { return null; }
  }

  function storeSummary(reportId, result) {
    try { sessionStorage.setItem(`${SUMMARY_PREFIX}${reportId}`, JSON.stringify(result)); } catch (_) {}
  }

  function summaryMarkup(result) {
    if (!result?.summary) return '';
    const s = result.summary;
    const c = result.course || {};
    const unmatched = Array.isArray(result.unmatched) ? result.unmatched : [];
    return `
      <div class="nuclei-paste-summary ${Number(s.review || 0) ? 'has-review' : 'all-good'}">
        <div class="nuclei-paste-summary-head">
          <strong>Núcleo ${Number(c.nucleus || 0)} procesado</strong>
          <span>${esc(c.career || '')} · ${esc(c.campus || '')} · Moodle ${Number(c.course_id || 0)}</span>
        </div>
        <div class="nuclei-paste-kpis">
          <span><strong>${Number(s.detected || 0)}</strong> detectados</span>
          <span><strong>${Number(s.matched || 0)}</strong> conciliados</span>
          <span><strong>${Number(s.review || 0)}</strong> por revisar</span>
          <span><strong>${Number(s.approved || 0)}</strong> aprobados</span>
          <span><strong>${Number(s.failed || 0)}</strong> reprobados</span>
        </div>
        ${unmatched.length ? `<details><summary>Ver registros por revisar</summary><div class="nuclei-paste-unmatched">${unmatched.map(item => `<div><strong>${esc(item.email || 'Sin correo')}</strong><span>${esc(item.name || '')} · nota ${esc(item.grade)}</span></div>`).join('')}</div></details>` : ''}
      </div>`;
  }

  function formMarkup(report) {
    const reportId = Number(report?.id || 0);
    const summary = readStoredSummary(reportId);
    return `
      <section class="nuclei-paste-box" data-nuclei-paste-box>
        <div class="nuclei-paste-title">
          <div>
            <span class="eyebrow">Carga inteligente desde Moodle</span>
            <h3>Pegar calificaciones de un Núcleo</h3>
            <p>Copie la tabla completa de calificaciones de Moodle y péguela aquí. Informtit detecta el aula, identifica a cada estudiante por correo, aprende el ID de Moodle, recupera su cédula y modalidad desde la población oficial, y toma la última calificación numérica de cada fila como nota final.</p>
          </div>
        </div>
        <form data-nuclei-paste-form>
          <label>Texto copiado de Moodle
            <textarea name="text" rows="10" required placeholder="Pegue aquí la tabla completa. Puede ser el texto copiado directamente desde Moodle o la tabla con enlaces."></textarea>
          </label>
          ${selectedCourseMarkup(report)}
          <div class="nuclei-paste-actions">
            <button type="submit" class="button primary">Procesar texto y guardar Núcleo</button>
            <small>Procese un aula por vez. La carga reemplaza únicamente ese aula/núcleo, no los demás Núcleos ya guardados.</small>
          </div>
        </form>
        <div data-nuclei-paste-result>${summaryMarkup(summary)}</div>
      </section>`;
  }

  function installBox() {
    const report = activeReport();
    const tab = document.getElementById('tab-nuclei');
    if (!report?.id || !tab) return;
    const upload = tab.querySelector('.excel-nuclei-upload');
    if (!upload || upload.querySelector('[data-nuclei-paste-box]')) return;
    upload.insertAdjacentHTML('afterbegin', formMarkup(report));
  }

  async function submitPaste(form) {
    const report = activeReport();
    const reportId = Number(report?.id || 0);
    if (!reportId) throw new Error('Abra un período antes de procesar Núcleos.');
    const text = String(form.elements.text?.value || '');
    const courseId = Number(form.elements.course_id?.value || 0);
    const button = form.querySelector('button[type="submit"]');
    const original = button?.textContent || 'Procesar texto y guardar Núcleo';
    if (button) {
      button.disabled = true;
      button.textContent = 'Procesando y conciliando...';
    }
    try {
      const result = await api(`/api/reports/${reportId}/nuclei/import-text`, {
        method: 'POST',
        body: JSON.stringify({ text, course_id: courseId || null }),
      });
      storeSummary(reportId, result);
      const summary = result.summary || {};
      const course = result.course || {};
      const message = `Núcleo ${Number(course.nucleus || 0)} guardado: ${Number(summary.matched || 0)} de ${Number(summary.detected || 0)} estudiantes conciliados${Number(summary.review || 0) ? `; ${Number(summary.review || 0)} por revisar` : ''}.`;
      toast(message, Number(summary.review || 0) > 0);
      form.reset();
      if (typeof openReport === 'function') await openReport(reportId);
    } finally {
      if (button && document.contains(button)) {
        button.disabled = false;
        button.textContent = original;
      }
    }
  }

  document.addEventListener('submit', event => {
    const form = event.target.closest?.('[data-nuclei-paste-form]');
    if (!form) return;
    event.preventDefault();
    void submitPaste(form).catch(error => toast(clean(error?.message) || 'No se pudo procesar el texto de Núcleos.', true));
  }, true);

  const style = document.createElement('style');
  style.textContent = `
    .nuclei-paste-box { margin:-2px 0 18px; padding:18px; border:1px solid #bfdbfe; border-radius:14px; background:#f8fbff; }
    .nuclei-paste-title h3 { margin:4px 0 6px; font-size:18px; }
    .nuclei-paste-title p { margin:0 0 14px; max-width:980px; color:#64748b; font-size:12px; line-height:1.55; }
    .nuclei-paste-box form { display:grid; gap:12px; }
    .nuclei-paste-box label { display:grid; gap:6px; font-weight:700; }
    .nuclei-paste-box textarea { width:100%; min-height:190px; resize:vertical; font-family:inherit; }
    .nuclei-paste-course select { min-height:42px; }
    .nuclei-paste-course small, .nuclei-paste-actions small { color:#64748b; font-size:11px; font-weight:400; }
    .nuclei-paste-actions { display:flex; gap:12px; align-items:center; flex-wrap:wrap; }
    .nuclei-paste-summary { margin-top:14px; padding:13px; border-radius:12px; border:1px solid #bbf7d0; background:#f0fdf4; }
    .nuclei-paste-summary.has-review { border-color:#fed7aa; background:#fff7ed; }
    .nuclei-paste-summary-head { display:grid; gap:3px; }
    .nuclei-paste-summary-head strong { font-size:14px; }
    .nuclei-paste-summary-head span { color:#64748b; font-size:11px; }
    .nuclei-paste-kpis { display:flex; gap:8px; flex-wrap:wrap; margin-top:10px; }
    .nuclei-paste-kpis span { padding:7px 9px; border-radius:9px; background:rgba(255,255,255,.78); font-size:11px; }
    .nuclei-paste-kpis strong { font-size:13px; }
    .nuclei-paste-summary details { margin-top:10px; }
    .nuclei-paste-summary summary { cursor:pointer; font-size:11px; font-weight:700; }
    .nuclei-paste-unmatched { display:grid; gap:5px; margin-top:8px; }
    .nuclei-paste-unmatched div { display:flex; justify-content:space-between; gap:12px; padding:7px 9px; background:#fff; border-radius:8px; font-size:11px; }
    .nuclei-paste-unmatched span { color:#64748b; text-align:right; }
    @media (max-width:720px) { .nuclei-paste-unmatched div { display:grid; } .nuclei-paste-unmatched span { text-align:left; } }
  `;
  document.head.appendChild(style);

  const observer = new MutationObserver(() => queueMicrotask(installBox));
  observer.observe(document.body, { childList: true, subtree: true });
  installBox();
})();
