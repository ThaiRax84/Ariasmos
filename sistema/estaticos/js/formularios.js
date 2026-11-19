(function () {
  "use strict";

  function sinAcentos(texto) {
    return (texto || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  }

  function prepararZona(lista) {
    var contenedor = lista.parentNode;
    var buscador = document.createElement("input");
    buscador.type = "search";
    buscador.className = "buscar-zona";
    buscador.placeholder = "Busca una ciudad, por ejemplo Monterrey o Madrid";
    buscador.setAttribute("aria-label", "Buscar zona horaria por ciudad");
    buscador.autocomplete = "off";
    contenedor.insertBefore(buscador, lista);
    var aviso = document.createElement("small");
    aviso.className = "zona-propuesta";
    aviso.hidden = true;
    contenedor.insertBefore(aviso, lista.nextSibling);

    function filtrar() {
      var texto = sinAcentos(buscador.value.trim());
      var visibles = 0;
      Array.prototype.forEach.call(lista.querySelectorAll("optgroup"), function (grupo) {
        var enGrupo = 0;
        Array.prototype.forEach.call(grupo.querySelectorAll("option"), function (opcion) {
          var coincide = !texto || sinAcentos(opcion.textContent + " " + opcion.value).indexOf(texto) !== -1;
          opcion.hidden = !coincide;
          if (coincide) { enGrupo += 1; }
        });
        grupo.hidden = enGrupo === 0;
        visibles += enGrupo;
      });
      lista.size = texto ? Math.max(2, Math.min(8, visibles + 1)) : 0;
      return visibles;
    }

    buscador.addEventListener("input", filtrar);
    buscador.addEventListener("keydown", function (evento) {
      if (evento.key === "Enter") {
        evento.preventDefault();
        var primera = lista.querySelector("optgroup:not([hidden]) option:not([hidden])");
        if (primera) {
          lista.value = primera.value;
          buscador.value = "";
          filtrar();
          lista.focus();
        }
      } else if (evento.key === "ArrowDown") {
        evento.preventDefault();
        lista.focus();
      }
    });
    lista.addEventListener("change", function () {
      if (buscador.value) {
        buscador.value = "";
        filtrar();
      }
      aviso.hidden = true;
    });

    if (lista.hasAttribute("data-proponer-local") && !lista.value) {
      var local = "";
      try { local = Intl.DateTimeFormat().resolvedOptions().timeZone || ""; } catch (error) { local = ""; }
      var opcion = local ? lista.querySelector('option[value="' + local.replace(/"/g, "") + '"]') : null;
      if (opcion) {
        lista.value = local;
        aviso.textContent = "Te proponemos la zona de esta computadora. Cámbiala si el negocio está en otra.";
        aviso.hidden = false;
      }
    }
  }

  function prepararEnvioAlCambiar() {
    document.querySelectorAll("[data-enviar-al-cambiar]").forEach(function (control) {
      var formulario = control.form;
      if (!formulario) { return; }
      formulario.querySelectorAll("[data-solo-sin-js]").forEach(function (boton) { boton.hidden = true; });
      control.addEventListener("change", function () {
        if (formulario.requestSubmit) { formulario.requestSubmit(); } else { formulario.submit(); }
      });
    });
  }

  function prepararPlegables() {
    document.querySelectorAll("details[data-abrir-con-error]").forEach(function (plegable) {
      if (plegable.querySelector(".con-error, .error")) { plegable.open = true; }
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("select[data-buscar-zona]").forEach(prepararZona);
    prepararEnvioAlCambiar();
    prepararPlegables();
  });
}());
