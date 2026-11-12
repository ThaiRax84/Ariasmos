document.addEventListener("DOMContentLoaded", function () {
  var imprimir = document.getElementById("imprimir");
  if (imprimir) {
    imprimir.addEventListener("click", function () { window.print(); });
  }
  document.querySelectorAll("[data-confirmar]").forEach(function (boton) {
    boton.addEventListener("click", function (evento) {
      if (!window.confirm(boton.getAttribute("data-confirmar"))) {
        evento.preventDefault();
      }
    });
  });
});
