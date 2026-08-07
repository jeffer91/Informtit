(() => {
  let scheduled = false;
  let requestId = 0;

  function esc(value = '') {
    return typeof escapeHtml === 'function'
      ? escapeHtml(String(value))
      : String(value).replace(/[&<>"']/g, character => ({
          '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;',
        })[character]);
  }

  function compareText(left, right) {
    return String(left || '').localeCompare(String(right || ''), 'es', { sensitivity: 'base' });
  }

  function courseMatchMarkup(items) {
    if (!items.length) return '';
    const ordered = [...items].sort((left, right) =>
      compareText(left.career_name, right.career_name)
      || Number(left.nucleus_number || 0) - Number(right.nucleus_number || 0)
    );
    const totalRead = ordered.reduce((sum, item) => sum + Number(item.read_students || 0), 0);
    const totalMatched = ordered.reduce((sum, item) => sum + Number(item.matched_students || 0), 0);
    const totalUnmatched = ordered.reduce((sum, item) => sum + Number(item.unmatched_students || 0), 0);
    return `<section class="nuclei-crosscheck" data-nuclei-crosscheck>
      <div class="panel-head">
        <div>
          <h3>Cruce de cursos cargados con la base de estudiantes</h3>
          <p>Esta tabla confirma cuántos estudiantes leyó Informtit en cada núcleo y cuántos pudo vincular con la base principal.</p>
        </div>
        <span class="badge ${totalUnmatched ? 'crosscheck-warning' : ''}">${totalMatched} de ${totalRead} vinculados</span>
      </div>
      <div class="student-table-wrap">
        <table class="student-table compact-table">
          <thead><tr><th>Carrera</th><th>Núcleo</th><th>Docente</th><th>Leídos</th><th>Vinculados</th><th>Sin coincidencia</th></tr></thead>
          <tbody>${ordered.map(item => `<tr>
            <td>${esc(item.career_name)}</td>
            <td>Núcleo ${Number(item.nucleus_number || 0)}</td>
            <td>${esc(item.teacher_name || 'Pendiente')}</td>
            <td>${Number(item.read_students || 0)}</td>
            <td><strong>${Number(item.matched_students || 0)}</strong></td>
            <td class="${Number(item.unmatched_students || 0) ? 'crosscheck-fail' : ''}">${Number(item.unmatched_students || 0)}</td>
          </tr>`).join('')}</tbody>
          <tfoot><tr><th colspan="3">Total</th><th>${totalRead}</th><th>${totalMatched}</th><th>${totalUnmatched}</th></tr></tfoot>
        </table>
      </div>
    </section>`;
  }

  async function enhance() {
    const reportId = Number(state.activeReport?.id || 0);
    const panel = document.querySelector('[data-eligibility-panel]');
    if (!reportId || !panel) return;

    const headingText = 'Consolidado acumulado de los cuatro núcleos';
    const descriptionText = 'La matriz reúne todos los cursos de núcleos guardados. Una nota en Núcleo 2 proviene de un curso de Núcleo 2 cargado anteriormente; no se genera a partir del texto de Núcleo 1.';
    const heading = panel.querySelector('.panel-head h2');
    const description = panel.querySelector('.panel-head p');
    if (heading && heading.textContent !== headingText) heading.textContent = headingText;
    if (description && description.textContent !== descriptionText) description.textContent = descriptionText;

    const details = panel.querySelector('.eligibility-details');
    if (details && !panel.querySelector('[data-cumulative-note]')) {
      details.insertAdjacentHTML('beforebegin', `<div class="nuclei-cumulative-note" data-cumulative-note>
        <strong>Cómo leer esta matriz:</strong> se muestran 15 estudiantes por página y una carrera a la vez. El curso recién pegado puede contener más estudiantes distribuidos en las páginas siguientes. Para revisar únicamente las personas y notas del texto pegado, abra <strong>Núcleos guardados → Ver calificaciones</strong>. Revise también el cuadro de cruce para confirmar el total leído y vinculado.
      </div>`);
    }

    const currentRequest = ++requestId;
    try {
      const data = await api(`/api/reports/${reportId}/nuclei/eligibility`);
      if (currentRequest !== requestId || Number(state.activeReport?.id || 0) !== reportId) return;
      const signature = JSON.stringify(data.course_matches || []);
      if (panel.dataset.courseMatchSignature === signature) return;
      panel.querySelector('[data-nuclei-crosscheck]')?.remove();
      const resultTable = panel.querySelector('h3 + .student-table-wrap');
      const markup = courseMatchMarkup(data.course_matches || []);
      if (markup) {
        if (resultTable) resultTable.insertAdjacentHTML('afterend', markup);
        else panel.insertAdjacentHTML('beforeend', markup);
      }
      panel.dataset.courseMatchSignature = signature;
    } catch (_error) {
      // La matriz principal continúa disponible aunque falle este resumen adicional.
    }
  }

  function schedule() {
    if (scheduled) return;
    scheduled = true;
    setTimeout(() => {
      scheduled = false;
      enhance();
    }, 120);
  }

  function mutationContainsPanel(record) {
    return [...record.addedNodes].some(node => {
      if (!(node instanceof Element)) return false;
      return node.matches?.('[data-eligibility-panel]') || Boolean(node.querySelector?.('[data-eligibility-panel]'));
    });
  }

  document.addEventListener('click', event => {
    if (event.target.closest('[data-tab="nuclei"]')) schedule();
  });
  new MutationObserver(records => {
    if (records.some(mutationContainsPanel)) schedule();
  }).observe(document.body, { childList: true, subtree: true });
  schedule();

  const style = document.createElement('style');
  style.textContent = `
    .nuclei-cumulative-note {
      margin: 14px 0;
      padding: 13px 15px;
      border: 1px solid #bfdbfe;
      border-radius: 12px;
      background: #eff6ff;
      color: #1e3a5f;
      line-height: 1.45;
    }
    .nuclei-crosscheck { margin: 20px 0; padding: 16px; border: 1px solid #dbe4ee; border-radius: 16px; background: #f8fafc; }
    .nuclei-crosscheck .panel-head { margin-bottom: 12px; }
    .nuclei-crosscheck h3 { margin: 0 0 4px; }
    .nuclei-crosscheck p { margin: 0; color: #64748b; }
    .crosscheck-warning { background: #fff1d6 !important; color: #925f00 !important; }
    .crosscheck-fail { color: #b42318; font-weight: 800; }
    .nuclei-crosscheck tfoot th { background: #eef3f7; }
  `;
  document.head.appendChild(style);
})();
