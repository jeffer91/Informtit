(() => {
  'use strict';

  if (!/(^|\.)github\.io$/i.test(window.location.hostname)) return;

  const DEFAULT_SECTIONS = [
    ['introduccion', 'Introducción'],
    ['base_legal', 'Base legal'],
    ['metodologia', 'Metodología'],
    ['resultados', 'Resultados'],
    ['conclusiones', 'Conclusiones'],
    ['recomendaciones', 'Recomendaciones'],
    ['anexos', 'Anexos'],
  ];

  const esc = value => typeof window.escapeHtml === 'function'
    ? window.escapeHtml(String(value ?? ''))
    : String(value ?? '').replace(/[&<>"']/g, char => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[char]));

  const clean = value => String(value ?? '').replace(/\u00a0/g, ' ').trim().replace(/\s+/g, ' ');

  function parseConfig(raw) {
    if (!raw) return {};
    if (typeof raw === 'object') return raw;
    try { return JSON.parse(String(raw)); } catch (_) { return {}; }
  }

  function configFor(report = window.state?.activeReport || {}) {
    const saved = parseConfig(report.document_config || report.documentConfig || report.document_config_json);
    const savedSections = Array.isArray(saved.sections) ? saved.sections : [];
    const sectionMap = new Map(savedSections.map(item => [clean(item.key || item.section_key), item]));
    return {
      cover: {
        enabled: saved.cover?.enabled !== false,
        institution: clean(saved.cover?.institution || ''),
        title: clean(saved.cover?.title || report.name || 'Informe Final del Proceso de Titulación'),
        subtitle: clean(saved.cover?.subtitle || ''),
        show_period: saved.cover?.show_period !== false,
        show_code: saved.cover?.show_code !== false,
        show_date: saved.cover?.show_date !== false,
        show_responsibles: saved.cover?.show_responsibles !== false,
      },
      header: {
        enabled: saved.header?.enabled !== false,
        left_text: clean(saved.header?.left_text || ''),
        center_text: clean(saved.header?.center_text || report.name || 'Informe Final de Titulación'),
        show_code: saved.header?.show_code !== false,
        show_version: saved.header?.show_version !== false,
        show_period: saved.header?.show_period === true,
        exclude_cover: saved.header?.exclude_cover !== false,
      },
      sections: DEFAULT_SECTIONS.map(([key, title], index) => {
        const prior = sectionMap.get(key) || {};
        return {
          key,
          title: clean(prior.title || title),
          visible: prior.visible !== false,
          order: Number.isFinite(Number(prior.order)) ? Number(prior.order) : index + 1,
        };
      }).sort((a, b) => a.order - b.order),
    };
  }

  function ensureDocumentTabs() {
    const tabs = document.getElementById('report-tabs');
    const generalButton = tabs?.querySelector('[data-tab="general"]');
    if (!tabs || !generalButton) return;

    const definitions = [
      ['cover', 'Portada'],
      ['header', 'Cabecera'],
      ['sections', 'Secciones'],
    ];
    let anchor = generalButton;
    definitions.forEach(([key, label]) => {
      let button = tabs.querySelector(`[data-tab="${key}"]`);
      if (!button) {
        button = document.createElement('button');
        button.type = 'button';
        button.className = 'tab';
        button.dataset.tab = key;
        button.textContent = label;
        anchor.insertAdjacentElement('afterend', button);
      }
      anchor = button;
    });

    const workspace = document.getElementById('report-workspace');
    const generalContent = document.getElementById('tab-general');
    if (!workspace || !generalContent) return;
    let contentAnchor = generalContent;
    definitions.forEach(([key]) => {
      let content = document.getElementById(`tab-${key}`);
      if (!content) {
        content = document.createElement('div');
        content.id = `tab-${key}`;
        content.className = 'tab-content';
        contentAnchor.insertAdjacentElement('afterend', content);
      }
      contentAnchor = content;
    });
  }

  function checked(value) { return value ? 'checked' : ''; }

  function reportCode(report) {
    const label = document.getElementById('report-modality')?.textContent || '';
    return /online|línea/i.test(label) ? (report.code_online || report.code || '') : (report.code_presencial || report.code || '');
  }

  function responsibleBlock(report) {
    const rows = [
      ['Elaborado por', report.prepared_by, report.prepared_role],
      ['Revisado por', report.reviewed_by, report.reviewed_role],
      ['Aprobado por', report.approved_by, report.approved_role],
    ].filter(([, name]) => clean(name));
    return rows.length
      ? rows.map(([label, name, role]) => `<div><span>${esc(label)}</span><strong>${esc(name)}</strong><small>${esc(role || '')}</small></div>`).join('')
      : '<div class="document-preview-empty">Los responsables se toman de Datos generales.</div>';
  }

  function renderCoverTab() {
    const host = document.getElementById('tab-cover');
    const report = window.state?.activeReport;
    if (!host || !report) return;
    const config = configFor(report);
    const cover = config.cover;
    host.innerHTML = `
      <section class="panel document-config-panel">
        <div class="panel-head"><div><h2>Portada</h2><p>Configure únicamente la primera página del documento. La portada es independiente de la cabecera y de las secciones internas.</p></div></div>
        <form id="cover-config-form" class="document-config-grid">
          <label>Institución<input name="institution" value="${esc(cover.institution)}" placeholder="Nombre institucional"></label>
          <label>Título principal<input name="title" value="${esc(cover.title)}" required></label>
          <label class="document-wide">Subtítulo<input name="subtitle" value="${esc(cover.subtitle)}" placeholder="Opcional"></label>
          <div class="document-checks document-wide">
            <label class="check"><input type="checkbox" name="enabled" ${checked(cover.enabled)}> Incluir portada</label>
            <label class="check"><input type="checkbox" name="show_period" ${checked(cover.show_period)}> Mostrar período</label>
            <label class="check"><input type="checkbox" name="show_code" ${checked(cover.show_code)}> Mostrar código</label>
            <label class="check"><input type="checkbox" name="show_date" ${checked(cover.show_date)}> Mostrar fecha</label>
            <label class="check"><input type="checkbox" name="show_responsibles" ${checked(cover.show_responsibles)}> Mostrar responsables</label>
          </div>
          <div class="form-actions document-wide"><button class="button primary" type="submit">Guardar portada</button></div>
        </form>
      </section>
      <section class="panel document-preview-panel">
        <div class="panel-head"><div><h2>Vista previa de portada</h2><p>Vista estructural de los datos que irán en la primera página.</p></div></div>
        <article class="cover-preview ${cover.enabled ? '' : 'is-disabled'}">
          <div class="cover-preview-institution">${esc(cover.institution || 'INSTITUCIÓN')}</div>
          <h3>${esc(cover.title)}</h3>
          ${cover.subtitle ? `<p class="cover-preview-subtitle">${esc(cover.subtitle)}</p>` : ''}
          <div class="cover-preview-meta">
            ${cover.show_period ? `<span>${esc(report.period || '')}</span>` : ''}
            ${cover.show_code ? `<span>${esc(reportCode(report) || 'Sin código')}</span>` : ''}
            ${cover.show_date ? `<span>${esc(report.elaboration_date || 'Fecha de elaboración pendiente')}</span>` : ''}
          </div>
          ${cover.show_responsibles ? `<div class="cover-preview-responsibles">${responsibleBlock(report)}</div>` : ''}
        </article>
      </section>`;

    host.querySelector('#cover-config-form')?.addEventListener('submit', async event => {
      event.preventDefault();
      const form = event.currentTarget;
      const next = configFor(window.state.activeReport);
      next.cover = {
        enabled: form.enabled.checked,
        institution: clean(form.institution.value),
        title: clean(form.title.value),
        subtitle: clean(form.subtitle.value),
        show_period: form.show_period.checked,
        show_code: form.show_code.checked,
        show_date: form.show_date.checked,
        show_responsibles: form.show_responsibles.checked,
      };
      await saveDocumentConfig(next, 'Portada guardada.');
    });
  }

  function renderHeaderTab() {
    const host = document.getElementById('tab-header');
    const report = window.state?.activeReport;
    if (!host || !report) return;
    const config = configFor(report);
    const header = config.header;
    host.innerHTML = `
      <section class="panel document-config-panel">
        <div class="panel-head"><div><h2>Cabecera</h2><p>Configure la cabecera repetida de las páginas internas. Por defecto no se aplica a la portada.</p></div></div>
        <form id="header-config-form" class="document-config-grid">
          <label>Texto izquierdo<input name="left_text" value="${esc(header.left_text)}" placeholder="Institución / unidad"></label>
          <label>Texto central<input name="center_text" value="${esc(header.center_text)}" placeholder="Nombre del documento"></label>
          <div class="document-checks document-wide">
            <label class="check"><input type="checkbox" name="enabled" ${checked(header.enabled)}> Usar cabecera</label>
            <label class="check"><input type="checkbox" name="show_code" ${checked(header.show_code)}> Mostrar código</label>
            <label class="check"><input type="checkbox" name="show_version" ${checked(header.show_version)}> Mostrar versión</label>
            <label class="check"><input type="checkbox" name="show_period" ${checked(header.show_period)}> Mostrar período</label>
            <label class="check"><input type="checkbox" name="exclude_cover" ${checked(header.exclude_cover)}> Excluir de la portada</label>
          </div>
          <div class="form-actions document-wide"><button class="button primary" type="submit">Guardar cabecera</button></div>
        </form>
      </section>
      <section class="panel document-preview-panel">
        <div class="panel-head"><div><h2>Vista previa de cabecera</h2><p>La información dinámica se toma del informe activo.</p></div></div>
        <div class="header-preview ${header.enabled ? '' : 'is-disabled'}">
          <strong>${esc(header.left_text || 'INSTITUCIÓN')}</strong>
          <span>${esc(header.center_text || report.name || '')}</span>
          <small>${[
            header.show_code ? reportCode(report) : '',
            header.show_version ? `V. ${report.version || '1.0'}` : '',
            header.show_period ? report.period : '',
          ].filter(Boolean).map(esc).join(' · ') || 'Sin metadatos adicionales'}</small>
        </div>
      </section>`;

    host.querySelector('#header-config-form')?.addEventListener('submit', async event => {
      event.preventDefault();
      const form = event.currentTarget;
      const next = configFor(window.state.activeReport);
      next.header = {
        enabled: form.enabled.checked,
        left_text: clean(form.left_text.value),
        center_text: clean(form.center_text.value),
        show_code: form.show_code.checked,
        show_version: form.show_version.checked,
        show_period: form.show_period.checked,
        exclude_cover: form.exclude_cover.checked,
      };
      await saveDocumentConfig(next, 'Cabecera guardada.');
    });
  }

  function renderSectionsTab() {
    const host = document.getElementById('tab-sections');
    const report = window.state?.activeReport;
    if (!host || !report) return;
    const config = configFor(report);
    host.innerHTML = `
      <section class="panel document-sections-panel">
        <div class="panel-head"><div><h2>Secciones del documento</h2><p>Defina el orden y la visibilidad de la estructura interna. Portada y Cabecera se administran por separado.</p></div></div>
        <div class="document-section-list" id="document-section-list">
          ${config.sections.map((section, index) => `
            <article class="document-section-row" data-section-key="${esc(section.key)}">
              <div class="document-section-order">${index + 1}</div>
              <label class="document-section-title">Título<input name="title" value="${esc(section.title)}"></label>
              <label class="check"><input type="checkbox" name="visible" ${checked(section.visible)}> Visible</label>
              <div class="document-section-actions">
                <button class="button secondary small" type="button" data-move="up" ${index === 0 ? 'disabled' : ''}>↑</button>
                <button class="button secondary small" type="button" data-move="down" ${index === config.sections.length - 1 ? 'disabled' : ''}>↓</button>
              </div>
            </article>`).join('')}
        </div>
        <div class="form-actions"><button class="button primary" type="button" id="save-document-sections">Guardar estructura</button></div>
      </section>`;

    const list = host.querySelector('#document-section-list');
    list?.addEventListener('click', event => {
      const button = event.target.closest('[data-move]');
      if (!button) return;
      const row = button.closest('[data-section-key]');
      if (!row) return;
      if (button.dataset.move === 'up' && row.previousElementSibling) list.insertBefore(row, row.previousElementSibling);
      if (button.dataset.move === 'down' && row.nextElementSibling) list.insertBefore(row.nextElementSibling, row);
      [...list.children].forEach((node, index) => { node.querySelector('.document-section-order').textContent = String(index + 1); });
    });

    host.querySelector('#save-document-sections')?.addEventListener('click', async () => {
      const next = configFor(window.state.activeReport);
      next.sections = [...list.querySelectorAll('[data-section-key]')].map((row, index) => ({
        key: row.dataset.sectionKey,
        title: clean(row.querySelector('[name="title"]')?.value),
        visible: Boolean(row.querySelector('[name="visible"]')?.checked),
        order: index + 1,
      }));
      await saveDocumentConfig(next, 'Estructura del documento guardada.');
    });
  }

  async function saveDocumentConfig(config, message) {
    const report = window.state?.activeReport;
    if (!report?.id) return;
    try {
      const result = await window.api(`/api/reports/${report.id}`, {
        method: 'PUT',
        body: JSON.stringify({ document_config: config, document_config_json: JSON.stringify(config) }),
      });
      window.state.activeReport = result?.report ? { ...result.report, document_config: config } : { ...report, document_config: config };
      if (typeof window.toast === 'function') window.toast(message);
      renderCoverTab();
      renderHeaderTab();
      renderSectionsTab();
    } catch (error) {
      if (typeof window.toast === 'function') window.toast(error.message || String(error), true);
    }
  }

  function injectStyles() {
    if (document.getElementById('pages-document-ui-style')) return;
    const style = document.createElement('style');
    style.id = 'pages-document-ui-style';
    style.textContent = `
      .document-config-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.document-wide{grid-column:1/-1}.document-checks{display:flex;gap:16px;flex-wrap:wrap;padding:12px;border:1px solid #dde6ee;border-radius:12px;background:#f8fafc}.document-preview-panel{margin-top:16px}.cover-preview{width:min(620px,100%);min-height:620px;margin:0 auto;padding:54px 48px;border:1px solid #d9e3ec;border-radius:8px;background:#fff;box-shadow:0 10px 30px rgba(15,35,55,.07);display:flex;flex-direction:column;align-items:center;text-align:center}.cover-preview.is-disabled,.header-preview.is-disabled{opacity:.45}.cover-preview-institution{font-size:13px;font-weight:800;letter-spacing:.08em;margin-bottom:80px}.cover-preview h3{font-size:25px;line-height:1.25;max-width:500px;margin:0}.cover-preview-subtitle{margin:14px 0 0;color:#52677a}.cover-preview-meta{display:grid;gap:7px;margin-top:34px;color:#50677b}.cover-preview-responsibles{width:100%;margin-top:auto;display:grid;grid-template-columns:repeat(3,1fr);gap:10px;border-top:1px solid #dfe7ee;padding-top:18px}.cover-preview-responsibles div{display:grid;gap:4px}.cover-preview-responsibles span{font-size:10px;text-transform:uppercase;color:#687b8d}.cover-preview-responsibles small{color:#687b8d}.document-preview-empty{grid-column:1/-1;color:#687b8d}.header-preview{display:grid;grid-template-columns:1fr 2fr 1.4fr;align-items:center;gap:12px;padding:14px 16px;border:1px solid #d9e3ec;border-radius:10px;background:#fff}.header-preview span{text-align:center;font-weight:700}.header-preview small{text-align:right;color:#596f83}.document-section-list{display:grid;gap:9px}.document-section-row{display:grid;grid-template-columns:38px minmax(220px,1fr) auto auto;gap:12px;align-items:end;padding:11px;border:1px solid #dfe7ee;border-radius:11px;background:#fff}.document-section-order{width:32px;height:32px;border-radius:50%;display:grid;place-items:center;background:#eef4f8;font-weight:800;color:#173b5c;align-self:center}.document-section-title{margin:0}.document-section-actions{display:flex;gap:6px;align-items:end}.document-section-actions .button{min-width:38px;padding-left:10px;padding-right:10px}
      @media(max-width:760px){.document-config-grid{grid-template-columns:1fr}.document-wide{grid-column:auto}.cover-preview{min-height:520px;padding:38px 24px}.cover-preview-responsibles{grid-template-columns:1fr}.header-preview{grid-template-columns:1fr}.header-preview span,.header-preview small{text-align:left}.document-section-row{grid-template-columns:34px 1fr}.document-section-row>.check,.document-section-actions{grid-column:2}}
    `;
    document.head.appendChild(style);
  }

  const previousRenderReport = window.renderReport;
  window.renderSectionsTab = renderSectionsTab;
  window.renderCoverTab = renderCoverTab;
  window.renderHeaderTab = renderHeaderTab;

  if (typeof previousRenderReport === 'function') {
    window.renderReport = function renderReportWithDocumentWorkspace(...args) {
      ensureDocumentTabs();
      const result = previousRenderReport.apply(this, args);
      renderCoverTab();
      renderHeaderTab();
      renderSectionsTab();
      return result;
    };
  }

  injectStyles();
  ensureDocumentTabs();
})();