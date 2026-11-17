(function () {
  "use strict";

  var AGENTE_PRINCIPAL = /\bAriasmos\/\d+\.\d+\.\d+ principal\b/;
  var pendientes = {};
  var contador = 0;

  function puedeIr(direccion) {
    var navegacion = window.navigation;
    if (navegacion && typeof navegacion.canGoBack === "boolean") {
      return direccion < 0 ? navegacion.canGoBack : navegacion.canGoForward;
    }
    return direccion < 0 ? window.history.length > 1 : true;
  }

  function ir(direccion) {
    if (!puedeIr(direccion)) { return; }
    if (direccion < 0) { window.history.back(); } else { window.history.forward(); }
  }

  function irSiNadieMas(direccion) {
    var navegacion = window.navigation;
    if (!navegacion || typeof navegacion.addEventListener !== "function") {
      ir(direccion);
      return;
    }
    var hecho = false;
    var marcar = function () { hecho = true; };
    navegacion.addEventListener("navigate", marcar);
    window.setTimeout(function () {
      navegacion.removeEventListener("navigate", marcar);
      if (!hecho) { ir(direccion); }
    }, 150);
  }

  function prepararNavegacion() {
    var grupo = document.querySelector("[data-navegacion]");
    var atras = document.querySelector("[data-ir-atras]");
    var adelante = document.querySelector("[data-ir-adelante]");
    if (grupo && atras && adelante) {
      var actualizar = function () {
        atras.disabled = !puedeIr(-1);
        adelante.disabled = !puedeIr(1);
      };
      atras.addEventListener("click", function () { ir(-1); });
      adelante.addEventListener("click", function () { ir(1); });
      if (window.navigation && typeof window.navigation.addEventListener === "function") {
        window.navigation.addEventListener("currententrychange", actualizar);
      }
      window.addEventListener("pageshow", actualizar);
      actualizar();
      grupo.hidden = false;
    }
    document.addEventListener("keydown", function (evento) {
      if (evento.altKey && !evento.ctrlKey && !evento.shiftKey && !evento.metaKey && (evento.key === "ArrowLeft" || evento.key === "ArrowRight")) {
        irSiNadieMas(evento.key === "ArrowLeft" ? -1 : 1);
      }
    });
    document.addEventListener("mouseup", function (evento) {
      if (evento.button === 3 || evento.button === 4) {
        irSiNadieMas(evento.button === 3 ? -1 : 1);
      }
    });
  }

  function enPrincipal() {
    return !!(window.chrome && window.chrome.webview && typeof window.chrome.webview.postMessage === "function") && AGENTE_PRINCIPAL.test(navigator.userAgent);
  }

  function pedir(mensaje, alResponder) {
    contador += 1;
    var id = "c" + contador + Math.floor(Math.random() * 2176782336).toString(36);
    mensaje.id = id;
    pendientes[id] = alResponder;
    window.chrome.webview.postMessage(mensaje);
  }

  function recibir(evento) {
    var datos = evento.data;
    if (!datos || typeof datos !== "object" || typeof datos.id !== "string") { return; }
    var responder = pendientes[datos.id];
    if (!responder) { return; }
    delete pendientes[datos.id];
    responder(datos);
  }

  function boton(texto) {
    var elemento = document.createElement("button");
    elemento.type = "button";
    elemento.className = "boton secundario";
    elemento.textContent = texto;
    return elemento;
  }

  function prepararCarpeta(campo, principal) {
    var caja = document.createElement("div");
    caja.className = "carpeta-acciones";
    var nota = document.createElement("small");
    nota.className = "carpeta-nota";
    if (principal) {
      var examinar = boton("Examinar…");
      examinar.addEventListener("click", function () {
        examinar.disabled = true;
        pedir({ tipo: "elegir_carpeta" }, function (respuesta) {
          examinar.disabled = false;
          if (typeof respuesta.ruta === "string" && respuesta.ruta) {
            campo.value = respuesta.ruta;
            campo.dispatchEvent(new Event("input", { bubbles: true }));
            campo.dispatchEvent(new Event("change", { bubbles: true }));
            campo.focus();
          }
        });
      });
      caja.appendChild(examinar);
      if (campo.hasAttribute("data-sin-permiso")) {
        var dar = boton("Dar permiso");
        dar.addEventListener("click", function () {
          var ruta = campo.value.trim();
          if (!ruta) { return; }
          dar.disabled = true;
          pedir({ tipo: "dar_permiso", ruta: ruta }, function () {
            dar.disabled = false;
            nota.textContent = "Si diste el permiso, vuelve a guardar.";
          });
        });
        caja.appendChild(dar);
      }
    } else {
      nota.textContent = "La carpeta es de la computadora principal: se elige con «Examinar…» desde el programa Ariasmos de esa computadora, o se escribe la ruta aquí.";
    }
    caja.appendChild(nota);
    campo.insertAdjacentElement("afterend", caja);
  }

  function prepararCarpetas() {
    var campos = document.querySelectorAll("input[data-carpeta]");
    if (!campos.length) { return; }
    var principal = enPrincipal();
    if (principal) { window.chrome.webview.addEventListener("message", recibir); }
    Array.prototype.forEach.call(campos, function (campo) { prepararCarpeta(campo, principal); });
  }

  document.addEventListener("DOMContentLoaded", function () {
    prepararNavegacion();
    prepararCarpetas();
  });
}());
