(function () {
  "use strict";

  function reportType(report) {
    return String(report?.report_type || "").toLowerCase() === "pvc" ? "pvc" : "normal";
  }

  function setText(node, value) {
    if (!node) return;
    const next = String(value ?? "");
    if (node.textContent !== next) node.textContent = next;
  }

  function decorate() {
    try {
      const footer = document.querySelector(".sidebar-footer span:last-child");
      setText(footer, "Firebase + respaldo local");

      document.querySelectorAll(".report-card").forEach(card => {
        const button = card.querySelector("[data-open-report]");
        if (!button || typeof state === "undefined") return;
        const report = (state.reports || []).find(
          item => Number(item.id) === Number(button.dataset.openReport)
        );
        if (!report) return;
        const badge = card.querySelector(".badge");
        if (badge && reportType(report) === "pvc") setText(badge, "PVC");
      });

      if (typeof state !== "undefined" && state.activeReport) {
        const pvc = reportType(state.activeReport) === "pvc";
        const modality = document.querySelector("#report-modality");
        if (pvc && modality) setText(modality, "PVC");

        const select = document.querySelector("#general-form [name=modality]");
        if (select) {
          select.disabled = pvc;
          select.title = pvc
            ? "Los informes PVC no se dividen en Presencial y Online."
            : "";
        }
      }

      document.querySelectorAll("#dashboard-metrics .metric").forEach(metric => {
        const label = metric.querySelector("span");
        const value = metric.querySelector("strong");
        if (label?.textContent.trim() === "Base de datos" && value) {
          setText(value, "Firebase + local");
        }
      });
    } catch (error) {
      console.warn("[Informtit Firebase] No se pudo actualizar la presentación.", error);
    }
  }

  function ensureDialog() {
    let dialog = document.querySelector("#firebase-sync-dialog");
    if (dialog) return dialog;

    dialog = document.createElement("dialog");
    dialog.id = "firebase-sync-dialog";
    dialog.innerHTML = `
      <form method="dialog" class="dialog-form" id="firebase-sync-form">
        <div class="dialog-head">
          <div>
            <h2>Sincronizar fuentes Firebase</h2>
            <p>Actualiza Estudiante, Requisitos y datos oficiales del periodo. No publica notas.</p>
          </div>
          <button class="icon-button" value="cancel" aria-label="Cerrar">×</button>
        </div>
        <label>
          Periodo
          <select name="period_id" required>
            <option value="">Cargando periodos...</option>
          </select>
        </label>
        <div id="firebase-period-note" class="empty-mini" style="margin-top:8px"></div>
        <div class="dialog-actions">
          <button class="button secondary" value="cancel">Cancelar</button>
          <button class="button primary" id="firebase-sync-submit" value="default">
            Sincronizar
          </button>
        </div>
      </form>`;
    document.body.appendChild(dialog);

    const form = dialog.querySelector("#firebase-sync-form");
    const select = form.elements.period_id;
    const note = dialog.querySelector("#firebase-period-note");

    select.addEventListener("change", () => {
      const option = select.selectedOptions[0];
      setText(note, option?.dataset.note || "");
    });

    form.addEventListener("submit", async event => {
      event.preventDefault();
      const periodId = String(select.value || "").trim();
      if (!periodId) return;

      const submit = dialog.querySelector("#firebase-sync-submit");
      submit.disabled = true;
      setText(submit, "Sincronizando...");
      try {
        const result = await api("/api/firebase/sync", {
          method: "POST",
          body: JSON.stringify({ period_id: periodId }),
        });
        dialog.close();
        await loadReports();
        if (result.report_id) await openReport(Number(result.report_id));

        const typeText = result.report_type === "pvc"
          ? "PVC"
          : "Presencial + Online";
        toast(`Fuentes oficiales sincronizadas: ${typeText}. Las notas no fueron publicadas.`, false);
      } catch (error) {
        toast(error.message || "No se pudo sincronizar Firebase.", true);
      } finally {
        submit.disabled = false;
        setText(submit, "Sincronizar");
      }
    });

    return dialog;
  }

  async function openSync() {
    const dialog = ensureDialog();
    const select = dialog.querySelector("[name=period_id]");
    const note = dialog.querySelector("#firebase-period-note");
    select.innerHTML = '<option value="">Cargando periodos...</option>';
    setText(note, "");
    dialog.showModal();

    try {
      const data = await api("/api/firebase/periods");
      const periods = data.periods || [];
      if (!periods.length) {
        select.innerHTML = '<option value="">No hay periodos disponibles</option>';
        return;
      }
      select.innerHTML = periods.map(period => {
        const label = escapeHtml(period.label || period.periodoId);
        const id = escapeHtml(period.periodoId);
        const type = period.report_type === "pvc" ? "PVC" : "Normal";
        const noteText = period.report_type === "pvc"
          ? "Se generará un solo informe PVC. Se ignora Online."
          : "Se generarán los informes Presencial y Online.";
        return `<option value="${id}" data-note="${escapeHtml(noteText)}">${label} · ${type}</option>`;
      }).join("");
      select.dispatchEvent(new Event("change"));
    } catch (error) {
      select.innerHTML = '<option value="">No se pudieron cargar los periodos</option>';
      toast(error.message || "No se pudo conectar con Firebase.", true);
    }
  }

  function activeReportId() {
    const candidates = [
      typeof state !== "undefined" && state.activeReport && state.activeReport.id,
      typeof state !== "undefined" && state.activeReportId,
      document.body.dataset.reportId,
    ];
    const value = candidates.find(item => Number(item) > 0);
    return value ? Number(value) : 0;
  }

  function moduleStatusHtml(item) {
    const issues = Array.isArray(item.issues) ? item.issues : [];
    const warnings = Array.isArray(item.warnings) ? item.warnings : [];
    const status = item.ready ? "Listo para publicar" : "Publicación bloqueada";
    const issueHtml = issues.length
      ? `<ul style="margin:8px 0 0 18px">${issues.slice(0, 8).map(value => `<li>${escapeHtml(value)}</li>`).join("")}</ul>`
      : "";
    const warningHtml = warnings.length
      ? `<p class="empty-mini" style="margin-top:8px">${escapeHtml(warnings.join(" "))}</p>`
      : "";
    return `
      <div class="panel" data-firebase-module="${escapeHtml(item.module)}" style="margin-top:12px">
        <div class="panel-head">
          <div>
            <h3 style="margin:0">${escapeHtml(item.label)}</h3>
            <p>${escapeHtml(status)} · ${Number(item.documents || 0)} documento(s)</p>
          </div>
          <button type="button" class="button ${item.ready ? "primary" : "secondary"} firebase-publish-module"
                  data-module="${escapeHtml(item.module)}" ${item.ready ? "" : "disabled"}>
            Publicar
          </button>
        </div>
        ${issueHtml}${warningHtml}
      </div>`;
  }

  function ensurePublicationDialog() {
    let dialog = document.querySelector("#firebase-publication-dialog");
    if (dialog) return dialog;
    dialog = document.createElement("dialog");
    dialog.id = "firebase-publication-dialog";
    dialog.innerHTML = `
      <div class="dialog-form" style="min-width:min(760px,90vw)">
        <div class="dialog-head">
          <div>
            <h2>Publicar notas en Firebase</h2>
            <p>Cada módulo se audita y publica por separado. Nunca se borran notas porque falten en una carga posterior.</p>
          </div>
          <button class="icon-button" type="button" id="firebase-publication-close" aria-label="Cerrar">×</button>
        </div>
        <div id="firebase-publication-content"><p>Cargando auditoría...</p></div>
        <div class="dialog-actions">
          <button class="button secondary" type="button" id="firebase-publication-refresh">Volver a auditar</button>
          <button class="button secondary" type="button" id="firebase-publication-done">Cerrar</button>
        </div>
      </div>`;
    document.body.appendChild(dialog);
    dialog.querySelector("#firebase-publication-close")?.addEventListener("click", () => dialog.close());
    dialog.querySelector("#firebase-publication-done")?.addEventListener("click", () => dialog.close());
    dialog.querySelector("#firebase-publication-refresh")?.addEventListener("click", () => refreshPublicationDialog(dialog));
    return dialog;
  }

  async function refreshPublicationDialog(dialog) {
    const reportId = activeReportId();
    const content = dialog.querySelector("#firebase-publication-content");
    if (!reportId) {
      content.innerHTML = "<p>Seleccione un informe antes de publicar.</p>";
      return;
    }
    content.innerHTML = "<p>Conciliando estudiantes y auditando los módulos...</p>";
    try {
      const result = await api(`/api/firebase/publication-status?report_id=${reportId}`);
      content.innerHTML = (result.modules || []).map(moduleStatusHtml).join("")
        || "<p>No hay módulos publicables para este informe.</p>";
      content.querySelectorAll(".firebase-publish-module").forEach(button => {
        button.addEventListener("click", async () => {
          const module = button.dataset.module;
          const original = button.textContent;
          button.disabled = true;
          button.textContent = "Publicando...";
          try {
            const published = await api("/api/firebase/publish", {
              method: "POST",
              body: JSON.stringify({ report_id: reportId, module }),
            });
            toast(
              `${published.label}: ${published.written || 0} actualizado(s), ${published.unchanged || 0} sin cambios.`,
              false
            );
            await refreshPublicationDialog(dialog);
          } catch (error) {
            toast(error.message || "No se pudo publicar el módulo.", true);
            await refreshPublicationDialog(dialog);
          } finally {
            button.textContent = original;
          }
        });
      });
    } catch (error) {
      content.innerHTML = `<div class="empty-state"><h3>No se pudo auditar</h3><p>${escapeHtml(error.message || "Error de publicación")}</p></div>`;
    }
  }

  async function openPublication() {
    const dialog = ensurePublicationDialog();
    dialog.showModal();
    await refreshPublicationDialog(dialog);
  }

  function installButton() {
    const actions = document.querySelector(".top-actions");
    if (!actions) return;
    if (!document.querySelector("#firebase-sync-btn")) {
      const button = document.createElement("button");
      button.className = "button secondary";
      button.id = "firebase-sync-btn";
      button.type = "button";
      button.textContent = "Sincronizar Firebase";
      button.addEventListener("click", openSync);
      actions.insertBefore(button, document.querySelector("#new-report-btn"));
    }
    let publish = document.querySelector("#firebase-publish-btn");
    if (!publish) {
      publish = document.createElement("button");
      publish.className = "button primary";
      publish.id = "firebase-publish-btn";
      publish.type = "button";
      publish.textContent = "Publicar notas";
      publish.addEventListener("click", openPublication);
      actions.insertBefore(publish, document.querySelector("#new-report-btn"));
    }
    publish.hidden = !activeReportId();
  }

  installButton();
  decorate();

  let renderQueued = false;
  const observer = new MutationObserver(() => {
    if (renderQueued) return;
    renderQueued = true;
    requestAnimationFrame(() => {
      renderQueued = false;
      installButton();
      decorate();
    });
  });
  observer.observe(document.body, { childList: true, subtree: true });
})();
