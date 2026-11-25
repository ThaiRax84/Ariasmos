(function () {
  "use strict";

  function iniciar(formulario) {
    var texto = formulario.querySelector("textarea");
    var vista = document.querySelector("[data-vista-previa]");
    if (!texto || !vista) { return; }
    var ejemplos = JSON.parse(vista.getAttribute("data-ejemplos"));

    function pintar() {
      vista.textContent = texto.value.replace(/\[([a-z_]+)\]/g, function (completo, nombre) {
        return Object.prototype.hasOwnProperty.call(ejemplos, nombre) ? ejemplos[nombre] : completo;
      });
    }

    Array.prototype.forEach.call(formulario.querySelectorAll("[data-variable]"), function (boton) {
      boton.addEventListener("click", function () {
        var dato = "[" + boton.getAttribute("data-variable") + "]";
        var inicio = texto.selectionStart;
        texto.value = texto.value.slice(0, inicio) + dato + texto.value.slice(texto.selectionEnd);
        texto.focus();
        texto.setSelectionRange(inicio + dato.length, inicio + dato.length);
        pintar();
      });
    });
    texto.addEventListener("input", pintar);
  }

  document.addEventListener("DOMContentLoaded", function () {
    Array.prototype.forEach.call(document.querySelectorAll("[data-mensaje]"), iniciar);
  });
})();
