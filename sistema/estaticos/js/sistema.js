(function () {
  "use strict";

  function crear(etiqueta, clase, texto) {
    var elemento = document.createElement(etiqueta);
    if (clase) { elemento.className = clase; }
    if (texto) { elemento.textContent = texto; }
    return elemento;
  }

  var dialogo = null;

  function armarDialogo() {
    if (dialogo) { return dialogo; }
    dialogo = crear("dialog", "dialogo");
    dialogo.setAttribute("aria-labelledby", "dialogo-titulo");
    dialogo.setAttribute("aria-describedby", "dialogo-texto");
    var caja = crear("div", "dialogo-caja");
    var titulo = crear("h2", "dialogo-titulo", "¿Seguro?");
    titulo.id = "dialogo-titulo";
    var texto = crear("p", "dialogo-texto");
    texto.id = "dialogo-texto";
    var acciones = crear("div", "dialogo-acciones");
    var cancelar = crear("button", "boton secundario", "Cancelar");
    cancelar.type = "button";
    cancelar.value = "no";
    var aceptar = crear("button", "boton", "Sí, continuar");
    aceptar.type = "button";
    aceptar.value = "si";
    acciones.appendChild(cancelar);
    acciones.appendChild(aceptar);
    caja.appendChild(titulo);
    caja.appendChild(texto);
    caja.appendChild(acciones);
    dialogo.appendChild(caja);
    cancelar.addEventListener("click", function () { dialogo.close("no"); });
    aceptar.addEventListener("click", function () { dialogo.close("si"); });
    dialogo.addEventListener("click", function (evento) { if (evento.target === dialogo) { dialogo.close("no"); } });
    document.body.appendChild(dialogo);
    return dialogo;
  }

  function confirmar(boton, continuar) {
    if (typeof HTMLDialogElement !== "function") {
      if (window.confirm(boton.getAttribute("data-confirmar"))) { continuar(); }
      return;
    }
    var caja = armarDialogo();
    caja.querySelector(".dialogo-texto").textContent = boton.getAttribute("data-confirmar");
    caja.querySelector(".dialogo-titulo").textContent = boton.getAttribute("data-confirmar-titulo") || "¿Seguro?";
    var aceptar = caja.querySelector(".dialogo-acciones .boton:not(.secundario)");
    aceptar.textContent = boton.getAttribute("data-confirmar-boton") || "Sí, continuar";
    aceptar.classList.toggle("peligro", boton.classList.contains("peligro"));
    caja.returnValue = "";
    caja.addEventListener("close", function alCerrar() {
      caja.removeEventListener("close", alCerrar);
      if (caja.returnValue === "si") { continuar(); } else { boton.focus(); }
    });
    caja.showModal();
    caja.querySelector(".dialogo-acciones .boton.secundario").focus();
  }

  function prepararConfirmaciones() {
    document.querySelectorAll("[data-confirmar]").forEach(function (boton) {
      boton.addEventListener("click", function (evento) {
        if (boton.dataset.confirmado === "1") { boton.dataset.confirmado = ""; return; }
        evento.preventDefault();
        confirmar(boton, function () {
          if (boton.form && boton.form.requestSubmit && boton.type === "submit") {
            boton.form.requestSubmit(boton);
          } else if (boton.form) {
            boton.dataset.confirmado = "1";
            boton.click();
          } else if (boton.href) {
            window.location.assign(boton.href);
          }
        });
      });
    });
  }

  function prepararMenuMas() {
    document.querySelectorAll("[data-menu-mas]").forEach(function (mas) {
      var resumen = mas.querySelector("summary");
      var enlaces = function () { return Array.prototype.slice.call(mas.querySelectorAll(".menu-mas-panel a")); };
      resumen.setAttribute("aria-haspopup", "true");
      var marcar = function () { resumen.setAttribute("aria-expanded", mas.open ? "true" : "false"); };
      marcar();
      mas.addEventListener("toggle", marcar);
      mas.addEventListener("keydown", function (evento) {
        var lista = enlaces();
        var indice = lista.indexOf(document.activeElement);
        if (evento.key === "Escape" && mas.open) {
          mas.open = false;
          resumen.focus();
          evento.preventDefault();
        } else if (evento.key === "ArrowDown") {
          if (!mas.open) { mas.open = true; }
          (lista[indice + 1] || lista[0]).focus();
          evento.preventDefault();
        } else if (evento.key === "ArrowUp" && mas.open) {
          (lista[indice - 1] || lista[lista.length - 1]).focus();
          evento.preventDefault();
        }
      });
      document.addEventListener("click", function (evento) { if (mas.open && !mas.contains(evento.target)) { mas.open = false; } });
      mas.addEventListener("focusout", function (evento) { if (mas.open && evento.relatedTarget && !mas.contains(evento.relatedTarget)) { mas.open = false; } });
    });
  }

  function prepararAvisosBreves() {
    document.querySelectorAll("[data-aviso-breve]").forEach(function (aviso) {
      var cerrar = crear("button", "", "×");
      cerrar.type = "button";
      cerrar.setAttribute("aria-label", "Cerrar aviso");
      aviso.appendChild(cerrar);
      var quitar = function () {
        aviso.classList.add("saliendo");
        window.setTimeout(function () { aviso.hidden = true; }, 250);
      };
      cerrar.addEventListener("click", quitar);
      window.setTimeout(quitar, 6000);
    });
  }

  function prepararSplash() {
    var splash = document.querySelector("[data-splash]");
    if (!splash) { return; }
    var listo = false;
    var quitar = function () {
      if (listo) { return; }
      listo = true;
      splash.classList.add("saliendo");
      window.setTimeout(function () { splash.hidden = true; }, 420);
      document.removeEventListener("keydown", quitar, true);
      var primero = document.querySelector("main input:not([type=hidden])");
      if (primero) { primero.focus(); }
    };
    splash.addEventListener("click", quitar);
    document.addEventListener("keydown", quitar, true);
    splash.addEventListener("animationend", function () { if (!listo) { listo = true; splash.hidden = true; document.removeEventListener("keydown", quitar, true); } });
  }

  function prepararImprimir() {
    var imprimir = document.getElementById("imprimir");
    if (imprimir) { imprimir.addEventListener("click", function () { window.print(); }); }
  }

  document.addEventListener("DOMContentLoaded", function () {
    prepararImprimir();
    prepararConfirmaciones();
    prepararMenuMas();
    prepararAvisosBreves();
    prepararSplash();
  });
}());
