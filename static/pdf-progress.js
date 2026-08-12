// Barra de progreso de la generación del PDF.
(function () {
  if (window.__informtitPdfProgressInstalled) return;
  window.__informtitPdfProgressInstalled = true;

  const POLL_MS = 550;
  let activeJobId = null;
  let polling = false;

  function ensureUI() {
    if (!document.getElementById('pdf-progress-style')) {
      const style = document.createElement('style');
      style.id = 'pdf-progress-style';
      style.textContent = `
        .pdf-progress-overlay {
          position: fixed;
          inset: 0;
          z-index: 99999;
          display: grid;
          place-items: center;
          padding: 24px;
          background: rgba(15, 29, 43, .58);
          backdrop-filter: blur(3px);
        }
        .pdf-progress-overlay[hidden] { display: none !important; }
        .pdf-progress-card {
          width: min(620px, 94vw);
          border-radius: 18px;
          background: #fff;
          box-shadow: 0 24px 80px rgba(0, 0, 0, .28);
          padding: 28px;
        }
        .pdf-progress-kicker {
          margin: 0 0 7px;
          color: #5d7184;
          font-size: 12px;
          font-weight: 800;
          letter-spacing: .08em;
          text-transform: uppercase;
        }
        .pdf-progress-title {
          margin: 0;
          color: #18364f;
          font-size: 24px;
        }
        .pdf-progress-stage {
          margin: 20px 0 5px;
          color: #244a73;
          font-size: 16px;
          font-weight: 800;
        }
        .pdf-progress-detail {
          min-height: 42px;
          margin: 0 0 17px;
          color: #647586;
          line-height: 1.45;
        }
        .pdf-progress-track {
          position: relative;
          height: 16px;
          overflow: hidden;
          border-radius: 999px;
          background: #e7edf2;
        }
        .pdf-progress-fill {
          width: 0;
          height: 100%;
          border-radius: inherit;
          background: linear-gradient(90deg, #244a73, #2f719f);
          transition: width .45s ease;
        }
        .pdf-progress-meta {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 16px;
          margin-top: 9px;
          color: #627486;
          font-size: 13px;
        }
        .pdf-progress-percent {
          color: #18364f;
          font-size: 20px;
          font-weight: 900;
        }
        .pdf-progress-actions {
          display: flex;
          justify-content: flex-end;
          margin-top: 20px;
        }
        .pdf-progress-card.error .pdf-progress-stage { color: #a73a3a; }
        .pdf-progress-card.error .pdf-progress-fill { background: #b94b4b; }
        .pdf-progress-card.done .pdf-progress-fill { background: #2c7b55; }
        @media (max-width: 560px) {
          .pdf-progress-card { padding: 22px 18px; }
          .pdf-progress-title { font-size: 21px; }
        }
      `;
      document.head.appendChild(style);
    }

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

  function setProgress(job) {
    const overlay = ensureUI();
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
    const overlay = ensureUI();
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

    resetProgress();
    const button = document.getElementById('export-pdf');
    if (button) {
      button.setAttribute('aria-disabled', 'true');
      button.style.pointerEvents = 'none';
      button.textContent = 'Generando PDF…';
    }

    try {
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
