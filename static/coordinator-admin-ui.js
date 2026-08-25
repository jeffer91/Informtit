(() => {
  "use strict";

  const adminState = { coordinators: [], careers: [] };

  function esc(value = "") {
    return typeof escapeHtml === "function"
      ? escapeHtml(String(value))
      : String(value).replace(/[&<>"']/g, char => ({
          "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;",
        })[char]);
  }

  function ensureUi() {
    const nav = document.querySelector(".sidebar nav");
    if (nav && !document.querySelector('[data-view="coordinators"]')) {
      const button = document.createElement("button");
      button.className = "nav-item";
      button.dataset.view = "coordinators";
      button.textContent = "Coordinadores";
      button.addEventListener("click", openView);
      nav.appendChild(button);
    }

    const main = document.querySelector(".main");
    if (main && !document.querySelector("#view-coordinators")) {
      const section = document.createElement("section");
      section.id = "view-coordinators";
      section.className = "view";
      section.innerHTML = `
        <div class="panel">
          <div class="panel-head coordinator-panel-head">
            <div>
              <h2>Coordinadores y carreras</h2>
              <p>Edite el nombre, Telegram y las carreras asignadas. Los cambios se guardan en la base local y se usan en los reportes.</p>
            </div>
            <button class="button primary" type="button" id="new-coordinator-btn">Nuevo coordinador</button>
          </div>
          <div id="coordinator-admin-list" class="coordinator-admin-grid"></div>
        </div>`;
      main.appendChild(section);
      section.querySelector("#new-coordinator-btn").addEventListener("click", () => openEditor(null));
    }

    if (!document.querySelector("#coordinator-admin-dialog")) {
      const dialog = document.createElement("dialog");
      dialog.id = "coordinator-admin-dialog";
      dialog.className = "wide-dialog";
      dialog.innerHTML = `
        <form method="dialog" id="coordinator-admin-form" class="dialog-form">
          <div class="dialog-head">
            <div><h2 id="coordinator-admin-title">Editar coordinador</h2><p>Seleccione las carreras que estarán bajo su coordinación.</p></div>
            <button class="icon-button" value="cancel" aria-label="Cerrar">×</button>
          </div>
          <input type="hidden" name="coordinator_id">
          <div class="form-grid">
            <label>Nombre completo<input name="name" required autocomplete="off"></label>
            <label>Telegram<input name="telegram" placeholder="@usuario" autocomplete="off"></label>
          </div>
          <div class="coordinator-career-head">
            <div><strong>Carreras asignadas</strong><span>Marque o desmarque carreras. Una carrera solo puede pertenecer a un coordinador.</span></div>
            <input id="coordinator-career-search" type="search" placeholder="Buscar carrera">
          </div>
          <div id="coordinator-career-options" class="coordinator-career-options"></div>
          <label>Nueva carrera no listada<input name="new_career" placeholder="Opcional"></label>
          <div class="dialog-actions">
            <button class="button secondary" value="cancel">Cancelar</button>
            <button class="button primary" value="default" id="coordinator-save-btn">Guardar cambios</button>
          </div>
        </form>`;
      document.body.appendChild(dialog);
      dialog.querySelector("#coordinator-admin-form").addEventListener("submit", saveCoordinator);
      dialog.querySelector("#coordinator-career-search").addEventListener("input", filterCareers);
    }

    if (!document.querySelector("#coordinator-admin-style")) {
      const style = document.createElement("style");
      style.id = "coordinator-admin-style";
      style.textContent = `
        .coordinator-panel-head{align-items:center}
        .coordinator-admin-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:14px}
        .coordinator-card{border:1px solid #d9e2eb;border-radius:13px;background:#fff;padding:15px;display:flex;flex-direction:column;gap:10px}
        .coordinator-card-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}
        .coordinator-card h3{margin:0 0 4px}.coordinator-card p{margin:0;color:#64748b;font-size:12px}
        .coordinator-career-tags{display:flex;flex-wrap:wrap;gap:6px}
        .coordinator-career-tag{padding:5px 8px;border-radius:999px;background:#eef5fb;color:#315f80;font-size:11px;font-weight:650}
        .coordinator-career-head{display:flex;justify-content:space-between;align-items:end;gap:14px;margin-top:4px}
        .coordinator-career-head strong,.coordinator-career-head span{display:block}.coordinator-career-head span{font-size:12px;color:#64748b;margin-top:3px}
        #coordinator-career-search{max-width:260px}
        .coordinator-career-options{display:grid;grid-template-columns:repeat(2,minmax(220px,1fr));gap:8px;max-height:330px;overflow:auto;border:1px solid #d9e2eb;border-radius:10px;padding:10px;background:#f8fafc}
        .coordinator-career-option{display:flex;align-items:flex-start;gap:8px;padding:8px;border-radius:8px;background:#fff;border:1px solid #e5eaf0;font-weight:500}
        .coordinator-career-option span{display:block}.coordinator-career-option small{display:block;color:#64748b;margin-top:2px}
        @media(max-width:760px){.coordinator-career-options{grid-template-columns:1fr}.coordinator-career-head{align-items:stretch;flex-direction:column}#coordinator-career-search{max-width:none}}
      `;
      document.head.appendChild(style);
    }
  }

  async function openView() {
    ensureUi();
    document.querySelectorAll(".view").forEach(view => view.classList.remove("active"));
    document.querySelector("#view-coordinators")?.classList.add("active");
    document.querySelectorAll(".nav-item").forEach(item => item.classList.toggle("active", item.dataset.view === "coordinators"));
    const title = document.querySelector("#page-title");
    const subtitle = document.querySelector("#page-subtitle");
    if (title) title.textContent = "Coordinadores";
    if (subtitle) subtitle.textContent = "Administre responsables y carreras asignadas.";
    await loadCoordinators();
  }

  async function loadCoordinators() {
    const list = document.querySelector("#coordinator-admin-list");
    if (!list) return;
    list.innerHTML = '<div class="empty-mini">Cargando coordinadores...</div>';
    try {
      const data = await api("/api/coordinators");
      adminState.coordinators = Array.isArray(data.coordinators) ? data.coordinators : [];
      adminState.careers = Array.isArray(data.careers) ? data.careers : [];
      renderCoordinators();
    } catch (error) {
      list.innerHTML = `<div class="empty-mini">${esc(error.message || "No se pudieron cargar los coordinadores.")}</div>`;
      if (typeof toast === "function") toast(error.message || "No se pudieron cargar los coordinadores.", true);
    }
  }

  function renderCoordinators() {
    const list = document.querySelector("#coordinator-admin-list");
    if (!list) return;
    if (!adminState.coordinators.length) {
      list.innerHTML = '<div class="empty-mini">No existen coordinadores configurados.</div>';
      return;
    }
    list.innerHTML = adminState.coordinators.map(item => {
      const careers = item.careers || [];
      return `
        <article class="coordinator-card">
          <div class="coordinator-card-head">
            <div><h3>${esc(item.name)}</h3><p>${esc(item.telegram || "Sin Telegram")} · ${careers.length} carrera(s)</p></div>
            <button class="button secondary small" type="button" data-edit-coordinator="${Number(item.id)}">Editar</button>
          </div>
          <div class="coordinator-career-tags">
            ${careers.length ? careers.map(career => `<span class="coordinator-career-tag">${esc(career.career)}</span>`).join("") : '<span class="empty-mini">Sin carreras asignadas</span>'}
          </div>
        </article>`;
    }).join("");
    list.querySelectorAll("[data-edit-coordinator]").forEach(button => {
      button.addEventListener("click", () => openEditor(Number(button.dataset.editCoordinator)));
    });
  }

  function openEditor(id) {
    ensureUi();
    const dialog = document.querySelector("#coordinator-admin-dialog");
    const form = dialog.querySelector("#coordinator-admin-form");
    const item = id ? adminState.coordinators.find(row => Number(row.id) === Number(id)) : null;
    form.reset();
    form.coordinator_id.value = item ? item.id : "";
    form.name.value = item?.name || "";
    form.telegram.value = item?.telegram || "";
    dialog.querySelector("#coordinator-admin-title").textContent = item ? "Editar coordinador" : "Nuevo coordinador";
    renderCareerOptions(item?.careers || []);
    dialog.showModal();
  }

  function renderCareerOptions(selected) {
    const box = document.querySelector("#coordinator-career-options");
    const selectedKeys = new Set((selected || []).map(item => String(item.career_key || normalizeUi(item.career))));
    box.innerHTML = adminState.careers.map(item => {
      const key = String(item.career_key || normalizeUi(item.career));
      return `
        <label class="coordinator-career-option" data-career-search="${esc(normalizeUi(item.career))}">
          <input type="checkbox" data-career-key="${esc(key)}" data-career="${esc(item.career)}" data-program="${esc(item.program || "")}" ${selectedKeys.has(key) ? "checked" : ""}>
          <span>${esc(item.career)}<small>${esc(item.program || "Programa no especificado")}</small></span>
        </label>`;
    }).join("");
  }

  function normalizeUi(value) {
    return String(value || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  }

  function filterCareers(event) {
    const query = normalizeUi(event.currentTarget.value);
    document.querySelectorAll("#coordinator-career-options .coordinator-career-option").forEach(option => {
      option.style.display = !query || String(option.dataset.careerSearch || "").includes(query) ? "" : "none";
    });
  }

  async function saveCoordinator(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const button = document.querySelector("#coordinator-save-btn");
    const careers = [...document.querySelectorAll("#coordinator-career-options input[type=checkbox]:checked")].map(input => ({
      career: input.dataset.career,
      program: input.dataset.program || "",
    }));
    const newCareer = String(form.new_career.value || "").trim();
    if (newCareer && !careers.some(item => normalizeUi(item.career) === normalizeUi(newCareer))) {
      careers.push({ career: newCareer, program: "" });
    }
    const payload = { name: form.name.value.trim(), telegram: form.telegram.value.trim(), careers };
    const id = Number(form.coordinator_id.value || 0);
    button.disabled = true;
    button.textContent = "Guardando...";
    try {
      await api(id ? `/api/coordinators/${id}` : "/api/coordinators", {
        method: id ? "PUT" : "POST",
        body: JSON.stringify(payload),
      });
      document.querySelector("#coordinator-admin-dialog").close();
      if (typeof toast === "function") toast("Coordinador actualizado.");
      await loadCoordinators();
    } catch (error) {
      if (typeof toast === "function") toast(error.message || "No se pudo guardar el coordinador.", true);
    } finally {
      button.disabled = false;
      button.textContent = "Guardar cambios";
    }
  }

  ensureUi();
})();
