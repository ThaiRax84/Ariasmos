(function () {
  "use strict";

  function formatear(centavos, simbolo) {
    var enteros = Math.floor(centavos / 100).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
    var resto = ("0" + (centavos % 100)).slice(-2);
    return simbolo + enteros + "." + resto;
  }

  function leer(campo) {
    var valor = (campo.value || "").trim();
    return /^[0-9]{1,6}$/.test(valor) ? parseInt(valor, 10) : 0;
  }

  function crear(etiqueta, clase, texto) {
    var elemento = document.createElement(etiqueta);
    if (clase) { elemento.className = clase; }
    if (texto) { elemento.textContent = texto; }
    return elemento;
  }

  function prepararMosaicos(contenedor) {
    var simbolo = contenedor.getAttribute("data-simbolo") || "$";
    var codigo = contenedor.getAttribute("data-moneda") || "";
    var formulario = contenedor.closest("form") || document;
    var recibido = formulario.querySelector("[data-recibido]");
    var cuadro = formulario.querySelector("[data-recibido-cuadro]");
    var piezas = Array.prototype.slice.call(contenedor.querySelectorAll(".pieza[data-centavos]"));
    contenedor.classList.add("mosaicos");
    formulario.querySelectorAll("[data-ayuda-sin-js]").forEach(function (ayuda) { ayuda.hidden = true; });
    formulario.querySelectorAll("[data-ayuda-con-js]").forEach(function (ayuda) { ayuda.hidden = false; });
    if (cuadro && contenedor.contains(formulario.querySelector(".pieza input[name^='r_']"))) { cuadro.hidden = false; }

    function sumar() {
      if (!recibido) { return; }
      var total = 0;
      formulario.querySelectorAll(".pieza[data-centavos] input[name^='r_']").forEach(function (campo) {
        var valor = parseInt(campo.closest(".pieza").getAttribute("data-centavos"), 10);
        if (!isNaN(valor)) { total += leer(campo) * valor; }
      });
      recibido.textContent = formatear(total, simbolo);
      if (codigo) {
        var moneda = crear("span", "moneda", codigo);
        recibido.appendChild(moneda);
      }
    }

    piezas.forEach(function (pieza) {
      var campo = pieza.querySelector("input");
      var etiqueta = pieza.querySelector(".denominacion");
      if (!campo || !etiqueta) { return; }
      var nombre = "";
      etiqueta.childNodes.forEach(function (nodo) { if (nodo.nodeType === 3) { nombre += nodo.textContent; } });
      nombre = nombre.trim();
      var tocar = crear("button", "mosaico");
      tocar.type = "button";
      var denominacion = crear("span", "mosaico-valor", nombre);
      var cuenta = crear("span", "mosaico-cuenta");
      tocar.appendChild(denominacion);
      tocar.appendChild(cuenta);
      var quitar = crear("button", "mosaico-quitar", "−");
      quitar.type = "button";
      quitar.setAttribute("aria-label", "Quitar una pieza de " + nombre);
      pieza.classList.add("con-mosaico");
      pieza.insertBefore(tocar, pieza.firstChild);
      pieza.appendChild(quitar);

      function pintar() {
        var piezasActuales = leer(campo);
        cuenta.textContent = piezasActuales > 0 ? "× " + piezasActuales : "—";
        tocar.setAttribute("aria-label", "Agregar una pieza de " + nombre + ". Llevas " + piezasActuales);
        pieza.classList.toggle("elegida", piezasActuales > 0);
        quitar.disabled = piezasActuales <= 0;
        sumar();
      }

      tocar.addEventListener("click", function () {
        var maximo = parseInt(campo.getAttribute("max"), 10);
        var nuevo = leer(campo) + 1;
        if (!isNaN(maximo) && nuevo > maximo) { nuevo = maximo; }
        campo.value = String(nuevo);
        pintar();
      });
      quitar.addEventListener("click", function () {
        campo.value = String(Math.max(0, leer(campo) - 1));
        pintar();
      });
      campo.addEventListener("input", pintar);
      pintar();
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-mosaicos]").forEach(prepararMosaicos);
  });
}());
