(() => {
  const ROUTE_LABELS = {
    COMPLEXIVO: "Examen Complexivo",
    TRABAJO_TITULACION: "Trabajo de Titulación",
  };
  const STATUS_LABELS = {
    ACTIVO: "Continúa proceso",
    NO_APROBADO_REQUISITO: "No aprobado por requisito",
    RETIRADO: "Retirado",
  };

  function api(path, options = {}) {
    if (window.api) return window.api(path, options);
    return fetch(path, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    }).then(async (response) => {
      const data = await response.json().catch(() => ({}));
      if (!response.ok || data.ok === false) throw new Error(data.error || "No se pudo completar la operación.");
      return data;
    });
  }

  function reportId() {
    const candidates = [
      window.state && window.state.activeReport && window.state.activeReport.id,
      window.state && window.state.activeReportId,
      window.activeReportId,
      document.body.dataset.reportId,
    ];
    const value = candidates.find((item) => Number(item) > 0);
    return value ? Number(value) : 0;
  }

  function esc(value) {
    return String(value == null ? "" : value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function badge(label, kind = "") {
    return `<span class="student-badge ${kind}">${esc(label)}</span>`;
  }

  function formatMissing(row) {
    const missing = Array.isArray(row.missing_requirements) ? row.missing_requirements : [];
    if (!missing.length) return badge("8/8 habilitantes", "ok");
    if (missing.length === 1) return badge(`Falta: ${missing[0]}`, "warn");
    return badge(`${missing.length} requisitos pendientes`, "danger");
  }

  function renderSummary(summary) {
    return `
      <div class="student-summary-grid">
        <div class="student-metric"><strong>${summary.students || 0}</strong><span>Total</span></div>
        <div class="student-metric"><strong>${summary.complexive || 0}</strong><span>Complexivo</span></div>
        <div class="student-metric"><strong>${summary.thesis || 0}</strong><span>Trabajo titulación</span></div>
        <div class="student-metric"><strong>${summary.graduated || 0}</strong><span>Graduados oficiales</span></div>
        <div class="student-metric"><strong>${summary.retired || 0}</strong><span>Retirados</span></div>
        <div class="student-metric"><strong>${summary.review || 0}</strong><span>Requieren revisión</span></div>
      </div>`;
  }

  function rowHtml(row) {
    const reconciliation = row.reconciliation_status === "OK"
      ? badge("Correcto", "ok")
      : badge(row.reconciliation_status || "Revisión", "warn");
    const official = Number(row.official_graduated) === 1
      ? badge("Graduado", "ok")
      : badge("No graduado", "muted");
    return `
      <tr data-student-id="${Number(row.id)}"
          data-search="${esc(`${row.identification} ${row.full_name} ${row.email} ${row.career_name}`.toLowerCase())}"
          data-route="${esc(row.route)}" data-process="${esc(row.process_status)}"
          data-reconciliation="${esc(row.reconciliation_status)}">
        <td><strong>${esc(row.full_name)}</strong><small>${esc(row.identification)}</small><small>${esc(row.email)}</small></td>
        <td>${esc(row.career_name)}<small>${esc(row.modality === "en_linea" ? "Online" : "Presencial")} · ${esc(row.campus || "Sin sede")}</small></td>
        <td>
          <select class="student-route-select" data-student-id="${Number(row.id)}">
            <option value="COMPLEXIVO" ${row.route === "COMPLEXIVO" ? "selected" : ""}>Examen Complexivo</option>
            <option value="TRABAJO_TITULACION" ${row.route === "TRABAJO_TITULACION" ? "selected" : ""}>Trabajo de Titulación</option>
          </select>
          <small>${row.route_source === "MANUAL" ? "Definido manualmente" : "Ruta por defecto"}</small>
        </td>
        <td>${formatMissing(row)}<small>${esc(STATUS_LABELS[row.process_status] || row.process_status)}</small></td>
        <td>${official}<small>${Number(row.official_titulation_completed) === 1 ? "Titulación: CUMPLE" : "Titulación no aprobada"}</small></td>
        <td>${reconciliation}<small>${esc(row.reconciliation_detail || "")}</small></td>
        <td><button class="button secondary compact student-detail-btn" data-student-id="${Number(row.id)}">Ver ficha</button></td>
      </tr>`;
  }

  function applyFilters(root) {
    const search = (root.querySelector("#student-search")?.value || "").trim().toLowerCase();
    const route = root.querySelector("#student-filter-route")?.value || "";
    const process = root.querySelector("#student-filter-process")?.value || "";
    const reconciliation = root.querySelector("#student-filter-reconciliation")?.value || "";
    root.querySelectorAll("tbody tr[data-student-id]").forEach((row) => {
      const visible = (!search || row.dataset.search.includes(search))
        && (!route || row.dataset.route === route)
        && (!process || row.dataset.process === process)
        && (!reconciliation || row.dataset.reconciliation === reconciliation);
      row.hidden = !visible;
    });
  }

  function detailHtml(row) {
    const missing = Array.isArray(row.missing_requirements) ? row.missing_requirements : [];
    const links = Array.isArray(row.source_links) ? row.source_links : [];
    return `
      <div class="student-detail-card">
        <div class="student-detail-head">
          <div><h3>${esc(row.full_name)}</h3><p>${esc(row.identification)} · ${esc(row.career_name)}</p></div>
          <button class="icon-button student-detail-close" type="button">×</button>
        </div>
        <div class="student-detail-grid">
          <div><span>Modalidad</span><strong>${esc(row.modality === "en_linea" ? "Online" : "Presencial")}</strong></div>
          <div><span>Ruta</span><strong>${esc(ROUTE_LABELS[row.route] || row.route)}</strong></div>
          <div><span>Estado proceso</span><strong>${esc(STATUS_LABELS[row.process_status] || row.process_status)}</strong></div>
          <div><span>Graduación oficial</span><strong>${Number(row.official_graduated) === 1 ? "GRADUADO" : "NO GRADUADO"}</strong></div>
          <div><span>Titulación oficial</span><strong>${Number(row.official_titulation_completed) === 1 ? "CUMPLE" : "NO CUMPLE"}</strong></div>
          <div><span>Conciliación</span><strong>${esc(row.reconciliation_status)}</strong></div>
        </div>
        <h4>Requisitos habilitantes pendientes</h4>
        <p>${missing.length ? esc(missing.join(", ")) : "Ninguno. Los ocho requisitos habilitantes están completos."}</p>
        <h4>Vínculos de fuentes</h4>
        ${links.length ? `<div class="student-links-list">${links.map((link) => `
          <div><strong>${esc(link.source_module)}</strong><span>${esc(link.source_name || link.source_key)}</span><span>${esc(link.match_status)} · ${esc(link.match_method || "")}${link.match_confidence != null ? ` · ${esc(link.match_confidence)}%` : ""}</span></div>`).join("")}</div>` : "<p>Aún no hay fuentes conciliadas para este estudiante.</p>"}
        ${row.reconciliation_detail ? `<div class="student-alert">${esc(row.reconciliation_detail)}</div>` : ""}
      </div>`;
  }

  async function renderStudents() {
    const root = document.getElementById("tab-students");
    if (!root) return;
    const id = reportId();
    if (!id) {
      root.innerHTML = `<div class="empty-state"><h3>Seleccione un período</h3><p>Abra un período para revisar sus estudiantes.</p></div>`;
      return;
    }
    root.innerHTML = `<div class="panel"><p>Cargando estudiantes y conciliando la información de Requisitos...</p></div>`;
    try {
      const data = await api(`/api/reports/${id}/students-domain`);
      const students = data.students || [];
      root._studentsData = students;
      root.innerHTML = `
        <div class="students-domain">
          <div class="panel">
            <div class="panel-head"><div><h2>Estudiantes del período</h2><p>Requisitos es la fuente maestra. Todos parten por Complexivo y solo los casos definidos manualmente pasan a Trabajo de Titulación.</p></div>
              <button class="button secondary" id="students-sync-btn">Reconciliar</button>
            </div>
            ${renderSummary(data.summary || {})}
            <div class="student-filters">
              <input id="student-search" placeholder="Buscar por cédula, nombre, correo o carrera">
              <select id="student-filter-route"><option value="">Todas las rutas</option><option value="COMPLEXIVO">Complexivo</option><option value="TRABAJO_TITULACION">Trabajo de Titulación</option></select>
              <select id="student-filter-process"><option value="">Todos los estados</option><option value="ACTIVO">Continúa proceso</option><option value="NO_APROBADO_REQUISITO">Falta un requisito</option><option value="RETIRADO">Retirado</option></select>
              <select id="student-filter-reconciliation"><option value="">Toda conciliación</option><option value="OK">Correctos</option><option value="OFFICIAL_DATA_CONFLICT">Conflicto oficial</option><option value="REVIEW_REQUIRED">Requieren revisión</option></select>
            </div>
            <div class="table-scroll"><table class="student-table"><thead><tr><th>Estudiante</th><th>Carrera</th><th>Ruta</th><th>Requisitos</th><th>Oficial</th><th>Conciliación</th><th></th></tr></thead><tbody>${students.map(rowHtml).join("")}</tbody></table></div>
          </div>
          <div id="student-detail-pane"></div>
        </div>`;

      root.querySelectorAll("#student-search,#student-filter-route,#student-filter-process,#student-filter-reconciliation").forEach((el) => {
        el.addEventListener("input", () => applyFilters(root));
        el.addEventListener("change", () => applyFilters(root));
      });
      root.querySelector("#students-sync-btn")?.addEventListener("click", async () => {
        await api(`/api/reports/${id}/students-domain/sync`, { method: "POST", body: "{}" });
        await renderStudents();
      });
      root.querySelectorAll(".student-route-select").forEach((select) => {
        select.addEventListener("change", async (event) => {
          const studentId = Number(event.target.dataset.studentId);
          const oldValue = students.find((item) => Number(item.id) === studentId)?.route || "COMPLEXIVO";
          try {
            await api(`/api/reports/${id}/students-domain/${studentId}/route`, {
              method: "PUT",
              body: JSON.stringify({ route: event.target.value }),
            });
            await renderStudents();
          } catch (error) {
            event.target.value = oldValue;
            window.showToast ? window.showToast(error.message, "error") : alert(error.message);
          }
        });
      });
      root.querySelectorAll(".student-detail-btn").forEach((button) => {
        button.addEventListener("click", () => {
          const student = students.find((item) => Number(item.id) === Number(button.dataset.studentId));
          const pane = root.querySelector("#student-detail-pane");
          if (student && pane) {
            pane.innerHTML = detailHtml(student);
            pane.scrollIntoView({ behavior: "smooth", block: "nearest" });
            pane.querySelector(".student-detail-close")?.addEventListener("click", () => { pane.innerHTML = ""; });
          }
        });
      });
    } catch (error) {
      root.innerHTML = `<div class="empty-state"><h3>No se pudo cargar Estudiantes</h3><p>${esc(error.message)}</p></div>`;
    }
  }

  function hookTab() {
    const button = document.querySelector('[data-tab="students"]');
    if (!button || button.dataset.studentsHooked) return;
    button.dataset.studentsHooked = "1";
    button.addEventListener("click", () => setTimeout(renderStudents, 0));
  }

  window.renderStudentsDomain = renderStudents;
  document.addEventListener("DOMContentLoaded", hookTab);
  setTimeout(hookTab, 0);
})();
