(() => {
  'use strict';

  // Compatibilidad temporal.
  // El módulo PVC completo se monta desde GitHub Pages mediante un único runtime.
  // Se desactiva aquí la versión anterior porque utilizaba un MutationObserver
  // que modificaba el DOM observado y podía provocar un bucle continuo al abrir PVC.
  window.INFORMTIT_PVC_LEGACY_DISABLED = true;
})();
