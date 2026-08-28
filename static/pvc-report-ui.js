(() => {
  'use strict';

  function esc(value) {
    return String(value ?? '').replace(/[&<>"']/g, char => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[char]));
  }

  function isPvc() {
    const report = state?.activeReport;
    const project = report?.project_summary || {};
    return String(report?.report_type || project?.report_type || '').toLowerCase() === 'pvc';
  }

  function injectStyles() {
    if (document.getElementById('pvc-report-style')) return;
    const style = document.createElement('style');
    style.id = 'pvc-report-style';
    style.textContent = [
      '.pvc-shell{display:grid;gap:16px}',
      '.pvc-hero{padding:18px;border:1px solid #dbe4ec;border-radius:14px;background:#f8fafc}',
      '.pvc-hero h2{margin:0 0 6px}.pvc-hero p{margin:0;color:#5c7082}',
      '.pvc-metrics{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:10px}',
      '.pvc-metric{padding:12px;border:1px solid #dfe7ee;border-radius:11px;background:white}',
      '.pvc-metric span{display:block;font-size:11px;color:#6a7e8f}.pvc-metric strong{display:block;font-size:21px;margin-top:4px}',
      '.pvc-upload{padding:16px;border:1px solid #dfe7ee;border-radius:12px;background:white}',
      '.pvc-upload-actions{display:flex;gap:10px;align-items:center;flex-wrap:wrap}',
      '.pvc-file{padding:10px;border:1px dashed #aab9c6;border-radius:9px;min-width:280px}',
      '.pvc-alert{padding:10px 12px;border-radius:9px;background:#fff8e8;color:#76551f;margin-top:8px}',
      '.pvc-ok{background:#edf8f1;color:#245f43}',
      '.pvc-table-wrap{overflow:auto;max-height:580px;border:1px solid #e1e8ee;border-radius:10px}',
      '.pvc-table{width:100%;border-collapse:collapse;font-size:12px;background:white}',
      '.pvc-table th,.pvc-table td{padding:8px;border-bottom:1px solid #edf1f4;text-align:left;white-space:nowrap}',
      '.pvc-table th{position:sticky;top:0;background:#f5f8fa;z-index:1}',
      '.pvc-contract{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-top:12px}',
      '.pvc-contract div{padding:10px;border-radius:9px;background:#f5f8fa;font-size:12px}',
      '@media(max-width:1100px){.pvc-metrics{grid-template-columns:repeat(3,minmax(0,1fr))}}'
    ].join('');
    document.head.appendChild(style);
  }

  function fmt(value) {
    const number = Number(value);
    return value === null || value === undefined || value === '' || Number.isNaN(number)
      ? '—'
      : number.toFixed(2).replace('.', ',');
  }

  function metric(label, value) {
    return '<article class="pvc-metric"><span>' + esc(label) + '</span><strong>' + esc(value) + '</strong></article>';
  }

  function setPvcTabs() {
    const tabs = document.getElementById('report-tabs');
    if (!tabs || !isPvc()) return;
    ['nuclei', 'careers'].forEach(name => {
      const button = tabs.querySelector('[data-tab="' + name + '"]');
      if (button) button.hidden = true;
      const content = document.getElementById('tab-' + name);
      if (content) content.hidden = true;
    });
    const projects = tabs.querySelector('[data-tab="projects"]');
    if (projects) {
      projects.hidden = false;
      projects.textContent = 'Resultados PVC';
    }
    const modality = document.getElementById('report-modality');
    if (modality) modality.textContent = 'PVC · Artículo Científico';
    const pdf = document.getElementById('export-pdf');
    if (pdf) {
      pdf.style.display = '';
      pdf.textContent = 'PDF PVC';
      pdf.dataset.pdfLabel = 'PVC';
      pdf.href = '#';
    }
  }

  async function fileToDataUrl(file) {
    return await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ''));
      reader.onerror = () => reject(reader.error || new Error('No se pudo leer el archivo.'));
      reader.readAsDataURL(file);
    });
  }

  function summaryMarkup(data) {
    const s = data.summary || {};
    return [
      metric('Requisitos', s.requirements_total || 0),
      metric('Habilitados', s.eligible || 0),
      metric('Base PVC', s.pvc_total || 0),
      metric('Conciliados', s.matched || 0),
      metric('Evaluados', s.evaluated || 0),
      metric('Aprobación', Number(s.approval_pct || 0).toFixed(2) + ' %'),
      metric('No evaluados', s.not_evaluated || 0),
      metric('Promedio escrito', fmt(s.written_average)),
      metric('Promedio defensa', fmt(s.defense_average)),
      metric('Promedio final', fmt(s.final_average)),
      metric('Sin conciliar', s.unmatched || 0),
      metric('Alertas fórmula', s.formula_warnings || 0)
    ].join('');
  }

  function recordsMarkup(records) {
    if (!Array.isArray(records) || !records.length) {
      return '<div class="empty-mini">Todavía no existen resultados PVC cargados.</div>';
    }
    return '<div class="pvc-table-wrap"><table class="pvc-table"><thead><tr>' +
      '<th>Estudiante</th><th>Cédula</th><th>Carrera oficial</th><th>Sede</th>' +
      '<th>Tutor</th><th>Lector</th><th>Escrito</th><th>Defensa</th><th>Final</th>' +
      '<th>Estado</th><th>Conciliación</th><th>Fórmula</th></tr></thead><tbody>' +
      records.map(row => '<tr>' +
        '<td>' + esc(row.display_name || row.source_name || '') + '</td>' +
        '<td>' + esc(row.identification || '—') + '</td>' +
        '<td>' + esc(row.career_name || 'Sin conciliación') + '</td>' +
        '<td>' + esc(row.campus || '—') + '</td>' +
        '<td>' + esc(row.tutor_name || '—') + '</td>' +
        '<td>' + esc(row.reader_name || '—') + '</td>' +
        '<td>' + esc(fmt(row.written)) + '</td>' +
        '<td>' + esc(fmt(row.defense_source)) + '</td>' +
        '<td>' + esc(fmt(row.final_grade)) + '</td>' +
        '<td>' + esc(row.final_status || '') + '</td>' +
        '<td>' + esc(row.match_status || '') + '</td>' +
        '<td>' + esc(row.formula_status || '') + '</td>' +
      '</tr>').join('') +
      '</tbody></table></div>';
  }

  async function renderPvcModule(force = false) {
    if (!isPvc()) return;
    const tab = document.getElementById('tab-projects');
    const reportId = Number(state.activeReport?.id || 0);
    if (!tab || !reportId) return;
    if (!force && tab.dataset.pvcRenderedFor === String(reportId)) return;
    tab.dataset.pvcRenderedFor = String(reportId);
    tab.innerHTML = '<div class="panel"><div class="loading-state">Cargando resultados PVC...</div></div>';
    try {
      const data = await api('/api/reports/' + reportId + '/pvc/summary');
      const latest = data.latest_import;
      const s = data.summary || {};
      const periods = Object.keys(data.source_periods || {}).filter(Boolean).join(' · ') || 'No detectado';
      const workTypes = Object.keys(data.work_types || {}).filter(Boolean).join(' · ') || 'No detectado';
      tab.innerHTML =
        '<div class="pvc-shell">' +
          '<section class="pvc-hero"><h2>Resultados PVC · Artículo Científico</h2>' +
          '<p>Requisitos conserva la identidad, carrera y sede oficiales. La Base PVC aporta acta, tutor, lector, tribunal, rúbricas, defensa y calificación final.</p>' +
          '<div class="pvc-contract">' +
            '<div><strong>Fórmula de validación</strong><br>70 % trabajo escrito + 30 % defensa oral.</div>' +
            '<div><strong>Regla del informe</strong><br>Antes de cada tabla, gráfico, mapa o diagrama se genera contexto; después se genera el análisis correspondiente.</div>' +
          '</div></section>' +
          '<section class="pvc-upload"><div class="panel-head"><div><h2>Base de resultados PVC</h2>' +
            '<p>Cargue el archivo .xlsx institucional. Una nueva carga reemplaza únicamente los resultados PVC de este informe; Requisitos no se modifica.</p></div></div>' +
            '<div class="pvc-upload-actions"><input class="pvc-file" id="pvc-results-file" type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet">' +
            '<button class="button primary" type="button" id="pvc-import-button">Importar Base PVC</button>' +
            '<span id="pvc-import-state"></span></div>' +
            (latest ? '<div class="pvc-alert pvc-ok"><strong>Última carga:</strong> ' + esc(latest.filename || '') + ' · ' + esc(latest.total_rows || 0) + ' registros · período fuente: ' + esc(latest.source_period || 'no detectado') + '</div>' : '') +
            (s.unmatched ? '<div class="pvc-alert"><strong>Conciliación:</strong> ' + esc(s.unmatched) + ' registro(s) no coinciden de forma única con Requisitos.</div>' : '') +
            (s.formula_warnings ? '<div class="pvc-alert"><strong>Fórmula:</strong> ' + esc(s.formula_warnings) + ' registro(s) presentan diferencias superiores a la tolerancia de cálculo.</div>' : '') +
            '<div class="pvc-alert pvc-ok"><strong>Fuente detectada:</strong> período ' + esc(periods) + ' · tipo de trabajo: ' + esc(workTypes) + '.</div>' +
          '</section>' +
          '<section class="panel"><div class="panel-head"><div><h2>Indicadores PVC</h2><p>Los no evaluados se mantienen separados de los reprobados.</p></div></div>' +
            '<div class="pvc-metrics">' + summaryMarkup(data) + '</div></section>' +
          '<section class="panel"><div class="panel-head"><div><h2>Registros conciliados y resultados</h2>' +
            '<p>La carrera mostrada procede de Requisitos; una identidad sin coincidencia no se asigna automáticamente.</p></div></div>' +
            recordsMarkup(data.records) + '</section>' +
        '</div>';
      bindImport(reportId);
    } catch (error) {
      tab.innerHTML = '<div class="panel"><div class="empty-mini">' + esc(error.message || 'No se pudo cargar el módulo PVC.') + '</div></div>';
    }
  }

  function bindImport(reportId) {
    const button = document.getElementById('pvc-import-button');
    const input = document.getElementById('pvc-results-file');
    const stateNode = document.getElementById('pvc-import-state');
    if (!button || !input) return;
    button.onclick = async () => {
      const file = input.files?.[0];
      if (!file) {
        toast('Seleccione la Base de resultados PVC en formato .xlsx.', true);
        return;
      }
      button.disabled = true;
      if (stateNode) stateNode.textContent = 'Leyendo y conciliando...';
      try {
        const dataUrl = await fileToDataUrl(file);
        const result = await api('/api/reports/' + reportId + '/pvc/import', {
          method: 'POST',
          body: JSON.stringify({ data_url: dataUrl, filename: file.name })
        });
        toast(result.records + ' registros PVC procesados. ' + result.matched + ' conciliados por cédula.');
        const tab = document.getElementById('tab-projects');
        if (tab) delete tab.dataset.pvcRenderedFor;
        await renderPvcModule(true);
        if (typeof loadReports === 'function') await loadReports();
      } catch (error) {
        toast(error.message || 'No se pudo importar la Base PVC.', true);
        if (stateNode) stateNode.textContent = '';
      } finally {
        if (document.contains(button)) button.disabled = false;
      }
    };
  }

  function applyPvcUi() {
    if (!isPvc()) return;
    injectStyles();
    setPvcTabs();
    const active = document.querySelector('#report-tabs .tab.active');
    if (active?.dataset?.tab === 'projects') void renderPvcModule();
  }

  const previousRenderReport = renderReport;
  renderReport = function () {
    previousRenderReport();
    queueMicrotask(applyPvcUi);
  };

  document.addEventListener('click', event => {
    if (!isPvc()) return;
    const button = event.target instanceof Element ? event.target.closest('#report-tabs [data-tab="projects"]') : null;
    if (!button) return;
    setTimeout(() => void renderPvcModule(true), 0);
  }, true);

  document.addEventListener('informtit:students-domain-changed', () => {
    if (!isPvc()) return;
    const tab = document.getElementById('tab-projects');
    if (tab) delete tab.dataset.pvcRenderedFor;
  });

  queueMicrotask(applyPvcUi);
})();
