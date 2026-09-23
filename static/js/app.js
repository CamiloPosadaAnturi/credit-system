// Interacciones generales del sistema.
(function () {
  "use strict";

  const shell = document.getElementById("appShell");
  const boton = document.getElementById("btnMenu");
  const CLAVE = "sidebar-colapsado";

  if (shell && localStorage.getItem(CLAVE) === "1") {
    shell.classList.add("colapsado");
  }

  if (boton && shell) {
    boton.addEventListener("click", function () {
      if (window.innerWidth < 992) {
        shell.classList.toggle("menu-abierto");
        return;
      }
      shell.classList.toggle("colapsado");
      localStorage.setItem(CLAVE, shell.classList.contains("colapsado") ? "1" : "0");
    });
  }

  // Confirmacion para operaciones sensibles.
  document.querySelectorAll("form[data-confirmar]").forEach(function (formulario) {
    formulario.addEventListener("submit", function (evento) {
      if (!window.confirm(formulario.dataset.confirmar)) {
        evento.preventDefault();
      }
    });
  });

  // Evita doble envio de formularios (pagos, aprobaciones).
  document.querySelectorAll("form[data-una-vez]").forEach(function (formulario) {
    formulario.addEventListener("submit", function () {
      const boton = formulario.querySelector("button[type=submit]");
      if (boton) {
        boton.disabled = true;
        boton.innerHTML = "Procesando...";
      }
    });
  });

  // Previsualizacion en vivo de las condiciones del credito.
  // IMPORTANTE: es solo informativa; el servidor recalcula todo al guardar.
  const simulador = document.getElementById("simulador");
  if (simulador) {
    const campos = ["capital", "tasa_interes", "numero_cuotas", "modalidad_interes",
                    "frecuencia_pago", "dias_personalizados"];
    const salida = document.getElementById("simulacion-salida");

    function moneda(valor) {
      return "$" + Number(valor).toLocaleString("es-MX", { minimumFractionDigits: 2 });
    }

    function simular() {
      const datos = {};
      campos.forEach(function (nombre) {
        const campo = simulador.querySelector("[name=" + nombre + "]");
        if (campo) { datos[nombre] = campo.value; }
      });
      if (!datos.capital || !datos.numero_cuotas) { return; }
      fetch(simulador.dataset.url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": simulador.dataset.csrf,
        },
        body: JSON.stringify(datos),
      })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (datos) {
          if (!datos || !salida) { return; }
          salida.querySelector("[data-campo=interes]").textContent = moneda(datos.interes_total);
          salida.querySelector("[data-campo=total]").textContent = moneda(datos.total_a_pagar);
          salida.querySelector("[data-campo=cuota]").textContent = moneda(datos.importe_cuota);
          salida.querySelector("[data-campo=ultima]").textContent = moneda(datos.importe_ultima_cuota);
          salida.classList.remove("d-none");
        })
        .catch(function () { /* la previsualizacion es opcional */ });
    }

    campos.forEach(function (nombre) {
      const campo = simulador.querySelector("[name=" + nombre + "]");
      if (campo) { campo.addEventListener("change", simular); campo.addEventListener("keyup", simular); }
    });
    simular();
  }
})();
