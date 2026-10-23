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

  function setMenuOpen(open) {
    shell.classList.toggle("menu-open", open);
    document.body.classList.toggle("menu-lock", open);
  }

  if (toggle && shell) {
    toggle.addEventListener("click", function () {
      if (window.innerWidth < 992) {
        setMenuOpen(!shell.classList.contains("menu-open"));
        return;
      }
      shell.classList.toggle("collapsed");
      writePreference(shell.classList.contains("collapsed") ? "1" : "0");
    });
    // Phone/tablet drawer: close it by tapping outside, with Escape, or when
    // the screen grows back to desktop size.
    const backdrop = document.getElementById("sidebarBackdrop");
    if (backdrop) {
      backdrop.addEventListener("click", function () { setMenuOpen(false); });
    }
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && shell.classList.contains("menu-open")) { setMenuOpen(false); }
    });
    window.addEventListener("resize", function () {
      if (window.innerWidth >= 992 && shell.classList.contains("menu-open")) { setMenuOpen(false); }
    });
  }

  // Confirmation for sensitive operations.
  document.querySelectorAll("form[data-confirm]:not([data-ajax-form])").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      if (!window.confirm(form.dataset.confirm)) {
        event.preventDefault();
      }
    });
  });

  // Prevent double submission (payments, loans).
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
    const initialBody = body ? body.innerHTML : "";
    const modal = form.closest(".modal");
    // Optional confirmation step (data-confirm-step): the first submit shows
    // a summary of the data; the second one ("Yes, ...") really sends it.
    const hasConfirmStep = form.hasAttribute("data-confirm-step");
    let confirming = false;

    form.querySelectorAll("button[type=submit]").forEach(function (button) {
      button.dataset.label = button.textContent;
    });

    function activeButton() {
      return form.querySelector("[data-step]:not(.d-none) button[type=submit]")
        || form.querySelector("button[type=submit]");
    }

    function setBusy(busy) {
      const button = activeButton();
      if (!button) { return; }
      button.disabled = busy;
      button.textContent = busy ? (button.dataset.busyLabel || "...") : button.dataset.label;
    }

    function showStep(name) {
      form.querySelectorAll("[data-step]").forEach(function (element) {
        element.classList.toggle("d-none", element.dataset.step !== name);
      });
      confirming = name === "confirm";
    }

    function focusFirstField() {
      let field = form.querySelector(".is-invalid");
      if (!field) {
        // First empty field (e.g. the principal when the customer is preselected).
        field = Array.prototype.find.call(
          (body || form).querySelectorAll("input:not([type=hidden]), select, textarea"),
          function (element) { return !element.value; });
      }
      if (field) { field.focus(); }
    }

    function fieldValue(name) {
      const field = form.querySelector("[name=" + name + "]");
      return field ? field.value.trim() : "";
    }

    function fieldText(name) {
      const field = form.querySelector("[name=" + name + "]");
      if (!field) { return ""; }
      if (field.tagName === "SELECT") {
        const option = field.options[field.selectedIndex];
        return option ? option.textContent.trim() : "";
      }
      return field.value.trim();
    }

    function formatDate(value) {
      const parts = value.split("-");
      return parts.length === 3 ? parts[2] + "/" + parts[1] + "/" + parts[0] : value;
    }

    function formatMoney(value) {
      const number = Number(value);
      if (!value || isNaN(number)) { return value || "-"; }
      return number.toLocaleString("es-MX", { style: "currency", currency: "MXN" });
    }

    function previewValue(name) {
      const element = form.querySelector("[data-preview] [data-field=" + name + "]");
      const text = element ? element.textContent.trim() : "";
      return text && text !== "-" ? text : "";
    }

    // Required data present? If not, skip the summary: the server answers
    // with the errors and nothing is saved.
    function looksComplete() {
      return ["customer", "principal", "installment_count", "first_payment_date"]
        .every(function (name) { return fieldValue(name) !== ""; });
    }

    function fillSummary() {
      const installment = previewValue("installment");
      const last = form.querySelector("[data-preview] [data-field=last]:not(.d-none)");
      let installments = fieldValue("installment_count");
      if (installment) { installments += " \u00d7 " + installment; }
      const frequency = fieldText("payment_frequency");
      if (frequency) { installments += " (" + frequency.toLowerCase() + ")"; }
      if (last && last.textContent.trim() && last.textContent.trim() !== "-") {
        installments += " \u00b7 " + last.textContent.trim();
      }
      const values = {
        customer: fieldText("customer"),
        principal: formatMoney(fieldValue("principal")),
        interest: previewValue("interest"),
        total: previewValue("total"),
        installments: installments,
        first_payment: formatDate(fieldValue("first_payment_date")),
        final: previewValue("final"),
      };
      Object.keys(values).forEach(function (key) {
        const element = form.querySelector("[data-summary=" + key + "]");
        if (element) { element.textContent = values[key] || "-"; }
      });
    }

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      if (hasConfirmStep && !confirming && looksComplete()) {
        fillSummary();
        showStep("confirm");
        const button = activeButton();
        if (button) { button.focus(); }
        return;
      }
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
          setBusy(false);
          if (hasConfirmStep) { showStep("edit"); }
          if (body && data.html) { body.innerHTML = data.html; }
          focusFirstField();
        })
        .catch(function () {
          // Unexpected answer: fall back to a normal (non-fetch) submission.
          form.submit();
        });
    });

    form.querySelectorAll("[data-step-back]").forEach(function (button) {
      button.addEventListener("click", function () {
        showStep("edit");
        focusFirstField();
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
      // No automatic focus on touch screens (it pops the keyboard up) or on
      // forms loaded on demand ([data-no-autofocus]).
      const canHover = window.matchMedia && window.matchMedia("(hover: hover)").matches;
      if (canHover && !form.hasAttribute("data-no-autofocus")) {
        modal.addEventListener("shown.bs.modal", focusFirstField);
      }
      modal.addEventListener("hidden.bs.modal", function () {
        if (body) { body.innerHTML = initialBody; }
        form.reset();
        setBusy(false);
        if (hasConfirmStep) { showStep("edit"); }
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

// Payment detail modal (payments list): clicking a row opens the payment in a modal.
document.addEventListener('click', function (e) {
  const trigger = e.target.closest('.js-payment-modal');
  if (!trigger) { return; }
  // Let other links/buttons inside the row (e.g. the loan) work normally,
  // and keep ctrl/cmd/middle click opening the full page in a new tab.
  const innerLink = e.target.closest('a, button');
  if (innerLink && innerLink !== trigger && innerLink.classList.contains('js-no-modal')) { return; }
  if (e.ctrlKey || e.metaKey || e.shiftKey || e.button === 1) { return; }

  const modalEl = document.getElementById('paymentModal');
  if (!modalEl || typeof bootstrap === 'undefined') { return; }
  e.preventDefault();

  const body = document.getElementById('paymentModalBody');
  const title = document.getElementById('paymentModalLabel');
  const loadingText = modalEl.dataset.loadingText || 'Cargando...';
  const errorText = modalEl.dataset.errorText || 'No se pudo cargar el pago.';
  const url = new URL(trigger.dataset.url, window.location.origin);
  url.searchParams.set('modal', '1');

  if (trigger.dataset.title) { title.textContent = trigger.dataset.title; }
  body.innerHTML = '';
  const loading = document.createElement('p');
  loading.className = 'text-secondary mb-0';
  loading.textContent = loadingText;
  body.appendChild(loading);
  bootstrap.Modal.getOrCreateInstance(modalEl).show();

  const requestId = String(Date.now());
  modalEl.dataset.requestId = requestId;
  fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' }, credentials: 'same-origin' })
    .then(function (r) {
      if (!r.ok) { throw new Error('HTTP ' + r.status); }
      return r.text();
    })
    .then(function (html) {
      if (modalEl.dataset.requestId === requestId) { body.innerHTML = html; }
    })
    .catch(function () {
      if (modalEl.dataset.requestId !== requestId) { return; }
      body.innerHTML = '';
      const err = document.createElement('div');
      err.className = 'alert alert-danger mb-0';
      err.textContent = errorText;
      body.appendChild(err);
    });
});

// Forms loaded on demand into a modal (e.g. "Edit" a customer): the trigger
// carries data-url (the form page) and data-target (the modal). The form
// fragment is fetched with ?modal=1 and submitted by the [data-ajax-form]
// handler above.
document.addEventListener('click', function (e) {
  const trigger = e.target.closest('.js-remote-form');
  if (!trigger) { return; }
  if (e.ctrlKey || e.metaKey || e.shiftKey || e.button === 1) { return; }
  const modalEl = document.querySelector(trigger.dataset.target);
  if (!modalEl || typeof bootstrap === 'undefined') { return; }
  e.preventDefault();

  const form = modalEl.querySelector('form');
  const body = modalEl.querySelector('[data-form-body]');
  const next = form.querySelector('[name=next]');
  const loadingText = modalEl.dataset.loadingText || 'Cargando...';
  const errorText = modalEl.dataset.errorText || 'No se pudo cargar el formulario.';
  const url = new URL(trigger.dataset.url, window.location.origin);

  form.action = url.pathname;
  if (next) { next.value = trigger.dataset.next || ''; }
  body.innerHTML = '';
  const loading = document.createElement('p');
  loading.className = 'text-secondary mb-0';
  loading.textContent = loadingText;
  body.appendChild(loading);
  bootstrap.Modal.getOrCreateInstance(modalEl).show();

  const requestId = String(Date.now());
  modalEl.dataset.requestId = requestId;
  url.searchParams.set('modal', '1');
  fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' }, credentials: 'same-origin' })
    .then(function (r) {
      if (!r.ok) { throw new Error('HTTP ' + r.status); }
      return r.text();
    })
    .then(function (html) {
      if (modalEl.dataset.requestId !== requestId) { return; }
      body.innerHTML = html;
      body.scrollTop = 0;
      if (window.matchMedia && window.matchMedia('(hover: hover)').matches) {
        const first = body.querySelector('input:not([type=hidden]), select, textarea');
        if (first) { first.focus({ preventScroll: true }); }
      }
    })
    .catch(function () {
      if (modalEl.dataset.requestId !== requestId) { return; }
      body.innerHTML = '';
      const err = document.createElement('div');
      err.className = 'alert alert-danger mb-0';
      err.textContent = errorText;
      body.appendChild(err);
    });
});

document.addEventListener("click", function (event) {
  const link = event.target.closest(".js-customer-summary");
  if (!link) return;

  // Permite abrir el enlace normalmente en otra pestaña con Ctrl o clic del medio.
  if (event.ctrlKey || event.metaKey || event.shiftKey || event.button === 1) return;

  const modal = document.getElementById("customerSummaryModal");
  if (!modal || typeof bootstrap === "undefined") return;

  event.preventDefault();

  document.getElementById("customerSummaryTitle").textContent = link.dataset.name;
  document.getElementById("summaryCode").textContent = link.dataset.code || "-";
  document.getElementById("summaryPhone").textContent = link.dataset.phone || "-";
  document.getElementById("summaryLoans").textContent = link.dataset.loans || "0";
  document.getElementById("summaryStatus").textContent = link.dataset.status || "-";

  bootstrap.Modal.getOrCreateInstance(modal).show();
});