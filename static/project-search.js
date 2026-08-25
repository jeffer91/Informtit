(() => {
  // Expone únicamente el estado local de la interfaz para que los módulos
  // posteriores (incluida la conciliación de Estudiantes) conozcan el informe
  // interno activo del período unificado. No altera datos académicos.
  try {
    if (typeof state !== 'undefined') window.state = state;
  } catch (_) {
    // La interfaz base puede no haber terminado de inicializarse todavía.
  }
})();
