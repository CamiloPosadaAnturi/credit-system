// General interactions of the credit system.
(function () {
  "use strict";

  const shell = document.getElementById("appShell");
  const toggle = document.getElementById("menuToggle");
  const STORAGE_KEY = "sidebar-collapsed";

  function readPreference() {
    try {
      return localStorage.getItem(STORAGE_KEY);
    } catch (error) {
      return null;
    }
  }

  function writePreference(value) {
    try {
      localStorage.setItem(STORAGE_KEY, value);
    } catch (error) {
      /* private mode or blocked storage: the preference is simply not kept */
    }
  }

  if (shell && readPreference() === "1") {
    shell.classList.add("collapsed");
  }

  if (toggle && shell) {
    toggle.addEventListener("click", function () {
      if (window.innerWidth < 992) {
        shell.classList.toggle("menu-open");
        return;
      }
      shell.classList.toggle("collapsed");
      writePreference(shell.classList.contains("collapsed") ? "1" : "0");
    });
  }

  // Confirmation for sensitive operations.
  document.querySelectorAll("form[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      if (!window.confirm(form.dataset.confirm)) {
        event.preventDefault();
      }
    });
  });

  // Prevent double submission (payments, approvals).
  document.querySelectorAll("form[data-submit-once]").forEach(function (form) {
    form.addEventListener("submit", function () {
      const button = form.querySelector("button[type=submit]");
      if (button) {
        button.disabled = true;
        button.textContent = button.dataset.busyLabel || "...";
      }
    });
  });

  // Live preview of the loan terms.
  // IMPORTANT: informational only; the server recomputes everything on save.
  const simulator = document.getElementById("loanSimulator");
  if (simulator) {
    const fieldNames = ["principal", "interest_rate", "installment_count",
                        "interest_mode", "payment_frequency", "custom_days"];
    const output = document.getElementById("simulationOutput");

    function currency(value) {
      return "$" + Number(value).toLocaleString("es-MX", { minimumFractionDigits: 2 });
    }

    function runSimulation() {
      const payload = {};
      fieldNames.forEach(function (name) {
        const field = simulator.querySelector("[name=" + name + "]");
        if (field) { payload[name] = field.value; }
      });
      if (!payload.principal || !payload.installment_count) { return; }
      fetch(simulator.dataset.url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": simulator.dataset.csrf,
        },
        body: JSON.stringify(payload),
      })
        .then(function (response) { return response.ok ? response.json() : null; })
        .then(function (data) {
          if (!data || !output) { return; }
          output.querySelector("[data-field=interest]").textContent = currency(data.total_interest);
          output.querySelector("[data-field=total]").textContent = currency(data.total_payable);
          output.querySelector("[data-field=installment]").textContent = currency(data.installment_amount);
          output.querySelector("[data-field=last]").textContent = currency(data.last_installment_amount);
          output.classList.remove("d-none");
        })
        .catch(function () { /* the preview is optional */ });
    }

    fieldNames.forEach(function (name) {
      const field = simulator.querySelector("[name=" + name + "]");
      if (field) {
        field.addEventListener("change", runSimulation);
        field.addEventListener("keyup", runSimulation);
      }
    });
    runSimulation();
  }
})();
