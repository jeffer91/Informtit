// Importación unificada y tolerante para bases antiguas y modernas.
(function () {
  'use strict';

  if (window.__informtitRobustImportUiInstalled) return;
  window.__informtitRobustImportUiInstalled = true;

  let activePreview = null;
  let analyzing = false;
  let committing = false;

  const supported = '.xls,.xlsx,.csv,.tsv,.html,.htm,.xml';

  function projectSummary() {
    return state?.activeReport?.project_summary || null;
  }

  function isUnifiedPeriod() {
    const project = projectSummary();
    return !!project && String(project.report_type || '').toLowerCase() !== 'pvc';
  }

  function metric(label, value, hint = '') {
    return `<article class="metric roster-metric"><span>${escapeHtml(label)}</span><strong>${value}</strong>${hint ? `<small>${escapeHtml(hint)}</small>` : ''}</article>`;
  }

  function currentReportId() {
    return Number(state?.activeReport?.id || 0);
  }

  function enhanceDialog() {
    const dialog = document.getElementById('active-report-import-dialog');
    if (!dialog) return;

    const title = dialog.querySelector('.dialog-head h2');
    const subtitle = dialog.querySelector('.dialog-head p');
    if (title) title.textContent = 'Cargar base de requisitos';
    if (subtitle) subtitle.textContent = 'Una sola carga detectará el formato y separará automáticamente Presencial y Online.';

    const context = document.getElementById('active-report-context');
    const project = projectSummary();
    if (context && isUnifiedPeriod()) {
      context.innerHTML = `<strong>${escapeHtml(project?.name || state.activeReport?.name || 'Informe del proceso de titulación')}</strong><span>Período académico · Presencial + Online</span>`;
    }

    const input = document.getElementById('active-roster-file');
    if (input) input.accept = supported;

    const drop = dialog.querySelector('label.file-drop');
    if (drop) {
      const strong = drop.querySelector('strong');
      const span = drop.querySelector('span');
      if (strong) strong.textContent = 'Seleccione el archivo de requisitos';
      if (span) span.textContent = '.xls, .xlsx, .csv, .tsv, .html, .htm o .xml';
    }

    const warning = dialog.querySelector('.replace-warning');
    if (warning && isUnifiedPeriod()) {
      warning.innerHTML = `
        <strong>La carga actualizará la base del período completo.</strong>
        <span>Informtit conservará una sola fuente y separará internamente los registros Presencial y Online.</span>`;
    }
  }

  function renderCareers(preview) {
    const box = document.getElementById('active-career-preview');
    if (!box) return;
    const presencial = Array.isArray(preview?.careers?.presencial) ? preview.careers.presencial : [];
    const online = Array.isArray(preview?.careers?.en_linea) ? preview.careers.en_linea : [];
    const rows = [
      ...presencial.map(item => ({ ...item, modality: 'Presencial' })),
      ...online.map(item => ({ ...item, modality: 'Online' })),
    ];
    box.innerHTML = rows.length
      ? rows.map(item => `
          <div>
            <span><small style="display:inline-block;margin-right:6px;font-weight:800;color:#246691">${item.modality}</small>${escapeHtml(item.name || '')}</span>
            <strong>${Number(item.students || 0)}</strong>
          </div>`).join('')
      : '<div class="empty-mini">No se encontraron carreras válidas en el archivo.</div>';
  }

  function renderPreview(preview) {
    const uploadStep = document.getElementById('active-import-upload-step');
    const confirmStep = document.getElementById('active-import-confirm-step');
    if (uploadStep) uploadStep.hidden = true;
    if (confirmStep) confirmStep.hidden = false;

    const recognized = document.getElementById('active-recognized-file');
    if (recognized) {
      const encoding = preview.encoding && preview.encoding !== 'Binario' ? ` · ${preview.encoding}` : '';
      recognized.textContent = `${preview.filename || ''} · ${preview.file_type || 'Formato reconocido'}${encoding}`;
    }

    const metrics = document.getElementById('active-import-metrics');
    if (metrics) {
      metrics.innerHTML = [
        ['Registros del archivo', Number(preview.total || 0), 'Total detectado'],
        ['Presencial', Number(preview.presencial || 0), 'Estudiantes'],
        ['Online', Number(preview.en_linea || 0), 'Estudiantes'],
        ['Carreras detectadas', Number(preview.careers_total || 0), 'Presencial + Online'],
        ['Modalidad ambigua', Number(preview.ambiguous_modality || 0), 'Revisar si es mayor a 0'],
      ].map(([label, value, hint]) => metric(label, value, hint)).join('');
    }

    const note = document.getElementById('active-modality-note');
    const total = Number(preview.total || 0);
    const presencial = Number(preview.presencial || 0);
    const online = Number(preview.en_linea || 0);
    const ambiguous = Number(preview.ambiguous_modality || 0);
    if (note) {
      if (!total || !presencial || !online) {
        note.innerHTML = '<strong>Error de población:</strong> no se reconocieron correctamente ambas modalidades. Revise las columnas Carrera/Código antes de importar.';
        note.style.background = '#fff0ee';
        note.style.color = '#91382f';
      } else if (ambiguous > 0) {
        note.innerHTML = `<strong>Clasificación completada con advertencias:</strong> ${presencial} Presencial + ${online} Online = ${total}. Hay ${ambiguous} registro(s) sin indicador explícito de modalidad; Informtit los marcó con confianza baja.`;
        note.style.background = '#fff8e8';
        note.style.color = '#76551f';
      } else {
        note.innerHTML = `<strong>Clasificación verificada:</strong> ${presencial} estudiantes Presencial + ${online} estudiantes Online = ${total} registros.`;
        note.style.background = '#edf8f1';
        note.style.color = '#245f43';
      }
    }

    renderCareers(preview);

    const form = document.getElementById('active-report-import-form');
    const periodInput = form?.elements?.namedItem('period');
    if (periodInput) periodInput.value = preview.period || state.activeReport?.period || '';

    const commit = document.getElementById('commit-active-roster');
    if (commit) {
      const valid = total > 0 && presencial > 0 && online > 0;
      commit.disabled = !valid;
      commit.textContent = valid ? 'Importar Presencial + Online' : 'Revise la clasificación antes de importar';
    }
  }

  async function analyzeUnified(event) {
    if (!isUnifiedPeriod() || analyzing) return;
    event.preventDefault();
    event.stopImmediatePropagation();

    const file = document.getElementById('active-roster-file')?.files?.[0];
    if (!file) {
      toast('Seleccione primero un archivo de requisitos.', true);
      return;
    }

    analyzing = true;
    const button = document.getElementById('analyze-active-roster');
    if (button) {
      button.disabled = true;
      button.textContent = 'Analizando...';
    }

    try {
      const dataURL = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = () => reject(reader.error || new Error('No se pudo leer el archivo seleccionado.'));
        reader.readAsDataURL(file);
      });

      const data = await api('/api/imports/preview', {
        method: 'POST',
        body: JSON.stringify({ data_url: dataURL, original_name: file.name }),
      });
      activePreview = data.preview;
      renderPreview(activePreview);
    } catch (error) {
      console.error('[Informtit][Importacion robusta] Error:', error);
      toast(error.message || 'No se pudo analizar el archivo.', true);
    } finally {
      analyzing = false;
      if (button) {
        button.disabled = false;
        button.textContent = 'Analizar archivo';
      }
    }
  }

  async function commitUnified(event) {
    if (!isUnifiedPeriod() || committing) return;
    event.preventDefault();
    event.stopImmediatePropagation();

    if (!activePreview?.token) {
      toast('Primero analice el archivo.', true);
      return;
    }

    const reportId = currentReportId();
    if (!reportId) {
      toast('No hay un período activo.', true);
      return;
    }

    const form = document.getElementById('active-report-import-form');
    const button = document.getElementById('commit-active-roster');
    committing = true;
    if (button) {
      button.disabled = true;
      button.textContent = 'Importando Presencial + Online...';
    }

    const value = name => form?.elements?.namedItem(name)?.value || '';
    try {
      const result = await api(`/api/reports/${reportId}/imports/${activePreview.token}/commit`, {
        method: 'POST',
        body: JSON.stringify({
          period: value('period'),
          version: value('version'),
          elaboration_date: value('elaboration_date'),
          code: value('code'),
        }),
      });

      document.getElementById('active-report-import-dialog')?.close();
      activePreview = null;
      toast(`${Number(result.presencial || 0)} Presencial + ${Number(result.en_linea || 0)} Online importados correctamente.`);
      await loadReports();
      await openReport(reportId);
      document.querySelector('.tab[data-tab="roster"]')?.click();
    } catch (error) {
      console.error('[Informtit][Importacion robusta] Error al guardar:', error);
      toast(error.message || 'No se pudo guardar la importación.', true);
    } finally {
      committing = false;
      if (button) {
        button.disabled = false;
        button.textContent = 'Importar Presencial + Online';
      }
    }
  }

  document.addEventListener('submit', event => {
    if (event.target?.id !== 'active-report-import-form') return;
    const confirmStep = document.getElementById('active-import-confirm-step');
    if (confirmStep && !confirmStep.hidden) return;
    void analyzeUnified(event);
  }, true);

  document.addEventListener('click', event => {
    const target = event.target?.closest?.('#commit-active-roster');
    if (!target) return;
    void commitUnified(event);
  }, true);

  document.addEventListener('change', event => {
    if (event.target?.id !== 'active-roster-file') return;
    activePreview = null;
    enhanceDialog();
  });

  const observer = new MutationObserver(() => enhanceDialog());
  observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['open'] });
  enhanceDialog();
})();
