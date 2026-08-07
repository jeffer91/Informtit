(() => {
  let requestSequence = 0;
  let renderGeneration = 0;

  function esc(value = '') {
    return typeof escapeHtml === 'function'
      ? escapeHtml(String(value))
      : String(value).replace(/[&<>"']/g, character => ({
          '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;',
        })[character]);
  }

  function normalize(value = '') {
    return String(value)
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, ' ')
      .trim();
  }

  function parseNumber(value = '') {
    const text = String(value).trim().replace('%', '').replace(',', '.');
    if (!text || text === '—') return null;
    const number = Number(text);
    return Number.isFinite(number) ? number : null;
  }

  function flowMarkup(data) {
    const s = data.summary || {};
    return `<section class="workflow-flow" data-workflow-flow>
      <div class="workflow-flow-head">
        <div>
          <h3>Flujo de habilitación del estudiante</h3>
          <p>Los estudiantes avanzan de una etapa a la siguiente únicamente cuando cumplen la condición anterior.</p>
        </div>
      </div>
      <div class="workflow-steps">
        <article><span>1</span><strong>Requisitos previos</strong><small>${Number(s.eligible_for_nuclei || 0)} habilitados para Núcleos</small></article>
        <i>→</i>
        <article><span>2</span><strong>4 Núcleos</strong><small>${Number(s.eligible_for_complexive || 0)} habilitados para Complexivo</small></article>
        <i>→</i>
        <article><span>3</span><strong>Examen Complexivo</strong><small>${Number(s.complexive_project_approved || 0)} con aprobación Complexivo/Proyecto</small></article>
        <i>→</i>
        <article><span>4</span><strong>Títulos cargados</strong><small>${Number(s.titles_uploaded || 0)} con Aprobación de Titulación</small></article>
      </div>
      <p class="workflow-rule"><strong>Requisitos de ingreso a Núcleos:</strong> Académico, Documentación, Inglés, Financiero, Actualización de datos, Seguimiento a graduados, Prácticas y Vinculación.</p>
    </section>`;
  }

  function blockedMarkup(rows) {
    if (!rows.length) return '';
    return `<details class="eligibility-details workflow-blocked" data-workflow-blocked>
      <summary>${rows.length} estudiante${rows.length === 1 ? '' : 's'} fuera de Núcleos por requisitos previos</summary>
      <div class="student-table-wrap">
        <table class="student-table compact-table">
          <thead><tr><th>Cédula</th><th>Estudiante</th><th>Carrera</th><th>Requisitos pendientes</th><th>Estado</th></tr></thead>
          <tbody>${rows.map(row => `<tr>
            <td>${esc(row.identification || '—')}</td>
            <td>${esc(row.full_name)}</td>
            <td>${esc(row.career_name)}</td>
            <td>${esc((row.missing_requirements || []).join(', ') || 'Información incompleta')}</td>
            <td><span class="workflow-blocked-status">No habilitado para Núcleos</span></td>
          </tr>`).join('')}</tbody>
        </table>
      </div>
    </details>`;
  }

  function enhanceNucleiPanel(data) {
    const panel = document.querySelector('[data-eligibility-panel]');
    if (!panel) return;
    const signature = JSON.stringify({
      summary: data.summary,
      blocked: data.rows.filter(row => row.option === 'No habilitado para Núcleos').map(row => [row.student_id, row.missing_requirements]),
    });
    if (panel.dataset.workflowSignature === signature) return;

    panel.querySelector('[data-workflow-flow]')?.remove();
    panel.querySelector('[data-workflow-blocked]')?.remove();
    const head = panel.querySelector('.panel-head');
    head?.insertAdjacentHTML('afterend', flowMarkup(data));

    const summaryItems = [...panel.querySelectorAll(':scope > .summary-grid .summary-item')];
    const labels = [
      ['Ingresaron a Núcleos', data.summary.eligible_for_nuclei],
      ['Habilitados para Complexivo', data.summary.eligible_for_complexive],
      ['Núcleos reprobados', data.summary.not_habilitated],
      ['Núcleos pendientes', data.summary.pending],
      ['Trabajo de Titulación', data.summary.thesis_students],
      ['Habilitación desde Núcleos', `${Number(data.summary.habilitation_percentage || 0).toFixed(2).replace('.', ',')} %`],
    ];
    summaryItems.forEach((item, index) => {
      if (!labels[index]) return;
      const span = item.querySelector('span');
      const strong = item.querySelector('strong');
      if (span) span.textContent = labels[index][0];
      if (strong) strong.textContent = labels[index][1];
    });

    const matrix = panel.querySelector('.eligibility-table');
    if (matrix) {
      const rowById = new Map(data.rows.map(row => [String(row.identification || ''), row]));
      [...matrix.querySelectorAll('tbody tr')].forEach(tr => {
        const cells = tr.querySelectorAll('td');
        const source = rowById.get(cells[0]?.textContent?.trim() || '');
        if (!source) return;
        const statusCell = cells[cells.length - 1];
        if (statusCell) {
          const badge = statusCell.querySelector('.eligibility-status');
          if (badge) badge.textContent = source.stage_status || source.status;
        }
      });
    }

    const blocked = data.rows.filter(row => row.option === 'No habilitado para Núcleos');
    if (blocked.length) panel.insertAdjacentHTML('beforeend', blockedMarkup(blocked));
    panel.dataset.workflowSignature = signature;
  }

  function eligibleKey(row) {
    return `${normalize(row.career_name)}|${normalize(row.full_name)}`;
  }

  function recomputeCareerSummary(card) {
    const rows = [...card.querySelectorAll('.student-table tbody tr')].filter(row => !row.hidden && row.querySelectorAll('td').length >= 8);
    const summary = card.querySelector('.summary-grid');
    const stateNode = card.querySelector('[id^="career-state-"]');
    if (!summary) return;

    let approved = 0;
    let failed = 0;
    let supplementary = 0;
    const finals = [];
    rows.forEach(row => {
      const cells = row.querySelectorAll('td');
      const status = normalize(cells[7]?.textContent || '');
      if (status === 'aprobado') approved += 1;
      else if (status === 'reprobado') failed += 1;
      if (parseNumber(cells[4]?.textContent) !== null || parseNumber(cells[5]?.textContent) !== null) supplementary += 1;
      const final = parseNumber(cells[6]?.textContent);
      if (final !== null) finals.push(final);
    });
    const average = finals.length ? finals.reduce((sum, value) => sum + value, 0) / finals.length : null;
    const pct = rows.length ? approved / rows.length * 100 : 0;
    summary.innerHTML = [
      ['Habilitados', rows.length],
      ['Aprobados', approved],
      ['Reprobados', failed],
      ['Supletorios', supplementary],
      ['Promedio', average === null ? '—' : average.toFixed(2).replace('.', ',')],
    ].map(([label, value]) => `<div class="summary-item"><span>${label}</span><strong>${value}</strong></div>`).join('');
    if (stateNode) stateNode.textContent = `${rows.length} estudiantes habilitados · ${pct.toFixed(2).replace('.', ',')} % de aprobación final`;
  }

  function filterComplexiveTab(data) {
    const tab = document.querySelector('#tab-careers');
    if (!tab) return;
    const eligible = new Set((data.complexive_rows || []).map(eligibleKey));

    let note = tab.querySelector('[data-complexive-gate-note]');
    if (!note) {
      note = document.createElement('div');
      note.className = 'complexive-gate-note';
      note.dataset.complexiveGateNote = '1';
      note.innerHTML = '<strong>Lista filtrada:</strong> aquí solo se muestran estudiantes que cumplieron los ocho requisitos previos y aprobaron los cuatro núcleos con mínimo 7,00.';
      tab.querySelector('.panel-head')?.insertAdjacentElement('afterend', note);
    }

    tab.querySelectorAll('.career-card').forEach(card => {
      const career = card.querySelector('.career-head h3')?.textContent?.trim() || '';
      const body = card.querySelector('.student-table tbody');
      if (!body) return;
      let visible = 0;
      [...body.querySelectorAll('tr')].forEach(row => {
        const firstCell = row.querySelector('td');
        const name = firstCell?.textContent?.trim() || '';
        if (!name || row.querySelectorAll('td').length < 8) return;
        const allowed = eligible.has(`${normalize(career)}|${normalize(name)}`);
        row.hidden = !allowed;
        if (allowed) visible += 1;
      });
      card.hidden = visible === 0;
      if (visible) recomputeCareerSummary(card);
    });

    const visibleCards = [...tab.querySelectorAll('.career-card')].filter(card => !card.hidden);
    let empty = tab.querySelector('[data-no-complexive-eligible]');
    if (!visibleCards.length) {
      if (!empty) {
        empty = document.createElement('div');
        empty.className = 'empty-mini';
        empty.dataset.noComplexiveEligible = '1';
        empty.textContent = 'No existen estudiantes habilitados para el Examen Complexivo con la secuencia completa de requisitos y núcleos.';
        tab.querySelector('#career-list')?.appendChild(empty);
      }
    } else {
      empty?.remove();
    }
  }

  async function enhance() {
    const reportId = Number(state.activeReport?.id || 0);
    if (!reportId) return;
    const request = ++requestSequence;
    try {
      const data = await api(`/api/reports/${reportId}/nuclei/eligibility`);
      if (request !== requestSequence || Number(state.activeReport?.id || 0) !== reportId) return;
      enhanceNucleiPanel(data);
      filterComplexiveTab(data);
    } catch (_error) {
      // Las vistas originales permanecen disponibles si el cruce aún no puede generarse.
    }
  }

  function scheduleEnhancements() {
    const generation = ++renderGeneration;
    [120, 350, 800, 1400, 2200].forEach(delay => {
      setTimeout(() => {
        if (generation !== renderGeneration) return;
        enhance();
      }, delay);
    });
  }

  const previousRenderReport = renderReport;
  renderReport = function renderReportWithWorkflow() {
    previousRenderReport();
    scheduleEnhancements();
  };

  document.addEventListener('click', event => {
    if (event.target.closest('[data-tab="nuclei"], [data-tab="careers"]')) {
      setTimeout(enhance, 120);
      setTimeout(enhance, 700);
    }
  });
  window.addEventListener('informtit:nuclei-career-change', () => setTimeout(enhance, 80));
  scheduleEnhancements();

  const style = document.createElement('style');
  style.textContent = `
    .workflow-flow { margin: 16px 0 18px; padding: 16px; border: 1px solid #cbdbe8; border-radius: 16px; background: #f8fbfd; }
    .workflow-flow-head h3 { margin: 0 0 4px; }
    .workflow-flow-head p { margin: 0; color: #64748b; }
    .workflow-steps { display: grid; grid-template-columns: 1fr auto 1fr auto 1fr auto 1fr; gap: 10px; align-items: stretch; margin-top: 14px; }
    .workflow-steps article { display: grid; gap: 5px; padding: 13px; border: 1px solid #d7e2eb; border-radius: 13px; background: white; }
    .workflow-steps article > span { display: grid; place-items: center; width: 27px; height: 27px; border-radius: 999px; background: #1f5d85; color: white; font-size: 12px; font-weight: 800; }
    .workflow-steps article strong { color: #173b57; }
    .workflow-steps article small { color: #64748b; line-height: 1.35; }
    .workflow-steps > i { align-self: center; font-style: normal; font-size: 20px; color: #7890a3; }
    .workflow-rule { margin: 14px 0 0; padding-top: 12px; border-top: 1px solid #dbe4ec; color: #3f5364; line-height: 1.45; }
    .workflow-blocked { margin-top: 16px; }
    .workflow-blocked-status { display: inline-flex; padding: 4px 8px; border-radius: 999px; background: #fff0ed; color: #a73525; font-size: 11px; font-weight: 800; }
    .complexive-gate-note { margin: 12px 0 18px; padding: 13px 15px; border: 1px solid #b9d8c4; border-radius: 12px; background: #f0f8f3; color: #23563a; line-height: 1.45; }
    @media (max-width: 1050px) {
      .workflow-steps { grid-template-columns: 1fr; }
      .workflow-steps > i { transform: rotate(90deg); justify-self: center; }
    }
  `;
  document.head.appendChild(style);
})();
