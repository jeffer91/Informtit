(() => {
  'use strict';

  if (!/(^|\.)github\.io$/i.test(window.location.hostname)) return;

  const form = document.getElementById('report-form');
  if (!form) return;

  const typeSelect = form.elements.report_type;
  const legacyBuilder = form.querySelector('.report-period-builder');
  const dialogHeadText = form.querySelector('.dialog-head p');
  const outputNote = document.getElementById('report-output-note');
  const help = document.getElementById('report-type-help');
  const periodPreview = document.getElementById('report-period-preview');
  const namePreview = document.getElementById('report-name-preview');
  const submit = document.getElementById('create-report-submit');

  const selectorSection = document.createElement('section');
  selectorSection.id = 'firebase-report-period-selector';
  selectorSection.className = 'report-period-builder';
  selectorSection.innerHTML = `
    <div class="report-field-label">Periodo académico</div>
    <label style="display:block;margin-top:8px">
      Seleccione un periodo existente en Firebase
      <select id="firebase-report-period" required>
        <option value="">Cargando periodos...</option>
      </select>
    </label>
    <div class="report-derived-preview" style="margin-top:12px">
      <span>Periodo seleccionado</span>
      <strong id="firebase-report-period-label">—</strong>
    </div>`;

  if (legacyBuilder) {
    legacyBuilder.hidden = true;
    legacyBuilder.insertAdjacentElement('beforebegin', selectorSection);
  } else {
    form.querySelector('.form-grid')?.insertAdjacentElement('afterend', selectorSection);
  }

  const periodSelect = selectorSection.querySelector('#firebase-report-period');
  const selectedLabel = selectorSection.querySelector('#firebase-report-period-label');
  let periods = [];

  if (dialogHeadText) {
    dialogHeadText.textContent = 'Seleccione el tipo de informe y un periodo existente en Firebase.';
  }

  function clean(value) {
    return String(value ?? '').trim();
  }

  function normalizeType(value) {
    return clean(value).toLowerCase() === 'pvc' ? 'pvc' : 'normal';
  }

  function exactLabel(period) {
    return clean(period?.label || period?.periodoId || period?._id);
  }

  function parseCanonicalPeriodId(value) {
    const match = /^(\d{4})-(\d{2})__(\d{4})-(\d{2})$/.exec(clean(value));
    if (!match) return null;
    return {
      startYear: Number(match[1]),
      startMonth: Number(match[2]),
      endYear: Number(match[3]),
      endMonth: Number(match[4]),
    };
  }

  function currentPeriod() {
    return periods.find(item => clean(item.periodoId || item._id) === clean(periodSelect.value)) || null;
  }

  function setLegacyPeriodFields(period) {
    const id = clean(period?.periodoId || period?._id);
    const parsed = parseCanonicalPeriodId(id);
    if (!parsed) return;
    if (form.elements.period_start_month) form.elements.period_start_month.value = String(parsed.startMonth);
    if (form.elements.period_start_year) form.elements.period_start_year.value = String(parsed.startYear);
    if (form.elements.period_end_month) form.elements.period_end_month.value = String(parsed.endMonth);
    if (form.elements.period_end_year) form.elements.period_end_year.value = String(parsed.endYear);
  }

  function ensureFirebasePeriodInput() {
    let input = form.elements.firebase_period_id;
    if (!input) {
      input = document.createElement('input');
      input.type = 'hidden';
      input.name = 'firebase_period_id';
      form.appendChild(input);
    }
    return input;
  }

  function applySelectedPeriod() {
    const period = currentPeriod();
    if (!period) {
      selectedLabel.textContent = '—';
      if (submit) submit.disabled = true;
      return;
    }

    const label = exactLabel(period);
    const id = clean(period.periodoId || period._id);
    setLegacyPeriodFields(period);

    // Dejar que el código existente actualice el código institucional y demás
    // campos derivados, pero restaurar después el label exacto de Firebase.
    if (typeof window.refreshDerivedReportFields === 'function') {
      try { window.refreshDerivedReportFields(); } catch (_) {}
    }

    if (form.elements.period) form.elements.period.value = label;
    if (form.elements.name) {
      form.elements.name.value = `Informe Final del Proceso de Titulación - ${label}`;
    }
    ensureFirebasePeriodInput().value = id;

    selectedLabel.textContent = label;
    if (periodPreview) periodPreview.textContent = label;
    if (namePreview) namePreview.textContent = `Informe Final del Proceso de Titulación - ${label}`;
    if (submit) submit.disabled = false;
  }

  function compatiblePeriods() {
    const wanted = normalizeType(typeSelect?.value);
    return periods.filter(period => normalizeType(period.report_type) === wanted);
  }

  function renderOptions({ preserve = true } = {}) {
    const previous = preserve ? clean(periodSelect.value) : '';
    const compatible = compatiblePeriods();

    if (!compatible.length) {
      periodSelect.innerHTML = '<option value="">No hay periodos de este tipo en Firebase</option>';
      periodSelect.disabled = true;
      selectedLabel.textContent = '—';
      if (submit) submit.disabled = true;
      return;
    }

    periodSelect.disabled = false;
    periodSelect.innerHTML = compatible.map(period => {
      const id = clean(period.periodoId || period._id);
      const label = exactLabel(period);
      return `<option value="${id.replace(/&/g, '&amp;').replace(/"/g, '&quot;')}">${label.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')}</option>`;
    }).join('');

    if (previous && compatible.some(period => clean(period.periodoId || period._id) === previous)) {
      periodSelect.value = previous;
    }
    applySelectedPeriod();
  }

  async function loadPeriods() {
    periodSelect.disabled = true;
    periodSelect.innerHTML = '<option value="">Cargando periodos...</option>';
    selectedLabel.textContent = 'Consultando Firebase...';
    if (submit) submit.disabled = true;

    try {
      let data;
      if (window.informtitFirebasePages?.listPeriods) {
        const rows = await window.informtitFirebasePages.listPeriods();
        data = { periods: rows };
      } else {
        const response = await fetch('/api/firebase/periods', { cache: 'no-store' });
        data = await response.json();
        if (!response.ok || data?.ok === false) throw new Error(data?.error || `Error ${response.status}`);
      }
      periods = Array.isArray(data?.periods) ? data.periods.filter(item => item && item.activo !== false) : [];
      renderOptions({ preserve: true });
    } catch (error) {
      periods = [];
      periodSelect.innerHTML = '<option value="">No se pudieron cargar los periodos</option>';
      selectedLabel.textContent = clean(error?.message) || 'No se pudo consultar Firebase.';
      periodSelect.disabled = true;
      if (submit) submit.disabled = true;
    }
  }

  function refreshTypePresentation() {
    const pvc = normalizeType(typeSelect?.value) === 'pvc';
    if (outputNote) outputNote.textContent = pvc ? 'PVC · un solo informe' : 'Presencial + Online';
    if (help) {
      help.textContent = pvc
        ? 'PVC usa un periodo existente de Firebase y genera un único informe.'
        : 'Regular usa un periodo existente de Firebase y genera Presencial + Online.';
    }
    renderOptions({ preserve: false });
  }

  periodSelect.addEventListener('change', applySelectedPeriod);
  typeSelect?.addEventListener('change', refreshTypePresentation);

  form.addEventListener('submit', () => {
    applySelectedPeriod();
  }, true);

  document.addEventListener('click', event => {
    const target = event.target instanceof Element ? event.target : null;
    const button = target?.closest('#new-report-btn, #new-pvc-report-btn');
    if (!button) return;
    window.setTimeout(async () => {
      const wanted = button.id === 'new-pvc-report-btn' ? 'pvc' : 'normal';
      if (typeSelect) typeSelect.value = wanted;
      if (!periods.length) await loadPeriods();
      else refreshTypePresentation();
    }, 0);
  }, true);

  loadPeriods();
})();
