(function () {
  "use strict";

  function formatear(centavos, simbolo) {
    var enteros = Math.floor(centavos / 100).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
    var resto = ("0" + (centavos % 100)).slice(-2);
    return simbolo + enteros + "." + resto;
  }

  function sencillo(texto) {
    return (texto || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").trim();
  }

  function leer(campo) {
    var valor = (campo.value || "").trim();
    if (!/^[0-9]{1,7}$/.test(valor)) { return 0; }
    return parseInt(valor, 10);
  }

  function tope(campo) {
    var maximo = parseInt(campo.getAttribute("max"), 10);
    return isNaN(maximo) ? 9999999 : maximo;
  }

  function prepararVenta(formulario) {
    var simbolo = formulario.getAttribute("data-simbolo") || "$";
    var codigo = formulario.getAttribute("data-moneda") || "";
    var filas = Array.prototype.slice.call(formulario.querySelectorAll("tr[data-articulo]"));
    var renglones = formulario.querySelector("[data-resumen-renglones]");
    var vacio = formulario.querySelector("[data-resumen-vacio]");
    var total = formulario.querySelector("[data-resumen-total]");
    var resumen = formulario.querySelector("[data-resumen]");
    var sinJs = formulario.querySelector("[data-resumen-sin-js]");
    var boton = formulario.querySelector("[data-boton-venta]");
    var buscador = formulario.querySelector("[data-buscar-articulo]");
    var sinCoincidencias = formulario.querySelector("[data-sin-coincidencias]");

    formulario.classList.add("con-js");
    if (resumen) { resumen.hidden = false; }
    if (sinJs) { sinJs.hidden = true; }

    function actualizar() {
      var suma = 0;
      var cuantos = 0;
      if (renglones) { renglones.textContent = ""; }
      filas.forEach(function (fila) {
        var campo = fila.querySelector("[data-cantidad]");
        if (!campo) { return; }
        var cantidad = leer(campo);
        var precio = parseInt(fila.getAttribute("data-precio"), 10);
        fila.classList.toggle("elegida", cantidad > 0);
        if (cantidad <= 0 || isNaN(precio)) { return; }
        var importe = cantidad * precio;
        suma += importe;
        cuantos += 1;
        if (renglones) {
          var renglon = document.createElement("li");
          var nombre = document.createElement("span");
          nombre.textContent = cantidad + " × " + fila.getAttribute("data-nombre");
          var cifra = document.createElement("strong");
          cifra.textContent = formatear(importe, simbolo);
          renglon.appendChild(nombre);
          renglon.appendChild(cifra);
          renglones.appendChild(renglon);
        }
      });
      if (vacio) { vacio.hidden = cuantos > 0; }
      if (total) {
        total.textContent = formatear(suma, simbolo);
        if (codigo) {
          var moneda = document.createElement("span");
          moneda.className = "moneda";
          moneda.textContent = codigo;
          total.appendChild(moneda);
        }
      }
    }

    function textoBoton() {
      if (!boton) { return; }
      var elegida = formulario.querySelector(".opcion input[type=radio]:checked");
      var etiqueta = elegida ? elegida.closest("[data-boton]") : null;
      var texto = etiqueta ? etiqueta.getAttribute("data-boton") : boton.getAttribute("data-texto");
      if (texto) { boton.textContent = texto; }
    }

    filas.forEach(function (fila) {
      var campo = fila.querySelector("[data-cantidad]");
      if (!campo) { return; }
      var quitar = fila.querySelector("[data-quitar]");
      var agregar = fila.querySelector("[data-agregar]");
      var cambiar = function (paso) {
        var nuevo = Math.min(tope(campo), Math.max(0, leer(campo) + paso));
        campo.value = String(nuevo);
        campo.dispatchEvent(new Event("input", { bubbles: true }));
      };
      if (quitar) { quitar.hidden = false; quitar.addEventListener("click", function () { cambiar(-1); }); }
      if (agregar) { agregar.hidden = false; agregar.addEventListener("click", function () { cambiar(1); }); }
      campo.addEventListener("focus", function () { campo.select(); });
    });

    if (buscador) {
      var caja = buscador.querySelector("input");
      buscador.hidden = false;
      caja.addEventListener("keydown", function (evento) { if (evento.key === "Enter") { evento.preventDefault(); } });
      caja.addEventListener("input", function () {
        var texto = sencillo(caja.value);
        var visibles = 0;
        filas.forEach(function (fila) {
          var coincide = !texto || sencillo(fila.getAttribute("data-buscar")).indexOf(texto) !== -1;
          fila.hidden = !coincide;
          if (coincide) { visibles += 1; }
        });
        if (sinCoincidencias) { sinCoincidencias.hidden = visibles > 0 || filas.length === 0; }
      });
    }

    formulario.addEventListener("input", function (evento) {
      if (evento.target && evento.target.hasAttribute("data-cantidad")) { actualizar(); }
    });
    formulario.addEventListener("change", textoBoton);
    actualizar();
    textoBoton();
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-venta]").forEach(prepararVenta);
  });
}());
