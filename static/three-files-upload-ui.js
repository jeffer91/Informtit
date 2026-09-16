(() => {
  'use strict';

  if (typeof window === 'undefined' || !/(^|\.)github\.io$/i.test(window.location.hostname)) return;

  const VERSION = '1.0.0';
  const MARKER = 'THREE_SISACAD_FILES_UPLOAD_V1';
  const selected = { requirements:null, complexive:null, nuclei:null };
  const $ = (selector, root = document) => root.querySelector(selector);

  function clean(value) {
    return String(value ?? '').replace(/\u00a0/g, ' ').trim().replace(/\s+/g, ' ');
  }

  function setBadge(kind, state, label, detail = '') {
    const card = document.querySelector(`[data-three-file="${kind}"]`);
    if (!card) return;
    card.dataset.state = state;
    const badge = card.querySelector('[data-three-file-badge]');
    const name = card.querySelector('[data-three-file-name]');
    if (badge) badge.textContent = label;
    if (name) name.textContent = detail || 'Ningún archivo seleccionado';
  }

  function assignFile(input, file) {
    if (!input || !file) return false;
    try {
      const transfer = new DataTransfer();
      transfer.items.add(file);
      input.files = transfer.files;
      input.dispatchEvent(new Event('change', { bubbles:true }));
      return true;
    } catch (_) {
      return false;
    }
  }

  function waitFor(selector, timeout = 3000) {
    return new Promise((resolve, reject) => {
      const started = Date.now();
      const tick = () => {
        const node = document.querySelector(selector);
        if (node) return resolve(node);
        if (Date.now() - started >= timeout) return reject(new Error(`No se encontró ${selector}.`));
        setTimeout(tick, 60);
      };
      tick();
    });
  }

  async function reviewRequirements() {
    const file = selected.requirements;
    if (!file) return;
    setBadge('requirements', 'review', 'Abriendo', file.name);
    try {
      document.querySelector('#report-tabs [data-tab="roster"]')?.click();
      const open = await waitFor('#neon-req-open');
      open.click();
      const input = await waitFor('#neon-req-file');
      if (!assignFile(input, file)) throw new Error('El navegador no permitió transferir el archivo al importador de requisitos.');
      setBadge('requirements', 'review', 'En revisión', file.name);
    } catch (error) {
      setBadge('requirements', 'error', 'Error', error?.message || String(error));
      window.toast?.(error?.message || String(error), true);
    }
  }

  async function reviewResult(kind) {
    const file = selected[kind];
    if (!file) return;
    const inputId = kind === 'complexive' ? '#complexive-import-file' : '#nuclei-import-file';
    setBadge(kind, 'review', 'Analizando', file.name);
    try {
      const input = document.querySelector(inputId);
      if (!input) throw new Error('Abra nuevamente la pestaña Importaciones para inicializar el importador.');
      if (!assignFile(input, file)) throw new Error('El navegador no permitió transferir el archivo al importador.');
      setTimeout(() => {
        const preview = document.querySelector(kind === 'complexive' ? '#complexive-import-preview' : '#nuclei-import-preview');
        const hasSave = Boolean(preview?.querySelector(`[data-save-${kind}]`));
        const hasError = Boolean(document.querySelector(kind === 'complexive' ? '#complexive-import-message.academic-error' : '#nuclei-import-message.academic-error'));
        if (hasError) setBadge(kind, 'error', 'Revisar', file.name);
        else if (hasSave) setBadge(kind, 'review', 'Analizado', file.name);
        else setBadge(kind, 'review', 'Procesando', file.name);
      }, 700);
    } catch (error) {
      setBadge(kind, 'error', 'Error', error?.message || String(error));
      window.toast?.(error?.message || String(error), true);
    }
  }

  function uploadCard(kind, number, title, description, accept, buttonText) {
    return `<article class="three-file-card" data-three-file="${kind}" data-state="empty">
      <div class="three-file-top">
        <span class="three-file-number">${number}</span>
        <span class="three-file-badge" data-three-file-badge>Sin archivo</span>
      </div>
      <h4>${title}</h4>
      <p>${description}</p>
      <label class="three-file-input">Seleccionar archivo<input type="file" data-three-file-input="${kind}" accept="${accept}"></label>
      <small data-three-file-name>Ningún archivo seleccionado</small>
      <button type="button" class="button secondary small" data-three-file-review="${kind}" disabled>${buttonText}</button>
    </article>`;
  }

  function panelHtml() {
    return `<section id="three-sisacad-files" class="three-files-panel">
      <div class="three-files-head">
        <div><span class="eyebrow">Carga SISACAD</span><h3>Subir los 3 archivos del período</h3><p>Los tres archivos se validan por separado y se cruzan por cédula. No se mezclan entre sí.</p></div>
        <span class="three-files-order">Orden: Requisitos → 01.xlsx → 02.xlsx</span>
      </div>
      <div class="three-files-grid">
        ${uploadCard('requirements','1','Población y requisitos','ReporteAprobacionTitulacion…xls. Es la población maestra del período.','.xls,.xlsx,.html,.htm,.csv,.tsv','Revisar requisitos')}
        ${uploadCard('complexive','2','Examen Complexivo','01.xlsx. Teórico, práctico, promedio acumulado y supletorio.','.xlsx,.xls','Analizar 01.xlsx')}
        ${uploadCard('nuclei','3','Núcleos','02.xlsx. Cuatro Núcleos por cédula, con materia, docente, nota y resultado.','.xlsx,.xls','Analizar 02.xlsx')}
      </div>
      <div class="three-files-note"><strong>Trabajo de Titulación sigue independiente.</strong> Se carga por cédula en su propio apartado y tiene prioridad sobre Complexivo.</div>
    </section>`;
  }

  function bindPanel(panel) {
    panel.querySelectorAll('[data-three-file-input]').forEach(input => {
      input.addEventListener('change', event => {
        const kind = event.currentTarget.dataset.threeFileInput;
        const file = event.currentTarget.files?.[0] || null;
        selected[kind] = file;
        const button = panel.querySelector(`[data-three-file-review="${kind}"]`);
        if (button) button.disabled = !file;
        if (file) setBadge(kind, 'review', 'Listo para revisar', file.name);
        else setBadge(kind, 'empty', 'Sin archivo', 'Ningún archivo seleccionado');
      });
    });
    panel.querySelector('[data-three-file-review="requirements"]')?.addEventListener('click', reviewRequirements);
    panel.querySelector('[data-three-file-review="complexive"]')?.addEventListener('click', () => reviewResult('complexive'));
    panel.querySelector('[data-three-file-review="nuclei"]')?.addEventListener('click', () => reviewResult('nuclei'));
  }

  function ensurePanel() {
    const shell = document.querySelector('#tab-imports .academic-import-shell');
    if (!shell || document.getElementById('three-sisacad-files')) return;
    const head = shell.querySelector('.academic-main-head');
    if (!head) return;
    head.insertAdjacentHTML('afterend', panelHtml());
    bindPanel(document.getElementById('three-sisacad-files'));
  }

  function injectStyles() {
    if (document.getElementById('three-files-style')) return;
    const style = document.createElement('style');
    style.id = 'three-files-style';
    style.textContent = `
      .three-files-panel{border:1px solid #d8e3ed;border-radius:14px;background:#f8fbfe;padding:14px;display:grid;gap:12px}
      .three-files-head{display:flex;justify-content:space-between;gap:14px;align-items:flex-start}.three-files-head h3{margin:3px 0 4px}.three-files-head p{margin:0;color:#60758a;font-size:12px}.three-files-order{font-size:10px;font-weight:800;background:#eaf2fb;color:#24577f;border-radius:999px;padding:6px 9px;white-space:nowrap}
      .three-files-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}.three-file-card{border:1px solid #e1a8a8;background:#fff3f3;border-radius:12px;padding:12px;display:grid;gap:8px;min-width:0}.three-file-card[data-state="review"]{border-color:#e4c46b;background:#fff9df}.three-file-card[data-state="ready"]{border-color:#addbb9;background:#f0faf3}.three-file-card[data-state="error"]{border-color:#d98080;background:#fdecec}.three-file-top{display:flex;justify-content:space-between;gap:8px;align-items:center}.three-file-number{width:24px;height:24px;border-radius:999px;display:grid;place-items:center;background:#e9f0f7;color:#284f73;font-size:11px;font-weight:800}.three-file-badge{font-size:9px;font-weight:800;border-radius:999px;padding:4px 7px;background:#f4dada;color:#982b2b}.three-file-card[data-state="review"] .three-file-badge{background:#ffe9a8;color:#805900}.three-file-card[data-state="ready"] .three-file-badge{background:#dff2e5;color:#24643d}.three-file-card h4{margin:0;font-size:14px}.three-file-card p{margin:0;color:#60758a;font-size:11px;line-height:1.4}.three-file-input{display:grid;gap:5px;font-size:11px;font-weight:700;border:1px dashed #a9bfd3;border-radius:9px;padding:9px;background:rgba(255,255,255,.75)}.three-file-input input{width:100%;font-size:10px}.three-file-card small{color:#60758a;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.three-file-card button{justify-self:start}.three-files-note{font-size:11px;color:#49647d;border-top:1px solid #e1e8ef;padding-top:9px}
      @media(max-width:900px){.three-files-grid{grid-template-columns:1fr}.three-files-head{flex-direction:column}.three-files-order{white-space:normal}}
    `;
    document.head.appendChild(style);
  }

  injectStyles();
  ensurePanel();
  const observer = new MutationObserver(() => ensurePanel());
  observer.observe(document.documentElement, { childList:true, subtree:true });
  document.addEventListener('click', event => {
    if (event.target.closest?.('[data-tab="imports"]')) setTimeout(ensurePanel, 0);
  }, true);

  window.InformtitThreeFilesUpload = Object.freeze({ VERSION, MARKER });
})();