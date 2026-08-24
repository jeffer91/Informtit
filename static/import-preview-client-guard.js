// Progreso visible, timeout real y acceso directo a la consola para Requisitos.
(function () {
  'use strict';

  if (typeof api !== 'function' || window.__informtitPreviewTimeoutInstalled) return;

  const previousApi = api;
  const PREVIEW_TIMEOUT_MS = 15000;
  let progressTimer = null;
  let elapsedTimer = null;
  let progressValue = 0;
  let startedAt = 0;

  const style = document.createElement('style');
  style.textContent = `
    #import-analysis-status{margin:2px 0 4px;padding:12px 14px;border:1px solid #d7e1ec;border-radius:11px;background:#f7f9fc;display:none}
    #import-analysis-status.active{display:block}
    #import-analysis-status.success{background:#edf8f1;border-color:#c7e5d2}
    #import-analysis-status.error{background:#fff0ee;border-color:#efc7c1}
    .import-analysis-head{display:flex;justify-content:space-between;gap:12px;align-items:center;margin-bottom:8px}
    .import-analysis-head strong{font-size:13px;color:#243a52}
    .import-analysis-head span{font-size:12px;color:#60758b;white-space:nowrap}
    .import-analysis-track{height:9px;background:#e4eaf1;border-radius:999px;overflow:hidden}
    .import-analysis-bar{height:100%;width:0;background:#25689a;border-radius:999px;transition:width .25s ease}
    #import-analysis-status.success .import-analysis-bar{background:#2c7a50}
    #import-analysis-status.error .import-analysis-bar{background:#b4423a}
    .import-analysis-detail{font-size:12px;color:#62768a;margin-top:8px;line-height:1.45}
    #open-devtools-btn{white-space:nowrap}
  `;
  document.head.appendChild(style);

  function installConsoleButton() {
    const actions = document.querySelector('.top-actions');
    if (!actions || document.getElementById('open-devtools-btn')) return;
    const button = document.createElement('button');
    button.type = 'button';
    button.id = 'open-devtools-btn';
    button.className = 'button secondary';
    button.textContent = 'Consola';
    button.title = 'Abrir herramientas de desarrollo (F12)';
    button.onclick = async () => {
      if (window.informtitDesktop?.openDevTools) {
        await window.informtitDesktop.openDevTools();
      } else {
        alert('Use F12 o Ctrl + Shift + I para abrir la consola.');
      }
    };
    actions.insertBefore(button, actions.firstChild);
  }

  function ensureProgressBox() {
    const dialog = document.getElementById('active-report-import-dialog');
    if (!dialog) return null;
    let box = document.getElementById('import-analysis-status');
    if (box) return box;

    box = document.createElement('div');
    box.id = 'import-analysis-status';
    box.innerHTML = `
      <div class="import-analysis-head">
        <strong id="import-analysis-title">Preparando análisis...</strong>
        <span id="import-analysis-time">0,0 s</span>
      </div>
      <div class="import-analysis-track"><div class="import-analysis-bar" id="import-analysis-bar"></div></div>
      <div class="import-analysis-detail" id="import-analysis-detail"></div>`;
    dialog.querySelector('.dialog-head')?.insertAdjacentElement('afterend', box);
    dialog.addEventListener('close', () => stopProgress(false));
    return box;
  }

  function paintProgress(percent, title, detail, type = 'active') {
    const box = ensureProgressBox();
    if (!box) return;
    progressValue = Math.max(0, Math.min(100, Number(percent) || 0));
    box.className = type;
    box.classList.add('active');
    const titleNode = document.getElementById('import-analysis-title');
    const detailNode = document.getElementById('import-analysis-detail');
    const bar = document.getElementById('import-analysis-bar');
    if (titleNode) titleNode.textContent = title;
    if (detailNode) detailNode.textContent = detail || '';
    if (bar) bar.style.width = `${progressValue}%`;
  }

  function stopTimers() {
    if (progressTimer !== null) window.clearInterval(progressTimer);
    if (elapsedTimer !== null) window.clearInterval(elapsedTimer);
    progressTimer = null;
    elapsedTimer = null;
  }

  function stopProgress(hide = false) {
    stopTimers();
    if (hide) {
      const box = document.getElementById('import-analysis-status');
      if (box) box.className = '';
    }
  }

  function startProgress() {
    stopTimers();
    startedAt = performance.now();
    progressValue = 8;
    paintProgress(
      8,
      'Preparando archivo...',
      'Leyendo el archivo seleccionado antes de enviarlo al analizador.'
    );

    elapsedTimer = window.setInterval(() => {
      const elapsed = (performance.now() - startedAt) / 1000;
      const node = document.getElementById('import-analysis-time');
      if (node) node.textContent = `${elapsed.toFixed(1).replace('.', ',')} s`;
    }, 100);

    progressTimer = window.setInterval(() => {
      if (progressValue >= 88) return;
      const elapsed = (performance.now() - startedAt) / 1000;
      const next = elapsed < 1.5 ? 38 : elapsed < 4 ? 58 : elapsed < 8 ? 74 : 88;
      if (next > progressValue) {
        const detail = next < 50
          ? 'Enviando la información al backend local.'
          : next < 70
            ? 'Leyendo estudiantes, carreras y códigos.'
            : 'Clasificando y validando Presencial + Online.';
        paintProgress(next, 'Analizando Requisitos...', detail);
      }
    }, 350);
  }

  document.addEventListener('submit', event => {
    if (event.target?.id !== 'active-report-import-form') return;
    const confirmStep = document.getElementById('active-import-confirm-step');
    if (confirmStep && !confirmStep.hidden) return;
    startProgress();
  }, true);

  document.addEventListener('change', event => {
    if (event.target?.id !== 'active-roster-file') return;
    stopProgress(false);
    const file = event.target.files?.[0];
    if (file) {
      paintProgress(0, 'Archivo seleccionado', `${file.name} · ${(file.size / 1024).toFixed(1)} KB. Listo para analizar.`);
    }
  });

  api = async function (path, options = {}) {
    if (path !== '/api/imports/preview') return previousApi(path, options);

    if (!startedAt) startProgress();
    paintProgress(28, 'Enviando archivo...', 'Conectando con el analizador local de Informtit.');

    const requestStarted = performance.now();
    const controller = new AbortController();
    let timeoutId = null;
    console.info('[Informtit][Requisitos] Iniciando análisis del archivo.');

    try {
      const request = previousApi(path, { ...options, signal: controller.signal });
      const timeout = new Promise((_, reject) => {
        timeoutId = window.setTimeout(() => {
          controller.abort();
          reject(new Error(
            'El análisis superó 15 segundos y fue cancelado. Revise Consola > Console y Network; la base no fue modificada.'
          ));
        }, PREVIEW_TIMEOUT_MS);
      });

      const result = await Promise.race([request, timeout]);
      const preview = result?.preview || {};
      stopTimers();
      const elapsed = (performance.now() - requestStarted) / 1000;
      paintProgress(
        100,
        'Análisis completado',
        `${Number(preview.total || 0)} registros: ${Number(preview.presencial || 0)} Presencial + ${Number(preview.en_linea || 0)} Online.`,
        'success'
      );
      const timeNode = document.getElementById('import-analysis-time');
      if (timeNode) timeNode.textContent = `${elapsed.toFixed(1).replace('.', ',')} s`;
      console.info(
        `[Informtit][Requisitos] Archivo analizado en ${Math.round(performance.now() - requestStarted)} ms.`,
        preview
      );
      return result;
    } catch (rawError) {
      stopTimers();
      const timedOut = rawError?.name === 'AbortError';
      const error = timedOut
        ? new Error('El backend no respondió dentro de 15 segundos. La importación fue cancelada sin modificar la base.')
        : rawError;
      paintProgress(
        100,
        'Error durante el análisis',
        `${error?.message || 'Error desconocido.'} Abra el botón Consola de la parte superior para ver el detalle técnico.`,
        'error'
      );
      console.error('[Informtit][Requisitos] Falló el análisis del archivo:', error);
      throw error;
    } finally {
      if (timeoutId !== null) window.clearTimeout(timeoutId);
    }
  };

  installConsoleButton();
  window.__informtitPreviewTimeoutInstalled = true;

  // La interfaz robusta se carga al final para reemplazar el flujo antiguo
  // "solo modalidad activa" sin depender de la caché del index principal.
  if (!document.querySelector('script[data-robust-import-ui]')) {
    const script = document.createElement('script');
    script.src = '/robust-import-ui.js?v=4.2';
    script.dataset.robustImportUi = '1';
    document.head.appendChild(script);
  }
})();
