(() => {
  'use strict';

  function esc(value = '') {
    if (typeof escapeHtml === 'function') return escapeHtml(value);
    return String(value).replace(/[&<>'"]/g, char => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
    }[char]));
  }

  function currentReport() {
    return typeof state !== 'undefined' ? (state.activeReport || null) : null;
  }

  function isPvc(report) {
    const project = report?.project_summary;
    return String(project?.report_type || report?.report_type || '').toLowerCase() === 'pvc';
  }

  function generationTargets() {
    const report = currentReport();
    if (!report) return [];
    const project = report.project_summary || {};
    if (isPvc(report)) {
      return [{
        reportId: Number(report.id || 0),
        label: 'PVC',
        description: 'Informe único de Titulación – Modalidad Artículo Científico.',
        disabled: !Number(report.id || 0),
      }];
    }

    if (project?.period_project_id) {
      return [
        {
          reportId: Number(project.presencial_report_id || 0),
          label: 'Presencial',
          description: `${Number(project.presencial_students || 0)} estudiantes en la población Presencial.`,
          disabled: !project.presencial_report_id || Number(project.presencial_students || 0) === 0,
        },
        {
          reportId: Number(project.online_report_id || 0),
          label: 'Online',
          description: `${Number(project.online_students || 0)} estudiantes en la población Online.`,
          disabled: !project.online_report_id || Number(project.online_students || 0) === 0,
        },
      ];
    }

    return [{
      reportId: Number(report.id || 0),
      label: report.modality === 'en_linea' ? 'Online' : 'Presencial',
      description: 'Genera una nueva versión con los datos actuales del informe.',
      disabled: !Number(report.id || 0),
    }];
  }

  function ensureDialogs() {
    if (!document.getElementById('generate-pdfs-dialog')) {
      const dialog = document.createElement('dialog');
      dialog.id = 'generate-pdfs-dialog';
      dialog.className = 'generated-pdf-dialog';
      dialog.innerHTML = `
        <div class="dialog-form">
          <div class="dialog-head">
            <div>
              <h2>Generar informes</h2>
              <p>Esta acción siempre crea una nueva versión del PDF con los datos actuales.</p>
            </div>
            <button type="button" class="icon-button" data-close-generate aria-label="Cerrar">×</button>
          </div>
          <div id="generate-pdfs-content"></div>
          <div class="dialog-actions">
            <button type="button" class="button secondary" data-close-generate>Cerrar</button>
          </div>
        </div>`;
      document.body.appendChild(dialog);
      dialog.querySelectorAll('[data-close-generate]').forEach(button => {
        button.addEventListener('click', () => dialog.close());
      });
    }

    if (!document.getElementById('generated-pdfs-dialog')) {
      const dialog = document.createElement('dialog');
      dialog.id = 'generated-pdfs-dialog';
      dialog.className = 'generated-pdf-dialog';
      dialog.innerHTML = `
        <div class="dialog-form">
          <div class="dialog-head">
            <div>
              <h2>PDFs generados</h2>
              <p>Descargue versiones ya creadas. Descargar nunca vuelve a generar el informe.</p>
            </div>
            <button type="button" class="icon-button" data-close-generated aria-label="Cerrar">×</button>
          </div>
          <div id="generated-pdfs-content"></div>
          <div class="dialog-actions">
            <button type="button" class="button secondary" id="refresh-generated-pdfs">Actualizar</button>
            <button type="button" class="button secondary" data-close-generated>Cerrar</button>
          </div>
        </div>`;
      document.body.appendChild(dialog);
      dialog.querySelectorAll('[data-close-generated]').forEach(button => {
        button.addEventListener('click', () => dialog.close());
      });
      dialog.querySelector('#refresh-generated-pdfs')?.addEventListener('click', () => {
        void renderGeneratedList(true);
      });
    }
  }

  function openGenerateDialog() {
    const report = currentReport();
    if (!report) {
      toast('Abra un informe antes de generar PDFs.', true);
      return;
    }
    ensureDialogs();
    const targets = generationTargets();
    const container = document.getElementById('generate-pdfs-content');
    container.innerHTML = `
      <div class="generated-summary">
        <span>${esc(report.period || '')}</span>
        <span>${isPvc(report) ? 'PVC' : 'Presencial + Online'}</span>
      </div>
      <div class="pdf-action-grid">
        ${targets.map(target => `
          <article class="pdf-action-card">
            <h3>PDF ${esc(target.label)}</h3>
            <p>${esc(target.description)}</p>
            <p><strong>Generar</strong> crea una nueva versión aunque ya exista un PDF anterior.</p>
            <button type="button"
              class="button primary"
              data-generate-report-id="${target.reportId}"
              data-generate-label="${esc(target.label)}"
              ${target.disabled ? 'disabled aria-disabled="true"' : ''}>
              Generar nueva versión
            </button>
          </article>
        `).join('')}
      </div>`;

    container.querySelectorAll('[data-generate-report-id]').forEach(button => {
      button.addEventListener('click', () => {
        const id = Number(button.dataset.generateReportId || 0);
        const label = button.dataset.generateLabel || 'PDF';
        if (!id || typeof window.informtitGeneratePdf !== 'function') {
          toast('El generador PDF no está disponible.', true);
          return;
        }
        void window.informtitGeneratePdf(id, button, label);
      });
    });

    document.getElementById('generate-pdfs-dialog').showModal();
  }

  function formatGeneratedDate(value) {
    if (!value) return '—';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return new Intl.DateTimeFormat('es-EC', {
      dateStyle: 'short',
      timeStyle: 'medium',
    }).format(date);
  }

  function formatBytes(value) {
    const bytes = Number(value || 0);
    if (!bytes) return '—';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  }

  async function browserDownload(url, filename) {
    const response = await fetch(url, { cache: 'no-store' });
    if (!response.ok) {
      let message = `Error ${response.status} al descargar el PDF.`;
      try {
        const data = await response.json();
        if (data?.error) message = data.error;
      } catch (_error) {}
      throw new Error(message);
    }
    const blob = await response.blob();
    if (!blob.size) throw new Error('El PDF está vacío.');
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = objectUrl;
    link.download = filename || 'Informe_Titulacion.pdf';
    link.style.display = 'none';
    document.body.appendChild(link);
    try {
      link.click();
    } finally {
      link.remove();
      setTimeout(() => URL.revokeObjectURL(objectUrl), 1500);
    }
    return { ok: true };
  }

  async function downloadGenerated(item, button) {
    const reportId = Number(item.report_id || 0);
    const artifactId = String(item.artifact_id || '');
    const url = `/api/reports/${reportId}/generated-pdfs/${artifactId}/download`;
    const original = button?.textContent || 'Descargar';
    if (button) {
      button.disabled = true;
      button.textContent = 'Preparando…';
    }
    try {
      const desktop = window.informtitDesktop;
      let result;
      if (desktop?.isElectron && typeof desktop.savePdf === 'function') {
        result = await desktop.savePdf({
          url,
          filename: item.filename || 'Informe_Titulacion.pdf',
        });
      } else {
        result = await browserDownload(url, item.filename || 'Informe_Titulacion.pdf');
      }
      if (result?.canceled) {
        toast('Descarga cancelada. El PDF continúa guardado en Informtit.');
        return;
      }
      toast('PDF descargado correctamente.');
    } catch (error) {
      toast(`No se pudo descargar el PDF: ${error.message}`, true);
    } finally {
      if (button) {
        button.disabled = false;
        button.textContent = original;
      }
    }
  }

  async function deleteGenerated(item, button) {
    const label = item.filename || 'este PDF';
    if (!confirm(`¿Eliminar del historial «${label}»? Esta acción no regenera ni modifica los demás PDFs.`)) return;
    const original = button?.textContent || 'Eliminar';
    if (button) {
      button.disabled = true;
      button.textContent = 'Eliminando…';
    }
    try {
      await api(`/api/reports/${Number(item.report_id)}/generated-pdfs/${item.artifact_id}`, {
        method: 'DELETE',
        body: JSON.stringify({}),
      });
      toast('PDF eliminado del historial.');
      await renderGeneratedList(true);
    } catch (error) {
      toast(error.message, true);
    } finally {
      if (button && button.isConnected) {
        button.disabled = false;
        button.textContent = original;
      }
    }
  }

  let generatedCache = null;
  let generatedCacheReportId = 0;

  async function renderGeneratedList(force = false) {
    const report = currentReport();
    const container = document.getElementById('generated-pdfs-content');
    if (!report || !container) return;

    const reportId = Number(report.id || 0);
    if (!force && generatedCache && generatedCacheReportId === reportId) {
      drawGeneratedList(container, generatedCache);
      return;
    }

    container.innerHTML = '<div class="generated-empty">Cargando PDFs generados…</div>';
    try {
      const data = await api(`/api/reports/${reportId}/generated-pdfs`);
      generatedCache = Array.isArray(data?.generated_pdfs) ? data.generated_pdfs : [];
      generatedCacheReportId = reportId;
      drawGeneratedList(container, generatedCache);
    } catch (error) {
      container.innerHTML = `<div class="generated-empty">No se pudo cargar el historial: ${esc(error.message)}</div>`;
    }
  }

  function drawGeneratedList(container, items) {
    const counts = {
      vigente: items.filter(item => item.status === 'vigente').length,
      historico: items.filter(item => item.status === 'historico').length,
      desactualizado: items.filter(item => item.status === 'desactualizado').length,
    };
    if (!items.length) {
      container.innerHTML = `
        <div class="generated-empty">
          <strong>Todavía no hay PDFs generados.</strong><br><br>
          Use «Generar informes» para crear la primera versión.
        </div>`;
      return;
    }

    container.innerHTML = `
      <div class="generated-summary">
        <span>${items.length} versiones</span>
        <span>${counts.vigente} vigentes</span>
        <span>${counts.historico} históricas</span>
        <span>${counts.desactualizado} desactualizadas</span>
      </div>
      <div class="generated-table-wrap">
        <table class="generated-table">
          <thead>
            <tr>
              <th>Modalidad</th>
              <th>Generado</th>
              <th>Estado</th>
              <th>Versión</th>
              <th>Archivo</th>
              <th>Tamaño</th>
              <th>Acciones</th>
            </tr>
          </thead>
          <tbody>
            ${items.map((item, index) => `
              <tr>
                <td><strong>${esc(item.modality_label || '—')}</strong></td>
                <td>${esc(formatGeneratedDate(item.generated_at))}</td>
                <td>
                  <span class="generated-status ${esc(item.status || 'historico')}">${esc(item.status || 'histórico')}</span>
                  ${item.stale_reason ? `<div class="generated-warning">${esc(item.stale_reason)}</div>` : ''}
                </td>
                <td>${esc(item.version || '1.0')}</td>
                <td>${esc(item.filename || 'Informe.pdf')}</td>
                <td>${esc(formatBytes(item.size))}</td>
                <td>
                  <div class="generated-actions">
                    <button type="button" class="button primary small" data-download-generated="${index}">Descargar</button>
                    <button type="button" class="button danger small" data-delete-generated="${index}">Eliminar</button>
                  </div>
                </td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>`;

    container.querySelectorAll('[data-download-generated]').forEach(button => {
      button.addEventListener('click', () => {
        const item = items[Number(button.dataset.downloadGenerated)];
        if (item) void downloadGenerated(item, button);
      });
    });
    container.querySelectorAll('[data-delete-generated]').forEach(button => {
      button.addEventListener('click', () => {
        const item = items[Number(button.dataset.deleteGenerated)];
        if (item) void deleteGenerated(item, button);
      });
    });
  }

  function openGeneratedDialog() {
    const report = currentReport();
    if (!report) {
      toast('Abra un informe antes de consultar PDFs generados.', true);
      return;
    }
    ensureDialogs();
    document.getElementById('generated-pdfs-dialog').showModal();
    void renderGeneratedList(true);
  }

  function ensureMainActions() {
    const workspace = document.getElementById('report-workspace');
    if (!workspace || workspace.hidden) return;
    const generate = document.getElementById('open-generate-pdfs');
    const generated = document.getElementById('open-generated-pdfs');
    if (generate) generate.hidden = false;
    if (generated) generated.hidden = false;
    const legacy = document.getElementById('export-pdf');
    if (legacy && legacy.style.display !== 'none') legacy.style.display = 'none';
    const periodActions = document.getElementById('period-pdf-actions');
    if (periodActions && periodActions.style.display !== 'none') periodActions.style.display = 'none';
  }

  ensureDialogs();

  document.getElementById('open-generate-pdfs')?.addEventListener('click', openGenerateDialog);
  document.getElementById('open-generated-pdfs')?.addEventListener('click', openGeneratedDialog);

  document.addEventListener('informtit:pdf-generated', () => {
    generatedCache = null;
    generatedCacheReportId = 0;
    const dialog = document.getElementById('generated-pdfs-dialog');
    if (dialog?.open) void renderGeneratedList(true);
  });

  const observer = new MutationObserver(() => ensureMainActions());
  observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['hidden', 'style'] });
  ensureMainActions();

  window.informtitOpenGeneratePdfs = openGenerateDialog;
  window.informtitOpenGeneratedPdfs = openGeneratedDialog;
})();
