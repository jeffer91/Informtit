(function () {
  "use strict";

  function reportType(report) {
    return String(report?.report_type || "").toLowerCase() === "pvc" ? "pvc" : "normal";
  }

  function decorate() {
    try {
      const footer = document.querySelector(".sidebar-footer span:last-child");
      if (footer) footer.textContent = "Firebase + respaldo local";

      document.querySelectorAll(".report-card").forEach(card => {
        const button = card.querySelector("[data-open-report]");
        if (!button || typeof state === "undefined") return;
        const report = (state.reports || []).find(
          item => Number(item.id) === Number(button.dataset.openReport)
        );
        if (!report) return;
        const badge = card.querySelector(".badge");
        if (badge && reportType(report) === "pvc") badge.textContent = "PVC";
      });

      if (typeof state !== "undefined" && state.activeReport) {
        const pvc = reportType(state.activeReport) === "pvc";
        const modality = document.querySelector("#report-modality");
        if (pvc && modality) modality.textContent = "PVC";

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
          value.textContent = "Firebase + local";
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
            <h2>Sincronizar Firebase</h2>
            <p>Seleccione el periodo. Informtit hará el resto.</p>
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
      note.textContent = option?.dataset.note || "";
    });

    form.addEventListener("submit", async event => {
      event.preventDefault();
      const periodId = String(select.value || "").trim();
      if (!periodId) return;

      const submit = dialog.querySelector("#firebase-sync-submit");
      submit.disabled = true;
      submit.textContent = "Sincronizando...";
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
        const warningText = (result.warnings || []).length
          ? " Algunos módulos no pudieron respaldarse; revise las reglas de Firebase."
          : "";
        toast(`Sincronizado: ${typeText}.${warningText}`, !!warningText);
        if (result.warnings?.length) {
          console.warn("[Informtit Firebase]", result.warnings);
        }
      } catch (error) {
        toast(error.message || "No se pudo sincronizar Firebase.", true);
      } finally {
        submit.disabled = false;
        submit.textContent = "Sincronizar";
      }
    });

    return dialog;
  }

  async function openSync() {
    const dialog = ensureDialog();
    const select = dialog.querySelector("[name=period_id]");
    const note = dialog.querySelector("#firebase-period-note");
    select.innerHTML = '<option value="">Cargando periodos...</option>';
    note.textContent = "";
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

  function installButton() {
    const actions = document.querySelector(".top-actions");
    if (!actions || document.querySelector("#firebase-sync-btn")) return;
    const button = document.createElement("button");
    button.className = "button secondary";
    button.id = "firebase-sync-btn";
    button.type = "button";
    button.textContent = "Sincronizar Firebase";
    button.addEventListener("click", openSync);
    actions.insertBefore(button, document.querySelector("#new-report-btn"));
  }

  installButton();
  decorate();

  const observer = new MutationObserver(() => {
    installButton();
    decorate();
  });
  observer.observe(document.body, { childList: true, subtree: true });
})();
