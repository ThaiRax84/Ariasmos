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

  function formatear(centavos, simbolo) {
    var signo = centavos < 0 ? "-" : "";
    var absoluto = Math.abs(centavos);
    var enteros = Math.floor(absoluto / 100).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
    var resto = ("0" + (absoluto % 100)).slice(-2);
    return signo + simbolo + enteros + "." + resto;
  }

  function prepararConteos() {
    document.querySelectorAll("[data-conteo]").forEach(function (tabla) {
      var simbolo = tabla.getAttribute("data-simbolo") || "$";
      var contenedor = tabla.closest("form") || document;
      var total = contenedor.querySelector("[data-contado]");
      var calcular = function () {
        var suma = 0;
        tabla.querySelectorAll("tr[data-centavos]").forEach(function (fila) {
          var campo = fila.querySelector("input");
          var piezas = parseInt(campo && campo.value, 10);
          var valor = parseInt(fila.getAttribute("data-centavos"), 10);
          var subtotal = isNaN(piezas) || isNaN(valor) ? 0 : piezas * valor;
          suma += subtotal;
          var celda = fila.querySelector("[data-subtotal]");
          if (celda) { celda.textContent = formatear(subtotal, simbolo); }
        });
        if (total) { total.textContent = formatear(suma, simbolo); }
      };
      tabla.addEventListener("input", calcular);
      calcular();
    });
  }

  function prepararImprimir() {
    var imprimir = document.getElementById("imprimir");
    if (imprimir) { imprimir.addEventListener("click", function () { window.print(); }); }
  }

  function prepararColores() {
    var patron = /^#[0-9A-Fa-f]{6}$/;
    Array.prototype.forEach.call(document.querySelectorAll('input[data-acepta="color"]'), function (campo) {
      var selector = document.createElement("input");
      selector.type = "color";
      selector.className = "selector-color";
      selector.setAttribute("aria-label", "Elegir el color");
      selector.value = patron.test(campo.value) ? campo.value : "#888888";
      selector.addEventListener("input", function () {
        campo.value = selector.value.toUpperCase();
        campo.dispatchEvent(new Event("input", { bubbles: true }));
      });
      campo.addEventListener("input", function () {
        if (patron.test(campo.value)) { selector.value = campo.value; }
      });
      campo.insertAdjacentElement("afterend", selector);
    });
  }

  function valorDeControl(raiz, nombre) {
    var controles = Array.prototype.slice.call(raiz.querySelectorAll('[name="' + nombre + '"]'));
    var valores = [];
    controles.forEach(function (control) {
      if (control.disabled) { return; }
      if (control.type === "checkbox" || control.type === "radio") {
        if (control.type === "checkbox" && controles.length === 1) { valores.push(control.checked ? "on" : ""); return; }
        if (control.checked) { valores.push(control.value); }
      } else if (control.tagName === "SELECT" && control.multiple) {
        Array.prototype.forEach.call(control.selectedOptions, function (opcion) { valores.push(opcion.value); });
      } else if (control.type !== "hidden" || controles.length === 1) {
        valores.push(control.value);
      }
    });
    return valores.length ? valores : [""];
  }

  function leerMapa(elemento, atributo) {
    var texto = elemento.getAttribute(atributo);
    if (!texto) { return null; }
    try { return JSON.parse(texto); } catch (error) { return null; }
  }

  function prepararDependencias() {
    var raices = [];
    document.querySelectorAll("[data-depende-de]").forEach(function (elemento) {
      var raiz = elemento.closest("form") || document;
      if (raices.indexOf(raiz) === -1) { raices.push(raiz); }
    });
    raices.forEach(function (raiz) {
      var dependientes = Array.prototype.slice.call(raiz.querySelectorAll("[data-depende-de]"));
      var etiquetaOriginal = new Map();
      dependientes.forEach(function (elemento) {
        elemento.querySelectorAll("[data-nota-dependencia]").forEach(function (nota) { nota.hidden = true; });
        var etiqueta = elemento.querySelector("label, .etiqueta");
        if (etiqueta) { etiquetaOriginal.set(elemento, etiqueta.textContent); }
      });

      function pintarUno(elemento) {
        var valores = valorDeControl(raiz, elemento.getAttribute("data-depende-de"));
        var mostrarSi = elemento.getAttribute("data-mostrar-si");
        var ocultarSi = elemento.getAttribute("data-ocultar-si");
        var mostrar = true;
        if (mostrarSi !== null) {
          var lista = mostrarSi.split(" ");
          mostrar = valores.some(function (valor) { return lista.indexOf(valor) !== -1; });
        } else if (ocultarSi !== null) {
          var excluidos = ocultarSi.split(" ");
          mostrar = !valores.some(function (valor) { return excluidos.indexOf(valor) !== -1; });
        }
        var cambio = elemento.hidden === mostrar;
        elemento.hidden = !mostrar;
        elemento.querySelectorAll("input, select, textarea").forEach(function (campo) { campo.disabled = !mostrar; });
        var etiquetas = leerMapa(elemento, "data-etiquetas");
        var etiqueta = elemento.querySelector("label, .etiqueta");
        if (etiquetas && etiqueta) {
          var nueva = null;
          valores.forEach(function (valor) { if (nueva === null && Object.prototype.hasOwnProperty.call(etiquetas, valor)) { nueva = etiquetas[valor]; } });
          etiqueta.textContent = nueva !== null ? nueva : etiquetaOriginal.get(elemento);
        }
        var maximos = leerMapa(elemento, "data-maximos");
        if (maximos) {
          var maximo = null;
          valores.forEach(function (valor) { if (maximo === null && Object.prototype.hasOwnProperty.call(maximos, valor)) { maximo = maximos[valor]; } });
          elemento.querySelectorAll("input").forEach(function (campo) {
            if (maximo !== null) { campo.setAttribute("max", String(maximo)); } else { campo.removeAttribute("max"); }
          });
        }
        return cambio;
      }

      function pintar() {
        for (var vuelta = 0; vuelta < 5; vuelta += 1) {
          var hubo = false;
          dependientes.forEach(function (elemento) { if (pintarUno(elemento)) { hubo = true; } });
          if (!hubo) { break; }
        }
      }

      raiz.addEventListener("change", pintar);
      raiz.addEventListener("input", function (evento) { if (evento.target && evento.target.tagName === "SELECT") { pintar(); } });
      window.addEventListener("pageshow", pintar);
      pintar();
    });
  }

  var LIBERAR_MS = 15000;

  function marcarTrabajando(elemento) {
    elemento.classList.add("trabajando");
    elemento.setAttribute("aria-busy", "true");
    elemento.setAttribute("aria-disabled", "true");
  }

  function liberar(elemento) {
    elemento.classList.remove("trabajando");
    elemento.removeAttribute("aria-busy");
    elemento.removeAttribute("aria-disabled");
  }

  function liberarTodo() {
    document.querySelectorAll("form[data-enviando]").forEach(function (formulario) { delete formulario.dataset.enviando; });
    document.querySelectorAll(".trabajando").forEach(liberar);
  }

  function prepararEnvioUnico() {
    document.addEventListener("submit", function (evento) {
      var formulario = evento.target;
      if (!(formulario instanceof HTMLFormElement)) { return; }
      if (formulario.dataset.enviando === "1") { evento.preventDefault(); return; }
      if (evento.defaultPrevented) { return; }
      formulario.dataset.enviando = "1";
      var boton = evento.submitter || formulario.querySelector("button[type=submit], button:not([type]), input[type=submit]");
      formulario.querySelectorAll("button[type=submit], button:not([type]), input[type=submit]").forEach(function (otro) { otro.setAttribute("aria-disabled", "true"); });
      if (boton) { marcarTrabajando(boton); }
      window.setTimeout(function () {
        delete formulario.dataset.enviando;
        formulario.querySelectorAll("[aria-disabled]").forEach(liberar);
      }, LIBERAR_MS);
    });
    document.addEventListener("click", function (evento) {
      var boton = evento.target.closest && evento.target.closest("button, input[type=submit]");
      if (boton && boton.form && boton.form.dataset.enviando === "1" && boton.type === "submit") { evento.preventDefault(); return; }
      var enlace = evento.target.closest && evento.target.closest("a.boton[href]");
      if (!enlace || evento.defaultPrevented || evento.button !== 0 || evento.ctrlKey || evento.metaKey || evento.shiftKey || evento.altKey || enlace.target) { return; }
      if (enlace.classList.contains("trabajando")) { evento.preventDefault(); return; }
      marcarTrabajando(enlace);
      window.setTimeout(function () { liberar(enlace); }, LIBERAR_MS);
    });
    window.addEventListener("pageshow", liberarTodo);
  }

  function prepararFiltrosVivos() {
    document.querySelectorAll("form[data-filtro-vivo]").forEach(function (formulario) {
      var region = document.getElementById(formulario.getAttribute("data-filtro-vivo"));
      var campo = formulario.querySelector('input[type="search"]');
      if (!region || !campo || !window.fetch || !window.DOMParser) { return; }
      var espera = null;
      var vigente = 0;
      function pedir() {
        var datos = new URLSearchParams(new FormData(formulario));
        var direccion = formulario.getAttribute("action") || window.location.pathname;
        var numero = vigente + 1;
        vigente = numero;
        region.classList.add("cargando");
        window.fetch(direccion + "?" + datos.toString(), { credentials: "same-origin", headers: { "X-Requested-With": "fetch" } })
          .then(function (respuesta) { return respuesta.ok ? respuesta.text() : null; })
          .then(function (texto) {
            if (numero !== vigente || texto === null) { return; }
            var nueva = new DOMParser().parseFromString(texto, "text/html").getElementById(region.id);
            if (!nueva) { return; }
            region.replaceChildren.apply(region, Array.prototype.slice.call(nueva.childNodes).map(function (nodo) { return document.importNode(nodo, true); }));
            if (window.history && window.history.replaceState) { window.history.replaceState(null, "", direccion + "?" + datos.toString()); }
            document.querySelectorAll("form.orden-formulario").forEach(function (orden) {
              var oculto = orden.querySelector('input[name="q"]');
              if (!oculto) {
                oculto = document.createElement("input");
                oculto.type = "hidden";
                oculto.name = "q";
                orden.insertBefore(oculto, orden.firstChild);
              }
              oculto.value = campo.value;
            });
          })
          .catch(function () { return null; })
          .then(function () { if (numero === vigente) { region.classList.remove("cargando"); } });
      }
      campo.addEventListener("input", function () {
        window.clearTimeout(espera);
        espera = window.setTimeout(pedir, 250);
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    prepararEnvioUnico();
    prepararFiltrosVivos();
    prepararDependencias();
    prepararImprimir();
    prepararConfirmaciones();
    prepararMenuMas();
    prepararAvisosBreves();
    prepararConteos();
    prepararColores();
  });
}());
