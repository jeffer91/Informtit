(() => {
  'use strict';

  if (!/(^|\.)github\.io$/i.test(location.hostname)) return;

  const form = document.getElementById('report-form');
  if (!form) return;

  const MONTHS = [
    'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
    'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre',
  ];
  const typeSelect = form.elements.report_type;
  const builder = form.querySelector('.report-period-builder');
  const outputNote = document.getElementById('report-output-note');
  const help = document.getElementById('report-type-help');
  const periodPreview = document.getElementById('report-period-preview');
  const namePreview = document.getElementById('report-name-preview');
  const codePreview = document.getElementById('report-code-preview');
  const submit = document.getElementById('create-report-submit');

  const clean = value => String(value ?? '').trim();
  const pad2 = value => String(Number(value || 0)).padStart(2, '0');
  const typeOf = value => clean(value).toLowerCase() === 'pvc' ? 'pvc' : 'normal';

  function hiddenInput(name) {
    let input = form.elements.namedItem(name);
    if (!input) {
      input = document.createElement('input');
      input.type = 'hidden';
      input.name = name;
      form.appendChild(input);
    }
    return input;
  }

  function today() {
    const date = new Date();
    return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;
  }

  function currentAcademicDefaults() {
    const date = new Date();
    const month = date.getMonth() + 1;
    const year = date.getFullYear();
    if (month >= 4 && month <= 9) {
      return { startMonth: 4, startYear: year, endMonth: 9, endYear: year };
    }
    if (month >= 10) {
      return { startMonth: 10, startYear: year, endMonth: 3, endYear: year + 1 };
    }
    return { startMonth: 10, startYear: year - 1, endMonth: 3, endYear: year };
  }

  function readPeriod() {
    const sm = Number(form.elements.period_start_month?.value || 0);
    const sy = Number(form.elements.period_start_year?.value || 0);
    const em = Number(form.elements.period_end_month?.value || 0);
    const ey = Number(form.elements.period_end_year?.value || 0);
    const valid = sm >= 1 && sm <= 12 && em >= 1 && em <= 12 && sy >= 2000 && ey >= 2000;
    const chronological = valid && (ey * 12 + em) >= (sy * 12 + sm);
    return { sm, sy, em, ey, valid, chronological };
  }

  function canonicalId(period) {
    return `${period.sy}-${pad2(period.sm)}__${period.ey}-${pad2(period.em)}`;
  }

  function periodLabel(period) {
    return `${MONTHS[period.sm - 1]} ${period.sy} - ${MONTHS[period.em - 1]} ${period.ey}`;
  }

  function codeFor(period, modality = 'presencial') {
    const suffix = `${period.ey}-${pad2(period.em)}`;
    return `UTET-INF-${modality === 'en_linea' ? '02' : '01'}-PRO-95-${suffix}`;
  }

  function setDefaults(force = false) {
    const defaults = currentAcademicDefaults();
    const fields = [
      ['period_start_month', defaults.startMonth],
      ['period_start_year', defaults.startYear],
      ['period_end_month', defaults.endMonth],
      ['period_end_year', defaults.endYear],
    ];
    fields.forEach(([name, value]) => {
      const input = form.elements[name];
      if (input && (force || !clean(input.value))) input.value = String(value);
    });
    if (form.elements.version && !clean(form.elements.version.value)) form.elements.version.value = '1.0';
    if (form.elements.elaboration_date && (force || !clean(form.elements.elaboration_date.value))) {
      form.elements.elaboration_date.value = today();
    }
  }

  function apply() {
    const period = readPeriod();
    const endYearInput = form.elements.period_end_year;
    if (endYearInput?.setCustomValidity) {
      endYearInput.setCustomValidity(period.valid && !period.chronological
        ? 'El final del período no puede ser anterior al inicio.'
        : '');
    }

    if (!period.valid || !period.chronological) {
      if (periodPreview) periodPreview.textContent = period.valid ? 'El final no puede ser anterior al inicio.' : '—';
      if (namePreview) namePreview.textContent = '—';
      if (codePreview) codePreview.textContent = '—';
      if (form.elements.period) form.elements.period.value = '';
      if (form.elements.name) form.elements.name.value = '';
      hiddenInput('firebase_period_id').value = '';
      hiddenInput('periodoId').value = '';
      hiddenInput('code_presencial').value = '';
      hiddenInput('code_online').value = '';
      if (submit) submit.disabled = true;
      return false;
    }

    const label = periodLabel(period);
    const id = canonicalId(period);
    const pvc = typeOf(typeSelect?.value) === 'pvc';
    const codePresencial = codeFor(period, 'presencial');
    const codeOnline = codeFor(period, 'en_linea');
    const codeMonth = `${period.ey}-${pad2(period.em)}`;
    const name = `Informe Final del Proceso de Titulación - ${label}`;

    if (form.elements.period) form.elements.period.value = label;
    if (form.elements.name) form.elements.name.value = name;
    if (form.elements.code) form.elements.code.value = codePresencial;
    if (form.elements.code_month) form.elements.code_month.value = codeMonth;
    if (form.elements.version && !clean(form.elements.version.value)) form.elements.version.value = '1.0';
    if (form.elements.elaboration_date && !clean(form.elements.elaboration_date.value)) form.elements.elaboration_date.value = today();

    hiddenInput('firebase_period_id').value = id;
    hiddenInput('periodoId').value = id;
    hiddenInput('code_presencial').value = codePresencial;
    hiddenInput('code_online').value = pvc ? '' : codeOnline;

    if (periodPreview) periodPreview.textContent = label;
    if (namePreview) namePreview.textContent = name;
    if (codePreview) {
      codePreview.innerHTML = pvc
        ? codePresencial
        : `Presencial: ${codePresencial}<br>Online: ${codeOnline}`;
    }
    if (submit) submit.disabled = false;
    return true;
  }

  function refreshType() {
    const pvc = typeOf(typeSelect?.value) === 'pvc';
    if (outputNote) outputNote.textContent = pvc ? 'PVC · Artículo Académico' : 'Presencial + Online';
    if (help) {
      help.textContent = pvc
        ? 'PVC utiliza el período configurado aquí y trabaja con Artículo Académico.'
        : 'Regular utiliza el período configurado aquí y consolida Presencial + Online.';
    }
    apply();
  }

  function enhanceBuilder() {
    document.getElementById('sheets-report-period-selector')?.remove();
    if (!builder) return;

    builder.hidden = false;
    builder.style.removeProperty('display');
    builder.querySelectorAll('input,select,button').forEach(node => { node.tabIndex = 0; });

    const source = document.getElementById('manual-period-source') || document.createElement('small');
    source.id = 'manual-period-source';
    source.textContent = 'Define el período con mes y año de inicio y fin. Se usará como identificador del período en Informtit y Google Sheets.';
    source.style.cssText = 'display:block;margin-top:8px;color:#64748b';
    if (!source.isConnected) builder.appendChild(source);

    for (const name of ['period_start_year', 'period_end_year']) {
      const input = form.elements[name];
      if (!input || input.closest('.period-year-stepper')) continue;
      const wrapper = document.createElement('div');
      wrapper.className = 'period-year-stepper';
      input.parentNode.insertBefore(wrapper, input);
      const minus = document.createElement('button');
      minus.type = 'button';
      minus.className = 'period-year-button';
      minus.textContent = '−';
      minus.setAttribute('aria-label', 'Restar un año');
      const plus = document.createElement('button');
      plus.type = 'button';
      plus.className = 'period-year-button';
      plus.textContent = '+';
      plus.setAttribute('aria-label', 'Sumar un año');
      wrapper.append(minus, input, plus);
      const step = delta => {
        const current = Number(input.value || new Date().getFullYear());
        input.value = String(Math.max(2000, Math.min(2100, current + delta)));
        input.dispatchEvent(new Event('input', { bubbles: true }));
      };
      minus.addEventListener('click', () => step(-1));
      plus.addEventListener('click', () => step(1));
    }
  }

  function injectStyles() {
    if (document.getElementById('manual-period-builder-style')) return;
    const style = document.createElement('style');
    style.id = 'manual-period-builder-style';
    style.textContent = `
      #report-dialog .report-period-grid{grid-template-columns:minmax(150px,1fr) minmax(180px,1fr) minmax(150px,1fr) minmax(180px,1fr);gap:12px;align-items:end}
      #report-dialog .period-year-stepper{display:grid;grid-template-columns:34px minmax(90px,1fr) 34px;gap:6px;align-items:center}
      #report-dialog .period-year-stepper input{min-width:0;width:100%;box-sizing:border-box}
      #report-dialog .period-year-button{height:36px;border:1px solid #cbd8e4;border-radius:8px;background:#f7f9fc;color:#102b46;font-weight:800;font-size:17px;cursor:pointer}
      #report-dialog .period-year-button:hover{background:#eef4fa}
      #report-dialog .report-period-builder{display:block!important}
      @media(max-width:760px){#report-dialog .report-period-grid{grid-template-columns:1fr 1fr}}
    `;
    document.head.appendChild(style);
  }

  async function submitReport(event) {
    event.preventDefault();
    event.stopImmediatePropagation();
    const reportForm = form;
    if (!apply() || !reportForm.reportValidity()) return;

    const button = submit;
    const original = button?.textContent || 'Crear informe';
    if (button) {
      button.disabled = true;
      button.textContent = 'Creando…';
    }

    try {
      const payload = Object.fromEntries(new FormData(reportForm).entries());
      const result = await api('/api/reports', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      document.getElementById('report-dialog')?.close();
      reportForm.reset();
      if (typeSelect) typeSelect.value = 'normal';
      setDefaults(true);
      refreshType();
      if (typeof toast === 'function') {
        toast(result.report_type === 'pvc' ? 'Informe PVC creado.' : 'Informe regular creado.');
      }
      if (typeof loadReports === 'function') await loadReports();
      if (typeof openReport === 'function' && result.report_id) await openReport(result.report_id);
    } catch (error) {
      if (typeof toast === 'function') toast(error?.message || 'No se pudo crear el informe.', true);
    } finally {
      if (button?.isConnected) {
        button.disabled = false;
        button.textContent = original;
      }
    }
  }

  injectStyles();
  enhanceBuilder();
  setDefaults(false);
  apply();

  for (const name of ['period_start_month', 'period_start_year', 'period_end_month', 'period_end_year']) {
    const control = form.elements[name];
    control?.addEventListener('input', apply);
    control?.addEventListener('change', apply);
  }
  form.elements.code_month?.addEventListener('change', apply);
  typeSelect?.addEventListener('change', refreshType);

  document.addEventListener('click', event => {
    const button = event.target.closest?.('#new-report-btn,#new-pvc-report-btn');
    if (!button) return;
    setTimeout(() => {
      if (typeSelect) typeSelect.value = button.id === 'new-pvc-report-btn' ? 'pvc' : 'normal';
      setDefaults(false);
      refreshType();
    }, 0);
  }, true);

  form.addEventListener('submit', submitReport, true);
})();
