// Auditoría previa y barra de progreso de la generación del PDF.
(function () {
  if (window.__informtitPdfProgressInstalled) return;
  window.__informtitPdfProgressInstalled = true;

  const POLL_MS = 550;
  let activeJobId = null;
  let polling = false;
  let progressStartedAt = 0;
  let timerHandle = null;
  let pendingDownload = null;

  function ensureStyles() {
    if (document.getElementById('pdf-progress-style')) return;
    const style = document.createElement('style');
    style.id = 'pdf-progress-style';
    style.textContent = `
      .pdf-progress-overlay, .report-audit-overlay {
        position: fixed;
        inset: 0;
        z-index: 99999;
        display: grid;
        place-items: center;
        padding: 24px;
        background: rgba(15, 29, 43, .58);
        backdrop-filter: blur(3px);
      }
      .pdf-progress-overlay[hidden], .report-audit-overlay[hidden] { display: none !important; }
      .pdf-progress-card, .report-audit-card {
        width: min(720px, 94vw);
        max-height: 90vh;
        overflow: auto;
        border-radius: 18px;
        background: #fff;
        box-shadow: 0 24px 80px rgba(0, 0, 0, .28);
        padding: 28px;
      }
      .pdf-progress-kicker, .report-audit-kicker {
        margin: 0 0 7px;
        color: #5d7184;
        font-size: 12px;
        font-weight: 800;
        letter-spacing: .08em;
        text-transform: uppercase;
      }
      .pdf-progress-title, .report-audit-title { margin: 0; color: #18364f; font-size: 24px; }
      .pdf-progress-stage { margin: 20px 0 5px; color: #244a73; font-size: 16px; font-weight: 800; }
      .pdf-progress-detail { min-height: 42px; margin: 0 0 17px; color: #647586; line-height: 1.45; }
      .pdf-progress-track { position: relative; height: 16px; overflow: hidden; border-radius: 999px; background: #e7edf2; }
      .pdf-progress-fill { width: 0; height: 100%; border-radius: inherit; background: linear-gradient(90deg, #244a73, #2f719f); transition: width .45s ease; }
      .pdf-progress-meta { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-top: 9px; color: #627486; font-size: 13px; }
      .pdf-progress-percent { color: #18364f; font-size: 20px; font-weight: 900; }
      .pdf-progress-timing { display:flex; justify-content:space-between; gap:12px; margin-top:14px; padding:10px 12px; border-radius:10px; background:#f5f8fa; color:#536a7d; font-size:12px; }
      .pdf-progress-timing strong { color:#18364f; }
      .pdf-progress-steps { margin-top:16px; display:grid; gap:7px; }
      .pdf-progress-step { display:grid; grid-template-columns:24px 1fr auto; align-items:center; gap:8px; padding:8px 10px; border-radius:9px; background:#f8fafc; color:#5d7184; font-size:12px; }
      .pdf-progress-step.current { background:#edf4fa; color:#244a73; font-weight:700; }
      .pdf-progress-step.done { color:#356b52; }
      .pdf-progress-step-icon { text-align:center; font-weight:900; }
      .pdf-progress-step-percent { color:#768898; font-variant-numeric:tabular-nums; }
      .pdf-progress-actions, .report-audit-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 20px; }
      .pdf-progress-card.error .pdf-progress-stage { color: #a73a3a; }
      .pdf-progress-card.error .pdf-progress-fill { background: #b94b4b; }
      .pdf-progress-card.done .pdf-progress-fill { background: #2c7b55; }
      .report-audit-state {
        display: inline-flex;
        align-items: center;
        margin: 14px 0 16px;
        padding: 7px 11px;
        border-radius: 999px;
        font-size: 12px;
        font-weight: 900;
        letter-spacing: .04em;
        background: #eef3f7;
        color: #244a73;
      }
      .report-audit-state.ok { background: #e7f5ed; color: #246445; }
      .report-audit-state.error { background: #fbeaea; color: #9a3434; }
      .report-audit-state.warning { background: #fff4db; color: #805d17; }
      .report-audit-intro { margin: 0 0 16px; color: #647586; line-height: 1.5; }
      .report-audit-table { width: 100%; border-collapse: collapse; font-size: 13px; }
      .report-audit-table th, .report-audit-table td { padding: 10px 9px; border-bottom: 1px solid #e4eaf0; vertical-align: top; text-align: left; }
      .report-audit-table th { color: #465d70; font-size: 12px; text-transform: uppercase; letter-spacing: .03em; }
      .report-audit-status { width: 48px; text-align: center !important; font-size: 17px; font-weight: 900; }
      .report-audit-detail { color: #687988; line-height: 1.4; }
      .report-audit-reconciliation { margin-top: 16px; padding: 12px 14px; border-radius: 10px; background: #f5f8fa; color: #536a7d; font-size: 13px; line-height: 1.5; }
      @media (max-width: 560px) {
        .pdf-progress-card, .report-audit-card { padding: 22px 18px; }
        .pdf-progress-title, .report-audit-title { font-size: 21px; }
      }
    `;
    document.head.appendChild(style);
  }

  function ensureProgressUI() {
    ensureStyles();
    let overlay = document.getElementById('pdf-progress-overlay');
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.id = 'pdf-progress-overlay';
      overlay.className = 'pdf-progress-overlay';
      overlay.hidden = true;
      overlay.innerHTML = `
        <section class="pdf-progress-card" role="dialog" aria-modal="true" aria-labelledby="pdf-progress-title">
          <p class="pdf-progress-kicker">Exportación institucional</p>
          <h2 class="pdf-progress-title" id="pdf-progress-title">Generando PDF</h2>
          <p class="pdf-progress-stage" id="pdf-progress-stage">Preparando generación</p>
          <p class="pdf-progress-detail" id="pdf-progress-detail">Espere mientras se prepara el informe.</p>
          <div class="pdf-progress-track" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0">
            <div class="pdf-progress-fill" id="pdf-progress-fill"></div>
          </div>
          <div class="pdf-progress-meta">
            <span>El porcentaje corresponde a etapas reales del generador.</span>
            <strong class="pdf-progress-percent" id="pdf-progress-percent">0 %</strong>
          </div>
          <div class="pdf-progress-timing">
            <span><strong id="pdf-progress-elapsed">Tiempo transcurrido: 00:00</strong></span>
            <span>No cierre Informtit mientras se genera el documento.</span>
          </div>
          <div class="pdf-progress-steps" id="pdf-progress-steps"></div>
          <div class="pdf-progress-actions">
            <button type="button" class="button primary" id="pdf-progress-download" hidden>Descargar PDF</button>
            <button type="button" class="button secondary" id="pdf-progress-close" hidden>Cerrar</button>
          </div>
        </section>`;
      document.body.appendChild(overlay);
      document.getElementById('pdf-progress-close').onclick = () => {
        if (!polling) overlay.hidden = true;
      };
      document.getElementById('pdf-progress-download').onclick = () => {
        void triggerPendingDownload();
      };
    }
    return overlay;
  }

  function ensureAuditUI() {
    ensureStyles();
    let overlay = document.getElementById('report-audit-overlay');
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.id = 'report-audit-overlay';
      overlay.className = 'report-audit-overlay';
      overlay.hidden = true;
      overlay.innerHTML = `
        <section class="report-audit-card" role="dialog" aria-modal="true" aria-labelledby="report-audit-title">
          <p class="report-audit-kicker">Control previo a emisión</p>
          <h2 class="report-audit-title" id="report-audit-title">Validación del informe</h2>
          <div id="report-audit-state" class="report-audit-state"></div>
          <p id="report-audit-intro" class="report-audit-intro"></p>
          <table class="report-audit-table">
            <thead><tr><th>Control</th><th class="report-audit-status">Estado</th><th>Detalle</th></tr></thead>
            <tbody id="report-audit-body"></tbody>
          </table>
          <div id="report-audit-reconciliation" class="report-audit-reconciliation"></div>
          <div class="report-audit-actions">
            <button type="button" class="button secondary" id="report-audit-cancel">Cerrar</button>
            <button type="button" class="button primary" id="report-audit-continue">Generar PDF</button>
          </div>
        </section>`;
      document.body.appendChild(overlay);
    }
    return overlay;
  }

  function auditSymbol(status) {
    if (status === 'ok') return '✓';
    if (status === 'error') return '✕';
    return '⚠';
  }

  function auditStateClass(audit) {
    if (audit.state === 'APTO PARA EMITIR' || audit.state === 'SIN POBLACIÓN') return 'ok';
    if (audit.state === 'ERROR DE CARGA') return 'error';
    return 'warning';
  }

  function auditIntro(audit) {
    if (audit.state === 'APTO PARA EMITIR') return 'La información superó los controles críticos. El documento puede emitirse como Informe Final.';
    if (audit.state === 'SIN POBLACIÓN') return 'La fuente confirma que esta modalidad no tiene población. Se generará un informe corto de ausencia de registros.';
    if (audit.state === 'ERROR DE CARGA') return 'Se detectaron errores bloqueantes. Corríjalos antes de generar el PDF.';
    return 'El documento contiene pendientes críticos. Puede generarse únicamente como Informe Preliminar.';
  }

  function showAudit(audit) {
    const overlay = ensureAuditUI();
    const stateNode = document.getElementById('report-audit-state');
    stateNode.className = `report-audit-state ${auditStateClass(audit)}`;
    stateNode.textContent = audit.state;
    document.getElementById('report-audit-intro').textContent = auditIntro(audit);
    document.getElementById('report-audit-body').innerHTML = (audit.controls || []).map(item => `
      <tr>
        <td><strong>${escapeHtml(item.name || '')}</strong></td>
        <td class="report-audit-status">${auditSymbol(item.status)}</td>
        <td class="report-audit-detail">${escapeHtml(item.detail || '')}</td>
      </tr>`).join('');

    const rec = audit.reconciliation || {};
    const reasons = rec.reasons || {};
    const reasonText = Object.entries(reasons)
      .filter(([, count]) => Number(count) > 0)
      .map(([reason, count]) => `${reason}: ${count}`)
      .join(' · ');
    const reconciliationLabel = audit.reconciliation_label || 'Conciliación de Núcleos';
    document.getElementById('report-audit-reconciliation').textContent = rec.imported !== undefined
      ? `${reconciliationLabel}: ${rec.imported} importados = ${rec.included} incluidos + ${rec.excluded} excluidos.${reasonText ? ` ${reasonText}.` : ''}`
      : `Sin ${reconciliationLabel.toLowerCase()} disponible.`;

    const continueButton = document.getElementById('report-audit-continue');
    continueButton.hidden = !audit.can_generate_pdf;
    continueButton.textContent = audit.final_ready
      ? 'Generar informe final'
      : audit.mode === 'no_population'
        ? 'Generar informe sin población'
        : 'Generar informe preliminar';
    overlay.hidden = false;
  }

  function confirmAudit(audit) {
    showAudit(audit);
    const overlay = ensureAuditUI();
    return new Promise(resolve => {
      const cancel = document.getElementById('report-audit-cancel');
      const proceed = document.getElementById('report-audit-continue');
      const finish = value => {
        overlay.hidden = true;
        cancel.onclick = null;
        proceed.onclick = null;
        resolve(value);
      };
      cancel.onclick = () => finish(false);
      proceed.onclick = () => finish(true);
    });
  }

  function formatElapsed(seconds) {
    const total = Math.max(0, Math.floor(Number(seconds || 0)));
    const minutes = Math.floor(total / 60);
    const remaining = total % 60;
    return `${String(minutes).padStart(2, '0')}:${String(remaining).padStart(2, '0')}`;
  }

  function updateElapsed(explicitSeconds = null) {
    const node = document.getElementById('pdf-progress-elapsed');
    if (!node) return;
    const seconds = explicitSeconds == null
      ? (progressStartedAt ? (Date.now() - progressStartedAt) / 1000 : 0)
      : Number(explicitSeconds || 0);
    node.textContent = `Tiempo transcurrido: ${formatElapsed(seconds)}`;
  }

  function startElapsedTimer() {
    progressStartedAt = Date.now();
    if (timerHandle) clearInterval(timerHandle);
    updateElapsed(0);
    timerHandle = setInterval(() => updateElapsed(), 500);
  }

  function stopElapsedTimer(explicitSeconds = null) {
    if (timerHandle) clearInterval(timerHandle);
    timerHandle = null;
    updateElapsed(explicitSeconds);
  }

  function renderProgressSteps(job) {
    const host = document.getElementById('pdf-progress-steps');
    if (!host) return;
    const steps = Array.isArray(job.steps) ? job.steps.slice(-8) : [];
    if (!steps.length) {
      const stage = job.stage || 'Preparando generación';
      host.innerHTML = `<div class="pdf-progress-step current"><span class="pdf-progress-step-icon">→</span><span>${escapeHtml(stage)}</span><span class="pdf-progress-step-percent">${Math.round(Number(job.progress || 0))}%</span></div>`;
      return;
    }
    host.innerHTML = steps.map((step, index) => {
      const isCurrent = index === steps.length - 1 && !['completed', 'error'].includes(job.status);
      const isDone = !isCurrent && job.status !== 'error';
      const icon = isCurrent ? '→' : isDone ? '✓' : '•';
      const klass = isCurrent ? 'current' : isDone ? 'done' : '';
      return `<div class="pdf-progress-step ${klass}">
        <span class="pdf-progress-step-icon">${icon}</span>
        <span>${escapeHtml(step.stage || '')}</span>
        <span class="pdf-progress-step-percent">${Math.round(Number(step.progress || 0))}%</span>
      </div>`;
    }).join('');
  }

  function setProgress(job) {
    const overlay = ensureProgressUI();
    const card = overlay.querySelector('.pdf-progress-card');
    const progress = Math.max(0, Math.min(100, Number(job.progress || 0)));
    const track = overlay.querySelector('.pdf-progress-track');
    overlay.hidden = false;
    card.classList.toggle('error', job.status === 'error');
    card.classList.toggle('done', job.status === 'completed');
    document.getElementById('pdf-progress-stage').textContent = job.stage || 'Generando PDF';
    const stalledDetail = job.stalled
      ? `La etapa no ha informado avances durante ${formatElapsed(job.seconds_without_progress || 0)}. Informtit sigue protegiendo el archivo; si continúa así, registre esta etapa para diagnóstico.`
      : '';
    document.getElementById('pdf-progress-detail').textContent = job.error || stalledDetail || job.detail || 'Procesando el informe.';
    document.getElementById('pdf-progress-fill').style.width = `${progress}%`;
    document.getElementById('pdf-progress-percent').textContent = `${Math.round(progress)} %`;
    track.setAttribute('aria-valuenow', String(Math.round(progress)));
    renderProgressSteps(job);
    if (job.status === 'completed' || job.status === 'error') {
      stopElapsedTimer(job.duration_seconds ?? job.elapsed_seconds ?? null);
    } else if (job.elapsed_seconds != null) {
      updateElapsed(job.elapsed_seconds);
    }
    document.getElementById('pdf-progress-close').hidden = !['completed', 'error'].includes(job.status);
    const downloadButton = document.getElementById('pdf-progress-download');
    if (downloadButton) downloadButton.hidden = !(job.status === 'completed' && pendingDownload);
  }

  function resetProgress() {
    const overlay = ensureProgressUI();
    const card = overlay.querySelector('.pdf-progress-card');
    card.classList.remove('error', 'done');
    overlay.hidden = false;
    startElapsedTimer();
    document.getElementById('pdf-progress-stage').textContent = 'Preparando generación';
    document.getElementById('pdf-progress-detail').textContent = 'Se está preparando el proceso de exportación.';
    document.getElementById('pdf-progress-fill').style.width = '1%';
    document.getElementById('pdf-progress-percent').textContent = '1 %';
    overlay.querySelector('.pdf-progress-track').setAttribute('aria-valuenow', '1');
    pendingDownload = null;
    document.getElementById('pdf-progress-close').hidden = true;
    const downloadButton = document.getElementById('pdf-progress-download');
    if (downloadButton) downloadButton.hidden = true;
    renderProgressSteps({status: 'running', progress: 1, stage: 'Preparando generación', steps: []});
  }

  async function downloadPdfUrl(url) {
    const response = await fetch(url, { cache: 'no-store' });
    if (!response.ok) {
      let message = `Error ${response.status} al descargar el PDF.`;
      const type = response.headers.get('content-type') || '';
      if (type.includes('application/json')) {
        const data = await response.json().catch(() => ({}));
        if (data?.error) message = data.error;
      }
      throw new Error(message);
    }

    const blob = await response.blob();
    if (!blob.size) throw new Error('El PDF generado está vacío.');

    const disposition = response.headers.get('content-disposition') || '';
    let filename = 'Informe_Titulacion.pdf';
    const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i);
    const regular = disposition.match(/filename="?([^";]+)"?/i);
    if (encoded?.[1]) {
      try { filename = decodeURIComponent(encoded[1]); } catch (_error) { filename = encoded[1]; }
    } else if (regular?.[1]) {
      filename = regular[1];
    }

    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = objectUrl;
    link.download = filename;
    link.style.display = 'none';
    document.body.appendChild(link);
    try {
      link.click();
    } finally {
      link.remove();
      setTimeout(() => URL.revokeObjectURL(objectUrl), 1500);
    }
    return { ok: true, canceled: false, path: '', filename };
  }

  async function savePdf(url, filename = 'Informe_Titulacion.pdf') {
    const desktop = window.informtitDesktop;
    if (desktop?.isElectron && typeof desktop.savePdf === 'function') {
      const result = await desktop.savePdf({ url, filename });
      if (result?.canceled) return { ok: false, canceled: true };
      if (!result?.ok) throw new Error(result?.error || 'Electron no pudo guardar el PDF.');
      return result;
    }
    return downloadPdfUrl(url);
  }

  function prepareDownload(url, filename = 'Informe_Titulacion.pdf') {
    pendingDownload = { url, filename };
    const button = document.getElementById('pdf-progress-download');
    if (button) button.hidden = false;
  }

  async function triggerPendingDownload() {
    if (!pendingDownload) return { ok: false, canceled: true };
    const button = document.getElementById('pdf-progress-download');
    if (button) {
      button.disabled = true;
      button.textContent = 'Guardando PDF…';
    }
    try {
      const result = await savePdf(pendingDownload.url, pendingDownload.filename);
      if (result?.canceled) {
        document.getElementById('pdf-progress-detail').textContent = 'El PDF está guardado en Informtit. Puede descargarlo cuando desee con el botón Descargar PDF.';
        return result;
      }
      const detail = result?.path
        ? `PDF guardado correctamente en: ${result.path}`
        : 'PDF descargado correctamente.';
      document.getElementById('pdf-progress-detail').textContent = detail;
      toast('PDF guardado correctamente.');
      return result;
    } catch (error) {
      document.getElementById('pdf-progress-detail').textContent = `El PDF sí fue generado y está guardado en Informtit, pero no se pudo copiar al destino: ${error.message}`;
      toast(`No se pudo guardar la copia del PDF: ${error.message}`, true);
      return { ok: false, canceled: false, error: error.message };
    } finally {
      if (button) {
        button.disabled = false;
        button.textContent = 'Descargar PDF';
        button.hidden = false;
      }
    }
  }

  async function pollJob(jobId) {
    polling = true;
    try {
      while (activeJobId === jobId) {
        const result = await api(`/api/pdf-jobs/${jobId}`);
        const job = result.job;
        setProgress(job);
        if (job.status === 'completed') {
          polling = false;
          activeJobId = null;
          prepareDownload(`/api/pdf-jobs/${jobId}/download`, job.filename || 'Informe_Titulacion.pdf');
          setProgress({
            ...job,
            detail: `PDF generado correctamente en ${formatElapsed(job.duration_seconds ?? job.elapsed_seconds ?? 0)}. Seleccione dónde desea guardar una copia.`,
          });

          const saved = await triggerPendingDownload();
          if (saved?.ok) {
            const completedOverlay = ensureProgressUI();
            setTimeout(() => {
              if (!polling && activeJobId === null) completedOverlay.hidden = true;
            }, 1400);
          }
          return;
        }
        if (job.status === 'error') {
          polling = false;
          activeJobId = null;
          toast(job.error || 'No se pudo generar el PDF.', true);
          return;
        }
        await new Promise(resolve => setTimeout(resolve, POLL_MS));
      }
    } catch (error) {
      polling = false;
      activeJobId = null;
      setProgress({ status: 'error', progress: 0, stage: 'No se pudo consultar el proceso PDF', error: error.message });
      toast(error.message, true);
    }
  }
  let startingPdf = false;

  async function generatePdf(reportId, button = null, label = 'PDF') {
    const id = Number(reportId || 0);
    if (!id) {
      toast('Abra un informe antes de generar el PDF.', true);
      return;
    }
    if (startingPdf || activeJobId) {
      toast('Ya se está generando un PDF. Espere a que termine.', true);
      return;
    }

    startingPdf = true;
    const originalText = button?.textContent || label;
    try {
      // Si nada cambió desde la última generación, descargar la copia persistente
      // de inmediato y evitar tanto la auditoría como la maquetación completa.
      try {
        const cacheResult = await api(`/api/reports/${id}/pdf-cache`);
        if (cacheResult?.cache?.available) {
          if (button) button.textContent = 'Descargando PDF guardado…';
          await downloadPdfUrl(`/api/reports/${id}/pdf-cache/download`);
          toast('PDF guardado descargado. No fue necesario regenerarlo.');
          return;
        }
      } catch (cacheError) {
        console.warn('[Informtit PDF cache] Se regenerará el documento:', cacheError);
      }

      // Feedback inmediato: la auditoría previa también puede tardar en informes
      // grandes y antes el usuario veía la pantalla inmóvil durante ese tiempo.
      resetProgress();
      document.getElementById('pdf-progress-title').textContent = `Preparando PDF ${label}`;
      setProgress({
        status: 'running',
        progress: 2,
        stage: 'Validando informe',
        detail: 'Revisando datos, balances y requisitos antes de iniciar la generación.',
        steps: [{stage: 'Validando informe', progress: 2}],
      });

      const auditResult = await api(`/api/reports/${id}/audit`);
      if (!auditResult?.audit) throw new Error('No se pudo validar el informe antes de generar el PDF.');
      const preflightToken = String(auditResult.preflight_token || '');
      stopElapsedTimer();
      ensureProgressUI().hidden = true;
      const proceed = await confirmAudit(auditResult.audit);
      if (!proceed) return;

      resetProgress();
      document.getElementById('pdf-progress-title').textContent = `Generando PDF ${label}`;
      if (button) {
        button.setAttribute('aria-disabled', 'true');
        button.style.pointerEvents = 'none';
        if ('disabled' in button) button.disabled = true;
        button.textContent = 'Generando PDF…';
      }

      const result = await api(`/api/reports/${id}/pdf-jobs`, {
        method: 'POST',
        body: JSON.stringify({ preflight_token: preflightToken }),
      });
      if (!result?.job?.id) throw new Error('El backend no devolvió un proceso de generación válido.');
      activeJobId = result.job.id;
      setProgress(result.job);
      await pollJob(activeJobId);
    } catch (error) {
      activeJobId = null;
      polling = false;
      setProgress({ status: 'error', progress: 0, stage: 'No se pudo iniciar la generación', error: error.message });
      toast(error.message, true);
    } finally {
      startingPdf = false;
      if (button) {
        button.removeAttribute('aria-disabled');
        button.style.pointerEvents = '';
        if ('disabled' in button) button.disabled = false;
        button.textContent = originalText;
      }
    }
  }

  window.informtitGeneratePdf = generatePdf;

  document.addEventListener('click', event => {
    const target = event.target instanceof Element ? event.target : null;
    const button = target?.closest('#export-pdf, [data-pdf-report-id]');
    if (!button) return;

    event.preventDefault();
    event.stopPropagation();

    const explicitId = Number(button.dataset.pdfReportId || 0);
    const reportId = explicitId || Number(state.activeReport?.id || 0);
    const label = button.dataset.pdfLabel || (explicitId ? 'del período' : 'del informe');
    void generatePdf(reportId, button, label);
  }, true);
})();
