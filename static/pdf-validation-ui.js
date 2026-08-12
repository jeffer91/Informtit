// Validación previa del PDF completo.
(function () {
  const button = document.getElementById('export-pdf');
  if (!button) return;

  button.addEventListener('click', async event => {
    event.preventDefault();
    const reportId = state.activeReport?.id;
    if (!reportId) {
      toast('Seleccione un informe antes de generar el PDF.', true);
      return;
    }

    button.setAttribute('aria-busy', 'true');
    button.classList.add('disabled');
    try {
      const data = await api(`/api/reports/${reportId}/validate-pdf`);
      const validation = data.validation || {};
      const errors = validation.errors || [];
      const warnings = validation.warnings || [];

      if (errors.length) {
        toast(errors.map(item => item.detail).join(' · '), true);
        return;
      }

      if (warnings.length) {
        const message = [
          'La validación encontró observaciones antes de generar el PDF:',
          '',
          ...warnings.map(item => `• ${item.detail}`),
          '',
          '¿Desea generar el PDF de todas formas?'
        ].join('\n');
        if (!window.confirm(message)) return;
      }

      window.location.href = `/api/reports/${reportId}/export/pdf`;
    } catch (error) {
      toast(error.message || 'No se pudo validar el PDF.', true);
    } finally {
      button.removeAttribute('aria-busy');
      button.classList.remove('disabled');
    }
  });
})();
