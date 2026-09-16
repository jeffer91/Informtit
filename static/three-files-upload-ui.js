(() => {
  'use strict';

  if (typeof window === 'undefined' || !/(^|\.)github\.io$/i.test(window.location.hostname)) return;

  const VERSION = '1.1.0';
  const MARKER = 'THREE_SISACAD_FILES_AUTODETECT_V1_1';
  const XLSX_SRC = 'https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js';
  const selected = { requirements:null, complexive:null, nuclei:null };
  const LABELS = {
    requirements: 'Población y requisitos',
    complexive: 'Examen Complexivo',
    nuclei: 'Núcleos',
  };
  const $ = (selector, root = document) => root.querySelector(selector);

  function clean(value) {
    return String(value ?? '').replace(/\u00a0/g, ' ').trim().replace(/\s+/g, ' ');
  }
  function fold(value) {
    return clean(value).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toUpperCase();
  }
  function keyOf(value) {
    return fold(value).replace(/[^A-Z0-9]/g, '');
  }

  async function loadXlsx() {
    if (window.XLSX) return window.XLSX;
    await new Promise((resolve, reject) => {
      const existing = document.querySelector(`script[src="${XLSX_SRC}"]`);
      if (existing) {
        if (window.XLSX) return resolve();
        existing.addEventListener('load', resolve, { once:true });
        existing.addEventListener('error', () => reject(new Error('No se pudo cargar el lector de Excel.')), { once:true });
        return;
      }
      const script = document.createElement('script');
      script.src = XLSX_SRC;
      script.onload = resolve;
      script.onerror = () => reject(new Error('No se pudo cargar el lector de Excel.'));
      document.head.appendChild(script);
    });
    return window.XLSX;
  }

  function classifyHeaders(headers = []) {
    const keys = new Set(headers.map(keyOf).filter(Boolean));
    const has = name => keys.has(keyOf(name));

    if (has('identificacion_estudiante') && has('notaTeorico') && has('notaPractico') && has('notaPromedioAcumulado')) {
      return 'complexive';
    }
    if (has('numeroIdentificacion') && has('cod_materia') && has('nota_nucleo') && has('resultado_aprobacion')) {
      return 'nuclei';
    }
    if (has('numeroIdentificacion') && has('Academico') && has('Documentacion') && has('AprobacionTitulacion')) {
      return 'requirements';
    }
    return '';
  }

  function htmlHeaders(text) {
    if (!/<table[\s>]/i.test(text)) return [];
    const doc = new DOMParser().parseFromString(text, 'text/html');
    const rows = [...doc.querySelectorAll('table tr')].slice(0, 12).map(tr =>
      [...tr.querySelectorAll('th,td')].map(td => clean(td.textContent))
    );
    return rows.find(row => row.some(cell => ['NUMEROIDENTIFICACION','IDENTIFICACIONESTUDIANTE','NOMBRES','NOMBRECARRERA'].includes(keyOf(cell)))) || rows[0] || [];
  }

  async function headersFromFile(file) {
    const buffer = await file.arrayBuffer();
    const bytes = new Uint8Array(buffer);
    const preview = new TextDecoder('windows-1252').decode(bytes.subarray(0, Math.min(bytes.length, 32768)));
    if (/<table[\s>]/i.test(preview)) {
      let text = preview;
      try { text = new TextDecoder('utf-8', { fatal:true }).decode(bytes); }
      catch (_) { text = new TextDecoder('windows-1252').decode(bytes); }
      if (/�/.test(text)) text = new TextDecoder('windows-1252').decode(bytes);
      return htmlHeaders(text);
    }

    const XLSX = await loadXlsx();
    const workbook = XLSX.read(buffer, { type:'array', cellDates:false });
    const first = workbook.SheetNames[0];
    if (!first) return [];
    const matrix = XLSX.utils.sheet_to_json(workbook.Sheets[first], { header:1, defval:'', raw:false });
    return (matrix || []).find(row => Array.isArray(row) && row.some(cell => clean(cell))) || [];
  }

  async function detectFile(file) {
    const headers = await headersFromFile(file);
    const kind = classifyHeaders(headers);
    return { kind, headers };
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

  function setInputFile(input, file) {
    if (!input) return false;
    if (!file) { input.value = ''; return true; }
    try {
      const transfer = new DataTransfer();
      transfer.items.add(file);
      input.files = transfer.files;
      return true;
    } catch (_) {
      return false;
    }
  }

  function updateButton(kind) {
    const button = document.querySelector(`[data-three-file-review="${kind}"]`);
    if (button) button.disabled = !selected[kind];
  }

  function placeDetectedFile(kind, file) {
    selected[kind] = file;
    const input = document.querySelector(`[data-three-file-input="${kind}"]`);
    setInputFile(input, file);
    updateButton(kind);
    setBadge(kind, 'review', 'Tipo detectado', `${file.name} · ${LABELS[kind]}`);
  }

  function restoreOrigin(kind, previous) {
    selected[kind] = previous || null;
    setInputFile(document.querySelector(`[data-three-file-input="${kind}"]`), previous || null);
    updateButton(kind);
    if (previous) setBadge(kind, 'review', 'Tipo detectado', `${previous.name} · ${LABELS[kind]}`);
    else setBadge(kind, 'empty', 'Sin archivo', 'Ningún archivo seleccionado');
  }

  async function handleSelectedFile(originKind, file, previous = null) {
    if (!file) return;
    setBadge(originKind, 'review', 'Detectando', file.name);
    const detected = await detectFile(file);
    if (!detected.kind) {
      restoreOrigin(originKind, previous);
      throw new Error(`${file.name}: no corresponde a ninguno de los 3 formatos SISACAD reconocidos.`);
    }
    if (detected.kind !== originKind) {
      restoreOrigin(originKind, previous);
      placeDetectedFile(detected.kind, file);
      window.toast?.(`${file.name} fue reconocido como ${LABELS[detected.kind]} y se colocó automáticamente en su apartado.`);
      return detected.kind;
    }
    placeDetectedFile(originKind, file);
    return originKind;
  }

  async function handleBulkFiles(files) {
    const message = document.getElementById('three-files-message');
    if (message) { message.textContent = 'Identificando archivos por sus columnas…'; message.className = 'three-files-message review'; }
    const errors = [];
    const detectedKinds = [];
    for (const file of files) {
      try {
        const result = await detectFile(file);
        if (!result.kind) throw new Error(`${file.name}: formato no reconocido`);
        placeDetectedFile(result.kind, file);
        detectedKinds.push(result.kind);
      } catch (error) {
        errors.push(error?.message || String(error));
      }
    }
    const uniqueKinds = new Set(detectedKinds);
    if (message) {
      if (errors.length) {
        message.className = 'three-files-message error';
        message.textContent = errors.join(' · ');
      } else if (uniqueKinds.size === 3) {
        message.className = 'three-files-message ready';
        message.textContent = 'Los 3 archivos fueron identificados correctamente por estructura, sin depender del nombre del archivo.';
      } else {
        const missing = Object.keys(LABELS).filter(kind => !selected[kind]).map(kind => LABELS[kind]);
        message.className = 'three-files-message review';
        message.textContent = `Archivos detectados. Falta: ${missing.join(', ') || 'ninguno'}.`;
      }
    }
  }

  function assignFileAndDispatch(input, file) {
    if (!input || !file) return false;
    if (!setInputFile(input, file)) return false;
    input.dispatchEvent(new Event('change', { bubbles:true }));
    return true;
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
    setBadge('requirements', 'review', 'Analizando', file.name);
    try {
      document.querySelector('#report-tabs [data-tab="roster"]')?.click();
      const open = await waitFor('#neon-req-open');
      open.click();
      const input = await waitFor('#neon-req-file');
      if (!assignFileAndDispatch(input, file)) throw new Error('El navegador no permitió transferir el archivo al importador de requisitos.');
      setTimeout(() => {
        const preview = document.querySelector('#neon-req-preview');
        const hasSave = !document.querySelector('#neon-req-save')?.disabled;
        const hasWarning = Boolean(preview?.querySelector('.req-warning'));
        if (hasSave && !hasWarning) setBadge('requirements', 'ready', 'Validado', file.name);
        else if (hasSave) setBadge('requirements', 'review', 'Con observaciones', file.name);
        else setBadge('requirements', 'error', 'Revisar', file.name);
      }, 1000);
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
      if (!assignFileAndDispatch(input, file)) throw new Error('El navegador no permitió transferir el archivo al importador.');
      setTimeout(() => {
        const preview = document.querySelector(kind === 'complexive' ? '#complexive-import-preview' : '#nuclei-import-preview');
        const message = document.querySelector(kind === 'complexive' ? '#complexive-import-message' : '#nuclei-import-message');
        const hasErrorMessage = Boolean(message?.classList.contains('academic-error'));
        const hasErrors = [...(preview?.querySelectorAll('.academic-pill.bad') || [])].length > 0;
        const hasWarnings = [...(preview?.querySelectorAll('.academic-pill.warn') || [])].length > 0;
        const hasSave = Boolean(preview?.querySelector(`[data-save-${kind}]`));
        if (hasErrorMessage || hasErrors) setBadge(kind, 'error', 'Revisar', file.name);
        else if (hasSave && !hasWarnings) setBadge(kind, 'ready', 'Validado', file.name);
        else if (hasSave) setBadge(kind, 'review', 'Con observaciones', file.name);
        else setBadge(kind, 'review', 'Procesando', file.name);
      }, 900);
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
        <div><span class="eyebrow">Carga SISACAD</span><h3>Subir los 3 archivos del período</h3><p>Informtit identifica cada archivo por sus columnas. El nombre 01, 02 o Reporte no se utiliza para decidir qué contiene.</p></div>
        <span class="three-files-order">Cruce: cédula</span>
      </div>
      <label class="three-files-bulk"><strong>Seleccionar los 3 archivos a la vez</strong><span>Puede elegirlos en cualquier orden; Informtit los ubicará automáticamente.</span><input type="file" id="three-files-bulk-input" multiple accept=".xls,.xlsx,.html,.htm,.csv,.tsv"></label>
      <div id="three-files-message" class="three-files-message">También puede elegir cada archivo por separado.</div>
      <div class="three-files-grid">
        ${uploadCard('requirements','1','Población y requisitos','Debe contener numeroIdentificacion, Académico, Documentación y aprobaciones. Acepta el .xls HTML antiguo en Windows-1252.','.xls,.xlsx,.html,.htm,.csv,.tsv','Revisar requisitos')}
        ${uploadCard('complexive','2','Examen Complexivo','Debe contener identificacion_estudiante, notaTeorico, notaPractico y notaPromedioAcumulado.','.xlsx,.xls','Analizar Complexivo')}
        ${uploadCard('nuclei','3','Núcleos','Debe contener numeroIdentificacion, cod_materia, nota_nucleo y resultado_aprobacion.','.xlsx,.xls','Analizar Núcleos')}
      </div>
      <div class="three-files-note"><strong>Trabajo de Titulación sigue independiente.</strong> Se carga por cédula en su propio apartado y tiene prioridad sobre Complexivo.</div>
    </section>`;
  }

  function bindPanel(panel) {
    panel.querySelectorAll('[data-three-file-input]').forEach(input => {
      input.addEventListener('change', async event => {
        const originKind = event.currentTarget.dataset.threeFileInput;
        const file = event.currentTarget.files?.[0] || null;
        if (!file) return;
        const previous = selected[originKind];
        try {
          await handleSelectedFile(originKind, file, previous);
        } catch (error) {
          setBadge(originKind, 'error', 'No reconocido', error?.message || String(error));
          window.toast?.(error?.message || String(error), true);
        }
      });
    });
    panel.querySelector('#three-files-bulk-input')?.addEventListener('change', event => {
      const files = [...(event.currentTarget.files || [])];
      if (files.length) void handleBulkFiles(files);
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
      .three-files-bulk{display:grid;gap:4px;border:1px dashed #7fa8cb;background:#fff;border-radius:11px;padding:11px;font-size:11px}.three-files-bulk>span{font-weight:400;color:#60758a}.three-files-bulk input{margin-top:3px}
      .three-files-message{font-size:11px;border-radius:9px;padding:8px 10px;background:#edf3f8;color:#49647d}.three-files-message.review{background:#fff6d7;color:#755500}.three-files-message.ready{background:#eaf8ef;color:#1d6538}.three-files-message.error{background:#fdeaea;color:#8e2525}
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

  window.InformtitThreeFilesUpload = Object.freeze({ VERSION, MARKER, classifyHeaders, detectFile });
})();