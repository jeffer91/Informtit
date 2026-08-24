// Auditoría previa y barra de progreso de la generación del PDF.
(function () {
  if (window.__informtitPdfProgressInstalled) return;
  window.__informtitPdfProgressInstalled = true;

  const POLL_MS = 550;
  let activeJobId = null;
  let polling = false;

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
            <span>Puede tardar varios minutos en informes extensos.</span>
            <strong class="pdf-progress-percent" id="pdf-progress-percent">0 %</strong>
          </div>
          <div class="pdf-progress-actions">
            <button type="button" class="button secondary" id="pdf-progress-close" hidden>Cerrar</button>
          </div>
        </section>`;
      document.body.appendChild(overlay);
      document.getElementById('pdf-progress-close').onclick = () => {
        if (!polling) overlay.hidden = true;
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
    document.getElementById('report-audit-reconciliation').textContent = rec.imported !== undefined
      ? `Conciliación de Núcleos: ${rec.imported} importados = ${rec.included} incluidos + ${rec.excluded} excluidos.${reasonText ? ` ${reasonText}.` : ''}`
      : 'Sin conciliación de Núcleos disponible.';

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

  function setProgress(job) {
    const overlay = ensureProgressUI();
    const card = overlay.querySelector('.pdf-progress-card');
    const progress = Math.max(0, Math.min(100, Number(job.progress || 0)));
    const track = overlay.querySelector('.pdf-progress-track');
    overlay.hidden = false;
    card.classList.toggle('error', job.status === 'error');
    card.classList.toggle('done', job.status === 'completed');
    document.getElementById('pdf-progress-stage').textContent = job.stage || 'Generando PDF';
    document.getElementById('pdf-progress-detail').textContent = job.error || job.detail || 'Procesando el informe.';
    document.getElementById('pdf-progress-fill').style.width = `${progress}%`;
    document.getElementById('pdf-progress-percent').textContent = `${Math.round(progress)} %`;
    track.setAttribute('aria-valuenow', String(Math.round(progress)));
    document.getElementById('pdf-progress-close').hidden = !['completed', 'error'].includes(job.status);
  }

  function resetProgress() {
    const overlay = ensureProgressUI();
    const card = overlay.querySelector('.pdf-progress-card');
    card.classList.remove('error', 'done');
    overlay.hidden = false;
    document.getElementById('pdf-progress-stage').textContent = 'Preparando generación';
    document.getElementById('pdf-progress-detail').textContent = 'Se está preparando el proceso de exportación.';
    document.getElementById('pdf-progress-fill').style.width = '1%';
    document.getElementById('pdf-progress-percent').textContent = '1 %';
    overlay.querySelector('.pdf-progress-track').setAttribute('aria-valuenow', '1');
    document.getElementById('pdf-progress-close').hidden = true;
  }

  function downloadJob(jobId) {
    const link = document.createElement('a');
    link.href = `/api/pdf-jobs/${jobId}/download`;
    link.download = '';
    link.style.display = 'none';
    document.body.appendChild(link);
    link.click();
    link.remove();
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
          downloadJob(jobId);
          toast('PDF generado correctamente.');
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
      setProgress({ status: 'error', progress: 0, stage: 'No se pudo consultar el progreso', error: error.message });
      toast(error.message, true);
    }
  }

  async function startPdf(event) {
    event.preventDefault();
    event.stopPropagation();
    if (activeJobId) return;
    const reportId = Number(state.activeReport?.id || 0);
    if (!reportId) {
      toast('Abra un informe antes de generar el PDF.', true);
      return;
    }

    const button = document.getElementById('export-pdf');
    try {
      const auditResult = await api(`/api/reports/${reportId}/audit`);
      const proceed = await confirmAudit(auditResult.audit);
      if (!proceed) return;

      resetProgress();
      if (button) {
        button.setAttribute('aria-disabled', 'true');
        button.style.pointerEvents = 'none';
        button.textContent = 'Generando PDF…';
      }
      const result = await api(`/api/reports/${reportId}/pdf-jobs`, { method: 'POST', body: '{}' });
      activeJobId = result.job.id;
      setProgress(result.job);
      await pollJob(activeJobId);
    } catch (error) {
      activeJobId = null;
      polling = false;
      setProgress({ status: 'error', progress: 0, stage: 'No se pudo iniciar la generación', error: error.message });
      toast(error.message, true);
    } finally {
      if (button) {
        button.removeAttribute('aria-disabled');
        button.style.pointerEvents = '';
        button.textContent = 'PDF';
      }
    }
  }

  document.addEventListener('click', event => {
    const button = event.target.closest('#export-pdf');
    if (button) startPdf(event);
  }, true);
})();