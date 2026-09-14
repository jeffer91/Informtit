(() => {
  'use strict';

  if (!/(^|\.)github\.io$/i.test(window.location.hostname)) return;

  const dialog = document.getElementById('report-dialog');
  const form = document.getElementById('report-form');
  const submit = document.getElementById('create-report-submit');
  if (!dialog || !form || !submit) return;

  const ACTIVE_PERIOD_KEY = 'informtit.activePeriod.v2';
  const DEFAULT_TIMEOUT_MS = 15000;
  const originalSubmitLabel = String(submit.textContent || 'Crear informe').trim() || 'Crear informe';
  let operationId = 0;
  let busy = false;

  const clean = value => String(value ?? '').replace(/\u00a0/g, ' ').trim().replace(/\s+/g, ' ');
  const typeOf = value => clean(value).toLowerCase() === 'pvc' ? 'pvc' : 'normal';

  function ensureErrorBox() {
    let box = document.getElementById('report-create-error');
    if (box) return box;
    box = document.createElement('div');
    box.id = 'report-create-error';
    box.setAttribute('role', 'alert');
    box.setAttribute('aria-live', 'assertive');
    box.hidden = true;
    box.style.margin = '10px 20px 0';
    box.style.padding = '10px 12px';
    box.style.borderRadius = '9px';
    box.style.border = '1px solid #f1c9c9';
    box.style.background = '#fff1f1';
    box.style.color = '#9a2d2d';
    box.style.fontSize = '12px';
    const actions = form.querySelector('.dialog-actions');
    if (actions) form.insertBefore(box, actions);
    else form.appendChild(box);
    return box;
  }

  function clearError() {
    const box = ensureErrorBox();
    box.hidden = true;
    box.textContent = '';
  }

  function showError(message) {
    const box = ensureErrorBox();
    box.textContent = clean(message) || 'No se pudo crear el informe.';
    box.hidden = false;
  }

  function activePeriodId() {
    try {
      const active = JSON.parse(window.localStorage.getItem(ACTIVE_PERIOD_KEY) || 'null');
      return clean(active?.id || active?.periodoId || active?.sourceId);
    } catch (_) {
      return '';
    }
  }

  function normalizePayload(raw = {}) {
    const periodId = clean(raw.periodoId || raw.period_id || raw.firebase_period_id || raw.period_context_id || activePeriodId());
    if (!periodId) throw new Error('No existe un período activo. Seleccione un período antes de crear el informe.');
    const reportType = typeOf(raw.report_type);
    return {
      ...raw,
      periodoId: periodId,
      period_id: periodId,
      firebase_period_id: periodId,
      period_context_id: periodId,
      report_type: reportType,
      tipo: reportType,
      status: 'DRAFT',
    };
  }

  function withTimeout(promise, timeoutMs = DEFAULT_TIMEOUT_MS) {
    let timer = null;
    return Promise.race([
      Promise.resolve(promise),
      new Promise((_, reject) => {
        timer = window.setTimeout(() => reject(new Error('Neon tardó demasiado en responder. No cierre la página; puede reintentar la creación.')), timeoutMs);
      }),
    ]).finally(() => {
      if (timer !== null) window.clearTimeout(timer);
    });
  }

  function reportIdOf(report) {
    const value = Number(report?.id || report?.report_id || report?.reportId || 0);
    return Number.isFinite(value) && value > 0 ? value : 0;
  }

  async function findExisting(api, periodId, reportType) {
    if (typeof api?.informes !== 'function') return null;
    const result = await withTimeout(api.informes(periodId), 8000);
    const rows = Array.isArray(result?.informes) ? result.informes : [];
    return rows.find(row => typeOf(row?.report_type || row?.tipo) === reportType) || null;
  }

  async function createInNeon(rawPayload) {
    const api = window.InformtitSheets;
    if (!api || typeof api.guardarInforme !== 'function') {
      throw new Error('Neon todavía no está disponible. Actualice la página e intente nuevamente.');
    }

    const payload = normalizePayload(rawPayload);
    const reportType = typeOf(payload.report_type);

    const existing = await findExisting(api, payload.periodoId, reportType);
    if (existing) {
      const existingId = reportIdOf(existing);
      if (!existingId) throw new Error('El informe ya existe, pero Neon no devolvió un identificador válido.');
      return { ok: true, report: existing, reportId: existingId, existed: true };
    }

    const result = await withTimeout(api.guardarInforme(payload), DEFAULT_TIMEOUT_MS);
    let report = result?.report || null;
    let reportId = reportIdOf(report);

    if (!reportId) {
      report = await findExisting(api, payload.periodoId, reportType);
      reportId = reportIdOf(report);
    }
    if (!reportId) throw new Error('Neon confirmó la operación, pero no devolvió el identificador del informe.');

    return { ok: true, report, reportId, existed: false };
  }

  function setBusy(nextBusy) {
    busy = Boolean(nextBusy);
    submit.disabled = busy;
    submit.setAttribute('aria-busy', busy ? 'true' : 'false');
    submit.textContent = busy ? 'Creando…' : originalSubmitLabel;
  }

  function closeDialog() {
    operationId += 1;
    setBusy(false);
    clearError();
    if (dialog.open) dialog.close('cancel');
  }

  function isCloseButton(button) {
    if (!button) return false;
    if (button.dataset?.reportClose === '1') return true;
    if (clean(button.value).toLowerCase() === 'cancel') return true;
    return button.classList?.contains('icon-button') && button.closest?.('#report-dialog') === dialog;
  }

  dialog.querySelectorAll('button').forEach(button => {
    if (isCloseButton(button)) {
      button.type = 'button';
      button.dataset.reportClose = '1';
      button.setAttribute('data-report-close', '1');
    }
  });

  dialog.addEventListener('click', event => {
    const button = event.target?.closest?.('button');
    if (!isCloseButton(button)) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    closeDialog();
  }, true);

  form.addEventListener('submit', async event => {
    const submitter = event.submitter || null;
    event.preventDefault();
    event.stopImmediatePropagation();

    if (submitter && submitter !== submit) {
      if (isCloseButton(submitter)) closeDialog();
      return;
    }
    if (busy) return;
    if (typeof form.reportValidity === 'function' && !form.reportValidity()) return;

    clearError();
    setBusy(true);
    const thisOperation = ++operationId;
    const payload = Object.fromEntries(new FormData(form).entries());

    try {
      const result = await createInNeon(payload);
      if (thisOperation !== operationId) return;

      if (typeof window.loadReports !== 'function' || typeof window.openReport !== 'function') {
        throw new Error('El informe se guardó en Neon, pero la interfaz no pudo actualizarse. Recargue la página.');
      }

      await window.loadReports();
      if (thisOperation !== operationId) return;

      dialog.close('created');
      form.reset();
      if (typeof window.setReportDialogType === 'function') window.setReportDialogType('normal');
      if (typeof window.toast === 'function') {
        window.toast(result.existed ? 'El informe ya existía. Se abrió el documento guardado.' : 'Informe creado en Neon.');
      }
      await window.openReport(result.reportId);
    } catch (error) {
      if (thisOperation !== operationId) return;
      showError(error?.message || error);
    } finally {
      if (thisOperation === operationId) setBusy(false);
    }
  }, true);

  dialog.addEventListener('close', () => {
    if (!busy) clearError();
  });

  window.InformtitReportCreateController = Object.freeze({
    createInNeon,
    normalizePayload,
    closeDialog,
    withTimeout,
    version: '1.0.0',
    provider: 'NEON',
  });
})();
