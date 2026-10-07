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

  // Forms submitted with fetch (e.g. the "New customer" modal). The server
  // answers JSON: {ok: true, redirect} or {ok: false, html} with the form
  // re-rendered and its errors, which replaces the form body in place.
  document.querySelectorAll("form[data-ajax-form]").forEach(function (form) {
    const body = form.querySelector("[data-form-body]");
    const button = form.querySelector("button[type=submit]");
    const initialBody = body ? body.innerHTML : "";
    const buttonLabel = button ? button.textContent : "";
    const modal = form.closest(".modal");

    function setBusy(busy) {
      if (!button) { return; }
      button.disabled = busy;
      button.textContent = busy ? (button.dataset.busyLabel || "...") : buttonLabel;
    }

    function focusFirstField() {
      let field = form.querySelector(".is-invalid");
      if (!field) {
        // First empty field (e.g. the principal when the customer is preselected).
        field = Array.prototype.find.call(
          form.querySelectorAll("input:not([type=hidden]), select, textarea"),
          function (element) { return !element.value; });
      }
      if (field) { field.focus(); }
    }

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      setBusy(true);
      fetch(form.action, {
        method: "POST",
        headers: { "X-Requested-With": "XMLHttpRequest" },
        body: new FormData(form),
        credentials: "same-origin",
      })
        .then(function (response) { return response.json(); })
        .then(function (data) {
          if (data.ok) {
            window.location.href = data.redirect;
            return;
          }
          if (body && data.html) { body.innerHTML = data.html; }
          setBusy(false);
          focusFirstField();
        })
        .catch(function () {
          // Unexpected answer: fall back to a normal (non-fetch) submission.
          form.submit();
        });
    });

    if (modal) {
      // A button can preselect the customer: data-customer="<id>".
      modal.addEventListener("show.bs.modal", function (event) {
        const trigger = event.relatedTarget;
        const customer = form.querySelector("[name=customer]");
        if (trigger && trigger.dataset.customer && customer) {
          customer.value = trigger.dataset.customer;
        }
      });
      modal.addEventListener("shown.bs.modal", focusFirstField);
      modal.addEventListener("hidden.bs.modal", function () {
        if (body) { body.innerHTML = initialBody; }
        form.reset();
        setBusy(false);
      });
    }
  });

  // Live preview of the loan terms.
  // IMPORTANT: informational only; the server recomputes everything on save.
  document.querySelectorAll("form[data-simulate-url]").forEach(function (form) {
    const fieldNames = ["customer", "principal", "payment_frequency",
                        "installment_count", "first_payment_date"];
    const csrfInput = form.querySelector("[name=csrfmiddlewaretoken]");
    let timer = null;
    let sequence = 0;

    function currency(value) {
      return "$" + Number(value).toLocaleString("es-MX", {
        minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    function preview() { return form.querySelector("[data-preview]"); }

    function clear() {
      const box = preview();
      if (!box) { return; }
      box.querySelector("[data-preview-body]").classList.add("d-none");
      box.querySelector("[data-preview-empty]").classList.remove("d-none");
      const warnings = box.querySelector("[data-field=warnings]");
      warnings.classList.add("d-none");
      warnings.textContent = "";
    }

    function render(data) {
      const box = preview();
      if (!box) { return; }
      const warnings = box.querySelector("[data-field=warnings]");
      warnings.textContent = "";
      (data.warnings || []).forEach(function (text) {
        const line = document.createElement("div");
        line.textContent = text;
        warnings.appendChild(line);
      });
      warnings.classList.toggle("d-none", !(data.warnings || []).length);

      const body = box.querySelector("[data-preview-body]");
      const empty = box.querySelector("[data-preview-empty]");
      const result = data.simulation;
      if (!result) {
        body.classList.add("d-none");
        empty.classList.remove("d-none");
        return;
      }
      body.querySelector("[data-field=interest]").textContent = currency(result.total_interest);
      body.querySelector("[data-field=total]").textContent = currency(result.total_payable);
      body.querySelector("[data-field=installment]").textContent =
        result.installment_count + " x " + currency(result.installment_amount);
      body.querySelector("[data-field=last]").textContent = currency(result.last_installment_amount);
      body.querySelector("[data-field=final]").textContent = result.final_due_date;
      const lastDiffers = result.last_installment_amount !== result.installment_amount;
      body.querySelectorAll("[data-last]").forEach(function (element) {
        element.classList.toggle("d-none", !lastDiffers);
      });
      body.classList.remove("d-none");
      empty.classList.add("d-none");
    }

    function run() {
      const payload = {};
      fieldNames.forEach(function (name) {
        const field = form.querySelector("[name=" + name + "]");
        if (field) { payload[name] = field.value; }
      });
      const current = ++sequence;
      fetch(form.dataset.simulateUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfInput ? csrfInput.value : "",
        },
        body: JSON.stringify(payload),
        credentials: "same-origin",
      })
        .then(function (response) { return response.ok ? response.json() : null; })
        .then(function (data) {
          if (data && current === sequence) { render(data); }
        })
        .catch(function () { /* the preview is optional */ });
    }

    function schedule() {
      window.clearTimeout(timer);
      timer = window.setTimeout(run, 250);
    }

    // Delegated: the fields may be re-rendered after a validation error.
    form.addEventListener("input", schedule);
    form.addEventListener("change", schedule);

    const modal = form.closest(".modal");
    if (modal) {
      modal.addEventListener("shown.bs.modal", run);
      modal.addEventListener("hidden.bs.modal", function () { sequence += 1; clear(); });
    } else {
      run();
    }
  });
})();
