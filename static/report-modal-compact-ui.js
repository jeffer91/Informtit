(() => {
  'use strict';

  if (!/(^|\.)github\.io$/i.test(location.hostname)) return;

  const dialog = document.getElementById('report-dialog');
  const form = document.getElementById('report-form');
  if (!dialog || !form) return;

  dialog.classList.add('report-dialog-compact');

  const subtitle = dialog.querySelector('.dialog-head p');
  if (subtitle) subtitle.textContent = 'Configure el período y revise los datos generados.';

  const periodLabel = document.getElementById('report-period-label');
  if (periodLabel) periodLabel.textContent = 'Período académico';

  const periodPreviewLabel = document.querySelector('#report-period-preview')?.previousElementSibling;
  if (periodPreviewLabel) periodPreviewLabel.textContent = 'Período generado';

  const help = document.getElementById('report-type-help');
  if (help) help.hidden = true;

  const source = document.getElementById('manual-period-source');
  if (source) source.hidden = true;

  const codeMonth = form.elements.code_month;
  const version = form.elements.version;
  if (codeMonth?.closest('label')) codeMonth.closest('label').classList.add('compact-hidden-field');
  if (version?.closest('label')) version.closest('label').classList.add('compact-hidden-field');

  const generatedGrid = codeMonth?.closest('.form-grid');
  if (generatedGrid) generatedGrid.classList.add('compact-generated-grid');

  const outputNote = document.getElementById('report-output-note');
  if (outputNote) outputNote.classList.add('compact-output-chip');

  const style = document.createElement('style');
  style.id = 'report-modal-compact-style';
  style.textContent = `
    #report-dialog.report-dialog-compact {
      width: min(820px, calc(100vw - 28px));
      max-width: 820px;
      max-height: 92vh;
      margin: auto;
      overflow: hidden;
      border-radius: 18px;
    }
    #report-dialog.report-dialog-compact #report-form {
      width: 100%;
      max-width: 100%;
      max-height: 92vh;
      padding: 0;
      gap: 0;
      overflow-x: hidden;
      overflow-y: auto;
      background: #fff;
    }
    #report-dialog.report-dialog-compact .dialog-head {
      position: sticky;
      top: 0;
      z-index: 4;
      padding: 18px 20px 14px;
      background: #fff;
      border-bottom: 1px solid var(--line);
    }
    #report-dialog.report-dialog-compact .dialog-head h2 {
      font-size: 22px;
      line-height: 1.15;
      margin: 0 0 4px;
    }
    #report-dialog.report-dialog-compact .dialog-head p {
      font-size: 12px;
      line-height: 1.35;
    }
    #report-dialog.report-dialog-compact .dialog-head + input,
    #report-dialog.report-dialog-compact .dialog-head + input + input,
    #report-dialog.report-dialog-compact .dialog-head + input + input + input {
      display: none;
    }
    #report-dialog.report-dialog-compact #report-form > .form-grid,
    #report-dialog.report-dialog-compact #report-form > .report-period-builder,
    #report-dialog.report-dialog-compact #report-form > .report-derived-preview {
      margin: 14px 20px 0;
      min-width: 0;
    }
    #report-dialog.report-dialog-compact #report-form > .form-grid:first-of-type {
      grid-template-columns: minmax(0, 1.3fr) minmax(180px, .7fr);
      gap: 14px;
      align-items: end;
    }
    #report-dialog.report-dialog-compact label {
      min-width: 0;
      gap: 5px;
      font-size: 12px;
    }
    #report-dialog.report-dialog-compact input,
    #report-dialog.report-dialog-compact select {
      min-width: 0;
      height: 38px;
      padding: 8px 10px;
    }
    #report-dialog.report-dialog-compact .compact-output-chip {
      min-height: 38px;
      display: flex;
      align-items: center;
      padding: 8px 11px;
      border: 1px solid #d8e3ee;
      border-radius: 9px;
      background: #f3f7fb;
      color: #244764;
      font-weight: 750;
    }
    #report-dialog.report-dialog-compact .report-period-builder {
      display: block !important;
      padding: 14px;
      border-radius: 13px;
      overflow: hidden;
    }
    #report-dialog.report-dialog-compact .report-field-label {
      margin-bottom: 10px;
      font-size: 13px;
    }
    #report-dialog.report-dialog-compact .report-period-grid {
      display: grid !important;
      grid-template-columns: repeat(4, minmax(0, 1fr)) !important;
      gap: 10px !important;
      align-items: end !important;
      width: 100%;
      min-width: 0;
    }
    #report-dialog.report-dialog-compact .period-year-stepper {
      display: grid !important;
      grid-template-columns: 30px minmax(0, 1fr) 30px !important;
      gap: 4px !important;
      width: 100%;
      min-width: 0;
    }
    #report-dialog.report-dialog-compact .period-year-button {
      width: 30px;
      min-width: 30px;
      height: 38px !important;
      padding: 0;
      border-radius: 8px;
    }
    #report-dialog.report-dialog-compact .report-period-builder .report-derived-preview {
      margin-top: 10px;
      padding: 9px 11px;
      border-radius: 9px;
    }
    #report-dialog.report-dialog-compact .report-derived-preview {
      padding: 10px 12px;
      border-radius: 10px;
      min-width: 0;
    }
    #report-dialog.report-dialog-compact .report-derived-preview span {
      font-size: 10px;
      text-transform: uppercase;
      letter-spacing: .03em;
    }
    #report-dialog.report-dialog-compact .report-derived-preview strong {
      font-size: 12px;
      line-height: 1.35;
      overflow-wrap: anywhere;
      word-break: normal;
    }
    #report-dialog.report-dialog-compact .compact-generated-grid {
      grid-template-columns: minmax(0, 1.35fr) minmax(210px, .65fr);
      gap: 14px;
      align-items: stretch;
    }
    #report-dialog.report-dialog-compact .compact-generated-grid .report-derived-preview.compact {
      min-height: 62px;
      align-self: stretch;
    }
    #report-dialog.report-dialog-compact .compact-hidden-field {
      display: none !important;
    }
    #report-dialog.report-dialog-compact .dialog-actions {
      position: sticky;
      bottom: 0;
      z-index: 4;
      margin-top: 14px;
      padding: 12px 20px 14px;
      background: #fff;
      box-shadow: 0 -8px 22px rgba(15, 33, 53, .06);
    }
    #report-dialog.report-dialog-compact .dialog-actions .button {
      min-width: 112px;
    }
    #report-dialog.report-dialog-compact * {
      max-width: 100%;
    }
    @media (max-width: 720px) {
      #report-dialog.report-dialog-compact {
        width: calc(100vw - 16px);
        max-height: 94vh;
        border-radius: 14px;
      }
      #report-dialog.report-dialog-compact #report-form {
        max-height: 94vh;
      }
      #report-dialog.report-dialog-compact #report-form > .form-grid:first-of-type,
      #report-dialog.report-dialog-compact .compact-generated-grid {
        grid-template-columns: 1fr;
      }
      #report-dialog.report-dialog-compact .report-period-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
      }
    }
    @media (max-width: 430px) {
      #report-dialog.report-dialog-compact .dialog-head,
      #report-dialog.report-dialog-compact .dialog-actions {
        padding-left: 14px;
        padding-right: 14px;
      }
      #report-dialog.report-dialog-compact #report-form > .form-grid,
      #report-dialog.report-dialog-compact #report-form > .report-period-builder,
      #report-dialog.report-dialog-compact #report-form > .report-derived-preview {
        margin-left: 14px;
        margin-right: 14px;
      }
      #report-dialog.report-dialog-compact .report-period-grid {
        grid-template-columns: 1fr !important;
      }
    }
  `;
  document.head.appendChild(style);
})();
