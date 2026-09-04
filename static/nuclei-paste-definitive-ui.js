(() => {
  'use strict';

  if (!/(^|\.)github\.io$/i.test(window.location.hostname)) return;

  const SUMMARY_PREFIX = 'informtit.nucleiPasteV2.';

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

  function readStoredSummary(reportId) {
    try { return JSON.parse(sessionStorage.getItem(`${SUMMARY_PREFIX}${reportId}`) || 'null'); }
    catch (_) { return null; }
  }

  function storeSummary(reportId, result) {
    try { sessionStorage.setItem(`${SUMMARY_PREFIX}${reportId}`, JSON.stringify(result)); } catch (_) {}
  }

  function summaryMarkup(result) {
    if (!result?.summary) return '';
    const s = result.summary;
    const a = result.assignment || {};
    const unmatched = Array.isArray(result.unmatched) ? result.unmatched : [];
    return `
      <div class="nuclei-final-summary ${Number(s.review || 0) ? 'has-review' : 'all-good'}">
        <div class="nuclei-final-summary-head">
          <strong>Núcleo ${Number(a.nucleus || 0)} procesado</strong>
          <span>${esc(a.career || '')}${a.campus ? ` · ${esc(a.campus)}` : ''}</span>
          <small>Asignación: ${esc(a.source || 'automática')}</small>
        </div>
        <div class="nuclei-final-kpis">
          <span><strong>${Number(s.detected || 0)}</strong> detectados</span>
          <span><strong>${Number(s.matched || 0)}</strong> conciliados</span>
          <span><strong>${Number(s.review || 0)}</strong> por revisar</span>
          <span><strong>${Number(s.approved || 0)}</strong> aprobados</span>
          <span><strong>${Number(s.failed || 0)}</strong> reprobados</span>
        </div>
        ${unmatched.length ? `<details><summary>Ver estudiantes por revisar</summary><div class="nuclei-final-unmatched">${unmatched.map(item => `<div><strong>${esc(item.email || 'Sin correo')}</strong><span>${esc(item.name || '')} · nota ${esc(item.grade)}</span></div>`).join('')}</div></details>` : ''}
      </div>`;
  }

  function boxMarkup(report) {
    const reportId = Number(report?.id || 0);
    const summary = readStoredSummary(reportId);
    return `
      <section class="nuclei-final-box" data-nuclei-final-box>
        <div class="nuclei-final-title">
          <span class="eyebrow">Carga inteligente desde Moodle</span>
          <h3>Pegar calificaciones de un Núcleo</h3>
          <p>Pegue la tabla tal como la copia desde Moodle. Si copia también el título, por ejemplo “T- NUCLEO 1 ENFERMERIA ... Manta”, Informtit detecta automáticamente Núcleo, carrera y sede. Si el título no viene, seleccione solamente el número de Núcleo. El aula Moodle ya no es obligatoria.</p>
        </div>
        <form data-nuclei-final-form>
          <label>Texto copiado de Moodle
            <textarea name="text" rows="11" required placeholder="Pegue aquí la tabla completa de calificaciones. Puede copiar desde el título del aula o solamente la tabla."></textarea>
          </label>
          <div class="nuclei-final-grid">
            <label>Núcleo
              <select name="nucleus_number">
                <option value="">Automático desde el texto</option>
                <option value="1">Núcleo 1</option>
                <option value="2">Núcleo 2</option>
                <option value="3">Núcleo 3</option>
                <option value="4">Núcleo 4</option>
              </select>
              <small>Úselo solo cuando el texto no diga claramente Núcleo 1, 2, 3 o 4.</small>
            </label>
            <div class="nuclei-final-auto">
              <strong>Carrera y sede</strong>
              <span>Automáticas por encabezado y estudiantes del período.</span>
            </div>
          </div>
          <div class="nuclei-final-actions">
            <button type="submit" class="button primary">Procesar texto y guardar Núcleo</button>
            <small>La app usa correo institucional como coincidencia principal. Los casos dudosos quedan marcados para revisar.</small>
          </div>
        </form>
        <div data-nuclei-final-result>${summaryMarkup(summary)}</div>
      </section>`;
  }

  function install() {
    const report = activeReport();
    const tab = document.getElementById('tab-nuclei');
    if (!report?.id || !tab) return;
    const upload = tab.querySelector('.excel-nuclei-upload');
    if (!upload) return;
    if (!upload.querySelector('[data-nuclei-final-box]')) {
      upload.insertAdjacentHTML('afterbegin', boxMarkup(report));
    }
  }

  async function submit(form) {
    const report = activeReport();
    const reportId = Number(report?.id || 0);
    if (!reportId) throw new Error('Abra un período antes de procesar Núcleos.');

    const text = String(form.elements.text?.value || '');
    const nucleusNumber = Number(form.elements.nucleus_number?.value || 0);
    const button = form.querySelector('button[type="submit"]');
    const original = button?.textContent || 'Procesar texto y guardar Núcleo';
    if (button) {
      button.disabled = true;
      button.textContent = 'Procesando y conciliando...';
    }

    try {
      const result = await api(`/api/reports/${reportId}/nuclei/import-text-v2`, {
        method: 'POST',
        body: JSON.stringify({ text, nucleus_number: nucleusNumber || null }),
      });
      storeSummary(reportId, result);
      const s = result.summary || {};
      const a = result.assignment || {};
      toast(`Núcleo ${Number(a.nucleus || 0)} guardado: ${Number(s.matched || 0)} de ${Number(s.detected || 0)} estudiantes conciliados${Number(s.review || 0) ? `; ${Number(s.review || 0)} por revisar` : ''}.`, Number(s.review || 0) > 0);
      form.reset();
      const resultBox = form.closest('[data-nuclei-final-box]')?.querySelector('[data-nuclei-final-result]');
      if (resultBox) resultBox.innerHTML = summaryMarkup(result);
      if (typeof openReport === 'function') await openReport(reportId);
    } finally {
      if (button && document.contains(button)) {
        button.disabled = false;
        button.textContent = original;
      }
    }
  }

  document.addEventListener('submit', event => {
    const form = event.target.closest?.('[data-nuclei-final-form]');
    if (!form) return;
    event.preventDefault();
    void submit(form).catch(error => toast(clean(error?.message) || 'No se pudo procesar el texto de Núcleos.', true));
  }, true);

  const style = document.createElement('style');
  style.textContent = `
    [data-nuclei-paste-box] { display:none !important; }
    .nuclei-final-box { margin:-2px 0 18px; padding:18px; border:1px solid #bfdbfe; border-radius:14px; background:#f8fbff; }
    .nuclei-final-title h3 { margin:4px 0 6px; font-size:18px; }
    .nuclei-final-title p { margin:0 0 14px; max-width:980px; color:#64748b; font-size:12px; line-height:1.55; }
    .nuclei-final-box form { display:grid; gap:12px; }
    .nuclei-final-box label { display:grid; gap:6px; font-weight:700; }
    .nuclei-final-box textarea { width:100%; min-height:210px; resize:vertical; font-family:inherit; }
    .nuclei-final-grid { display:grid; grid-template-columns:minmax(220px, .8fr) minmax(260px, 1.2fr); gap:12px; align-items:stretch; }
    .nuclei-final-grid select { min-height:42px; }
    .nuclei-final-grid small, .nuclei-final-actions small { color:#64748b; font-size:11px; font-weight:400; }
    .nuclei-final-auto { border:1px solid #dbeafe; background:#fff; border-radius:10px; padding:11px 12px; display:grid; align-content:center; gap:3px; }
    .nuclei-final-auto strong { color:#173b57; }
    .nuclei-final-auto span { color:#64748b; font-size:11px; }
    .nuclei-final-actions { display:flex; gap:12px; align-items:center; flex-wrap:wrap; }
    .nuclei-final-summary { margin-top:14px; padding:13px; border-radius:12px; border:1px solid #bbf7d0; background:#f0fdf4; }
    .nuclei-final-summary.has-review { border-color:#fed7aa; background:#fff7ed; }
    .nuclei-final-summary-head { display:grid; gap:3px; }
    .nuclei-final-summary-head strong { font-size:14px; }
    .nuclei-final-summary-head span, .nuclei-final-summary-head small { color:#64748b; font-size:11px; }
    .nuclei-final-kpis { display:flex; gap:8px; flex-wrap:wrap; margin-top:10px; }
    .nuclei-final-kpis span { padding:7px 9px; border-radius:9px; background:rgba(255,255,255,.82); font-size:11px; }
    .nuclei-final-kpis strong { font-size:13px; }
    .nuclei-final-summary details { margin-top:10px; }
    .nuclei-final-summary summary { cursor:pointer; font-size:11px; font-weight:700; }
    .nuclei-final-unmatched { display:grid; gap:5px; margin-top:8px; }
    .nuclei-final-unmatched div { display:flex; justify-content:space-between; gap:12px; padding:7px 9px; background:#fff; border-radius:8px; font-size:11px; }
    .nuclei-final-unmatched span { color:#64748b; text-align:right; }
    @media (max-width:760px) { .nuclei-final-grid { grid-template-columns:1fr; } .nuclei-final-unmatched div { display:grid; } .nuclei-final-unmatched span { text-align:left; } }
  `;
  document.head.appendChild(style);

  const observer = new MutationObserver(() => queueMicrotask(install));
  observer.observe(document.body, { childList: true, subtree: true });
  install();
})();
