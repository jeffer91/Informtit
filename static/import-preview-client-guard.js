// Evita que el diálogo de Requisitos quede indefinidamente en "Analizando...".
(function () {
  'use strict';

  if (typeof api !== 'function' || window.__informtitPreviewTimeoutInstalled) return;

  const previousApi = api;
  const PREVIEW_TIMEOUT_MS = 20000;

  api = async function (path, options = {}) {
    if (path !== '/api/imports/preview') return previousApi(path, options);

    const started = performance.now();
    console.info('[Informtit][Requisitos] Iniciando análisis del archivo.');

    let timer = null;
    try {
      const timeout = new Promise((_, reject) => {
        timer = window.setTimeout(() => {
          reject(new Error(
            'El análisis del archivo tardó más de 20 segundos. Abra la consola con F12 y revise la pestaña Console/Network.'
          ));
        }, PREVIEW_TIMEOUT_MS);
      });

      const result = await Promise.race([previousApi(path, options), timeout]);
      console.info(
        `[Informtit][Requisitos] Archivo analizado en ${Math.round(performance.now() - started)} ms.`,
        result?.preview || result
      );
      return result;
    } catch (error) {
      console.error('[Informtit][Requisitos] Falló el análisis del archivo:', error);
      throw error;
    } finally {
      if (timer !== null) window.clearTimeout(timer);
    }
  };

  window.__informtitPreviewTimeoutInstalled = true;
})();
