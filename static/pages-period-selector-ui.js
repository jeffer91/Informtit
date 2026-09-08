(() => {
  'use strict';

  if (!/(^|\.)github\.io$/i.test(location.hostname) || !window.InformtitSheets) return;
  const form = document.getElementById('report-form');
  if (!form) return;

  const typeSelect = form.elements.report_type;
  const legacyBuilder = form.querySelector('.report-period-builder');
  const outputNote = document.getElementById('report-output-note');
  const help = document.getElementById('report-type-help');
  const periodPreview = document.getElementById('report-period-preview');
  const namePreview = document.getElementById('report-name-preview');
  const codePreview = document.getElementById('report-code-preview');
  const submit = document.getElementById('create-report-submit');
  let periods = [];

  const clean = value => String(value ?? '').trim();
  const fold = value => clean(value).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toUpperCase().replace(/\s+/g, ' ');
  const typeOf = value => clean(value).toLowerCase() === 'pvc' ? 'pvc' : 'normal';
  const labelOf = row => clean(row?.nombre || row?.label || row?.periodoId || row?.id);
  const idOf = row => clean(row?.periodoId || row?.id);

  function parseCanonical(value) {
    const m = /^(\d{4})-(\d{2})__(\d{4})-(\d{2})$/.exec(clean(value));
    return m ? { sy:+m[1], sm:+m[2], ey:+m[3], em:+m[4] } : null;
  }
  function inferredType(row) {
    const explicit = clean(row?.report_type || row?.tipo).toLowerCase();
    if (explicit === 'pvc') return 'pvc';
    if (explicit === 'normal' || explicit === 'regular') return 'normal';
    const p = parseCanonical(idOf(row));
    if (!p) return 'normal';
    return ((p.sm === 4 && p.em === 9) || (p.sm === 10 && p.em === 3)) ? 'normal' : 'pvc';
  }
  function reportMonth(row) {
    const p = parseCanonical(idOf(row));
    if (!p) return '';
    const index = p.sy * 12 + (p.sm - 1) + 2;
    return `${Math.floor(index/12)}-${String((index%12)+1).padStart(2,'0')}`;
  }
  function codeFor(row, modality='presencial') {
    const ym = reportMonth(row); if (!ym) return '';
    return `UTET-INF-${modality === 'en_linea' ? '02' : '01'}-PRO-95-${ym}`;
  }
  function today() {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
  }

  const selector = document.createElement('section');
  selector.id = 'sheets-report-period-selector';
  selector.className = 'report-period-builder';
  selector.innerHTML = `
    <div class="report-field-label">Período académico</div>
    <label style="display:block;margin-top:8px">Seleccione un período de Google Sheets
      <select id="sheets-report-period" required><option value="">Cargando períodos…</option></select>
    </label>
    <small id="sheets-period-source" style="display:block;margin-top:6px;color:#64748b">Fuente principal: Google Sheets</small>`;
  if (legacyBuilder) {
    legacyBuilder.hidden = true;
    legacyBuilder.style.setProperty('display','none','important');
    legacyBuilder.querySelectorAll('input,select,button').forEach(node => { node.tabIndex = -1; });
    legacyBuilder.insertAdjacentElement('beforebegin', selector);
  }
  const select = selector.querySelector('#sheets-report-period');

  function hiddenInput(name) {
    let input = form.elements.namedItem(name);
    if (!input) { input = document.createElement('input'); input.type='hidden'; input.name=name; form.appendChild(input); }
    return input;
  }

  function compatible() {
    const wanted = typeOf(typeSelect?.value);
    return periods.filter(row => inferredType(row) === wanted);
  }

  function renderOptions(preserve=true) {
    const previous = preserve ? clean(select.value) : '';
    const rows = compatible();
    if (!rows.length) {
      select.innerHTML = '<option value="">No hay períodos compatibles en Google Sheets</option>';
      select.disabled = true; if (submit) submit.disabled = true; return;
    }
    select.disabled = false;
    select.innerHTML = rows.map(row => `<option value="${idOf(row).replace(/&/g,'&amp;').replace(/"/g,'&quot;')}">${labelOf(row).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}</option>`).join('');
    if (previous && rows.some(row => idOf(row) === previous)) select.value = previous;
    apply();
  }

  function apply() {
    const row = periods.find(item => idOf(item) === clean(select.value));
    if (!row) { if (submit) submit.disabled = true; return; }
    const label = labelOf(row), id = idOf(row), pvc = typeOf(typeSelect?.value) === 'pvc';
    if (form.elements.period) form.elements.period.value = label;
    if (form.elements.name) form.elements.name.value = `Informe Final del Proceso de Titulación - ${label}`;
    hiddenInput('firebase_period_id').value = id;
    hiddenInput('periodoId').value = id;
    const codeP = codeFor(row,'presencial'), codeO = codeFor(row,'en_linea'), ym = reportMonth(row);
    if (form.elements.code_month && ym) form.elements.code_month.value = ym;
    if (form.elements.code) form.elements.code.value = codeP;
    if (form.elements.version) form.elements.version.value = '1.0';
    if (form.elements.elaboration_date) form.elements.elaboration_date.value = today();
    if (periodPreview) periodPreview.textContent = label;
    if (namePreview) namePreview.textContent = `Informe Final del Proceso de Titulación - ${label}`;
    if (codePreview) codePreview.innerHTML = pvc ? (codeP || '—') : (codeP ? `Presencial: ${codeP}<br>Online: ${codeO}` : '—');
    if (submit) submit.disabled = false;
  }

  function refreshType() {
    const pvc = typeOf(typeSelect?.value) === 'pvc';
    if (outputNote) outputNote.textContent = pvc ? 'PVC · Artículo Académico' : 'Presencial + Online';
    if (help) help.textContent = pvc
      ? 'PVC utiliza un período de Google Sheets y trabaja con Artículo Académico.'
      : 'Regular utiliza un período de Google Sheets y consolida Presencial + Online.';
    renderOptions(false);
  }

  async function load() {
    select.disabled = true;
    try {
      const data = await window.InformtitSheets.periodos();
      periods = (Array.isArray(data?.periodos) ? data.periodos : []).filter(row => row && row.activo !== false && fold(row.activo) !== 'NO');
      renderOptions(false);
    } catch (error) {
      periods = [];
      select.innerHTML = `<option value="">Google Sheets no respondió</option>`;
      selector.querySelector('#sheets-period-source').textContent = clean(error?.message) || 'No se pudieron leer los períodos.';
      if (submit) submit.disabled = true;
    }
  }

  select.addEventListener('change', apply);
  typeSelect?.addEventListener('change', refreshType);
  document.addEventListener('click', event => {
    const button = event.target.closest?.('#new-report-btn,#new-pvc-report-btn');
    if (!button) return;
    setTimeout(() => {
      if (typeSelect) typeSelect.value = button.id === 'new-pvc-report-btn' ? 'pvc' : 'normal';
      refreshType();
    },0);
  }, true);
  form.addEventListener('submit', apply, true);
  void load();
})();
