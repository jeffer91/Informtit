// Corrección de formularios asíncronos: event.currentTarget queda en null después de await.
(function applyFormSubmitFixes() {
  const reportForm = document.querySelector('#report-form');
  const careerForm = document.querySelector('#career-form');

  if (reportForm) {
    reportForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      event.stopImmediatePropagation();
      const form = event.currentTarget;
      const submitButton = form.querySelector('#create-report-submit');
      const payload = Object.fromEntries(new FormData(form).entries());
      if (submitButton) submitButton.disabled = true;
      try {
        const result = await api('/api/reports', { method: 'POST', body: JSON.stringify(payload) });
        document.querySelector('#report-dialog')?.close();
        form.reset();
        toast('Informe creado.');
        await loadReports();
        await openReport(result.report_id);
      } catch (error) {
        toast(error.message, true);
      } finally {
        if (submitButton) submitButton.disabled = false;
      }
    }, true);
  }

  if (careerForm) {
    careerForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      event.stopImmediatePropagation();
      const form = event.currentTarget;
      const submitButton = form.querySelector('button[value="default"]');
      const payload = Object.fromEntries(new FormData(form).entries());
      const reportId = state.activeReport?.id;
      if (!reportId) {
        toast('Primero abra un informe.', true);
        return;
      }
      if (submitButton) submitButton.disabled = true;
      try {
        await api(`/api/reports/${reportId}/careers`, { method: 'POST', body: JSON.stringify(payload) });
        document.querySelector('#career-dialog')?.close();
        form.reset();
        toast('Carrera agregada.');
        await openReport(reportId);
      } catch (error) {
        toast(error.message, true);
      } finally {
        if (submitButton) submitButton.disabled = false;
      }
    }, true);
  }
})();
