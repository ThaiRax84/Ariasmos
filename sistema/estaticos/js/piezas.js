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

    var destino = contenedor.getAttribute("data-total") ? document.getElementById(contenedor.getAttribute("data-total")) : null;

    function sumarPropio() {
      if (!destino) { return; }
      var total = 0;
      contenedor.querySelectorAll(".pieza[data-centavos] input").forEach(function (campo) {
        var valor = parseInt(campo.closest(".pieza").getAttribute("data-centavos"), 10);
        if (!isNaN(valor)) { total += leer(campo) * valor; }
      });
      destino.textContent = formatear(total, simbolo);
      if (codigo) { destino.appendChild(crear("span", "moneda", codigo)); }
    }

    function sumar() {
      sumarPropio();
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
      if (!campo || !etiqueta || pieza.classList.contains("con-mosaico")) { return; }
      var nombre = "";
      etiqueta.childNodes.forEach(function (nodo) { if (nodo.nodeType === 3) { nombre += nodo.textContent; } });
      nombre = nombre.trim();
      var tocar = crear("button", "mosaico");
      tocar.type = "button";
      var denominacion = crear("span", "mosaico-valor", nombre);
      var cuenta = crear("span", "mosaico-cuenta");
      tocar.appendChild(denominacion);
      tocar.appendChild(cuenta);
      var quitar = crear("button", "mosaico-quitar", "\u2212");
      quitar.type = "button";
      quitar.setAttribute("aria-label", "Quitar una pieza de " + nombre);
      pieza.classList.add("con-mosaico");
      if (pieza.getAttribute("data-tipo") === "moneda") { pieza.classList.add("es-moneda"); }
      var rotulo = pieza.getAttribute("data-rotulo") || "\u2014";
      pieza.insertBefore(tocar, pieza.firstChild);
      pieza.appendChild(quitar);
      var tecleo = 0;

      function pintar() {
        var piezasActuales = leer(campo);
        cuenta.textContent = piezasActuales > 0 ? "\u00d7 " + piezasActuales : rotulo;
        tocar.setAttribute("aria-label", "Agregar una pieza de " + nombre + ". Llevas " + piezasActuales);
        pieza.classList.toggle("elegida", piezasActuales > 0);
        quitar.tabIndex = piezasActuales > 0 ? 0 : -1;
        sumar();
        formulario.dispatchEvent(new CustomEvent("piezas-cambio", { bubbles: true }));
      }

      function poner(cantidad) {
        var maximo = parseInt(campo.getAttribute("max"), 10);
        if (!isNaN(maximo) && cantidad > maximo) { cantidad = maximo; }
        campo.value = String(Math.max(0, cantidad));
        pintar();
      }

      tocar.addEventListener("click", function () {
        poner(leer(campo) + 1);
        tocar.classList.remove("toque");
        void tocar.offsetWidth;
        tocar.classList.add("toque");
        if (!quieto()) {
          var vuela = crear("span", "vuela", "+" + nombre);
          pieza.appendChild(vuela);
          window.setTimeout(function () { vuela.remove(); }, 640);
        }
      });
      quitar.addEventListener("click", function () {
        poner(leer(campo) - 1);
        if (!leer(campo)) { tocar.focus(); }
      });
      [tocar, quitar].forEach(function (boton) {
        boton.addEventListener("keydown", function (evento) {
          if (!/^[0-9]$/.test(evento.key) && evento.key !== "Backspace") { return; }
          evento.preventDefault();
          var ahora = Date.now();
          var previo = ahora - tecleo < 1200 ? String(leer(campo) || "") : "";
          tecleo = ahora;
          poner(evento.key === "Backspace" ? 0 : Math.min(999, parseInt(previo + evento.key, 10)));
          tocar.focus();
        });
      });
      campo.addEventListener("input", pintar);
      pintar();
    });
  }

  function quieto() {
    return window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  function preparar(raiz) {
    raiz.querySelectorAll("[data-mosaicos]").forEach(function (contenedor) {
      if (!contenedor.classList.contains("mosaicos")) { prepararMosaicos(contenedor); }
    });
  }

  document.addEventListener("ariasmos:contenido", function (evento) { preparar(evento.target); });

  document.addEventListener("DOMContentLoaded", function () { preparar(document); });
}());
