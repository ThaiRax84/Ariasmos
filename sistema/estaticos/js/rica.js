(function () {
  "use strict";

  var A = window.Ariasmos = window.Ariasmos || {};
  A.alIniciar = A.alIniciar || [];
  var raiz = document.documentElement;
  raiz.classList.add("con-js");
  var CURVA = "cubic-bezier(.2,.7,.2,1)";

  function $(selector, base) { return (base || document).querySelector(selector); }
  function $$(selector, base) { return Array.prototype.slice.call((base || document).querySelectorAll(selector)); }
  function crear(etiqueta, clase, texto) {
    var elemento = document.createElement(etiqueta);
    if (clase) { elemento.className = clase; }
    if (texto !== undefined && texto !== null) { elemento.textContent = texto; }
    return elemento;
  }
  function quieto() { return !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches); }
  function llano(texto) { return String(texto || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase(); }
  function simbolo() { return (document.body && document.body.getAttribute("data-simbolo")) || "$"; }
  function dinero(centavos) {
    var signo = centavos < 0 ? "-" : "";
    var absoluto = Math.abs(Math.round(centavos));
    var enteros = Math.floor(absoluto / 100).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
    return signo + simbolo() + enteros + "." + ("0" + (absoluto % 100)).slice(-2);
  }
  function aCentavos(texto) {
    var limpio = String(texto || "").replace(/[^0-9.]/g, "");
    if (!limpio || !/^[0-9]*(\.[0-9]{0,2})?$/.test(limpio)) { return null; }
    var partes = limpio.split(".");
    return parseInt(partes[0] || "0", 10) * 100 + parseInt(((partes[1] || "") + "00").slice(0, 2), 10);
  }
  function plano(centavos) { return Math.floor(centavos / 100) + "." + ("0" + (centavos % 100)).slice(-2); }
  function reiniciar(elemento, clase) {
    if (!elemento) { return; }
    elemento.classList.remove(clase);
    void elemento.offsetWidth;
    elemento.classList.add(clase);
  }
  function enriquecer(nodo) { nodo.dispatchEvent(new CustomEvent("ariasmos:contenido", { bubbles: true })); }
  function importar(nodos) { return Array.prototype.slice.call(nodos).map(function (nodo) { return document.importNode(nodo, true); }); }
  function mostrarConJs(base) {
    $$(".solo-con-js", base).forEach(function (e) { e.hidden = false; });
    $$("[data-solo-sin-js]", base).forEach(function (e) { e.hidden = true; });
  }

  function animarCifra(elemento, hasta, formato) {
    formato = formato || dinero;
    var desde = Number(elemento.getAttribute("data-valor") || 0);
    elemento.setAttribute("data-valor", String(hasta));
    if (quieto() || desde === hasta) { elemento.textContent = formato(hasta); return; }
    var inicio = performance.now();
    var duracion = 480;
    function paso(ahora) {
      if (Number(elemento.getAttribute("data-valor")) !== hasta) { return; }
      var avance = Math.min(1, (ahora - inicio) / duracion);
      var suave = 1 - Math.pow(1 - avance, 3);
      elemento.textContent = formato(avance < 1 ? Math.round(desde + (hasta - desde) * suave) : hasta);
      if (avance < 1) { requestAnimationFrame(paso); }
    }
    requestAnimationFrame(paso);
  }

  function mover(contenedor, selector, cambio) {
    var antes = new Map($$(selector, contenedor).map(function (e) { return [e.getAttribute("data-id"), e.getBoundingClientRect().top]; }));
    cambio();
    if (quieto()) { return; }
    $$(selector, contenedor).forEach(function (e) {
      var arriba = antes.get(e.getAttribute("data-id"));
      if (arriba === undefined) {
        e.animate([{ opacity: 0, transform: "translateY(8px)" }, { opacity: 1, transform: "none" }], { duration: 260, easing: "ease-out" });
        return;
      }
      var distancia = arriba - e.getBoundingClientRect().top;
      if (distancia) { e.animate([{ transform: "translateY(" + distancia + "px)" }, { transform: "none" }], { duration: 340, easing: CURVA }); }
    });
  }

  function cajaAvisos() {
    var caja = $("#avisos-vivos");
    if (!caja) {
      caja = crear("ul", "avisos-breves");
      caja.id = "avisos-vivos";
      caja.setAttribute("role", "status");
      document.body.appendChild(caja);
    }
    return caja;
  }

  function aviso(texto, opciones) {
    opciones = opciones || {};
    var caja = cajaAvisos();
    var ms = opciones.ms || 5200;
    while (caja.children.length >= 3) { caja.firstElementChild.remove(); }
    var renglon = crear("li", "aviso-breve");
    if (opciones.vivo) { renglon.appendChild(crear("span", "icono-vivo")); }
    renglon.appendChild(crear("span", "", texto));
    var accion = null;
    if (opciones.accion) {
      accion = crear("button", "accion-aviso", opciones.accion);
      accion.type = "button";
      renglon.appendChild(accion);
    }
    var cerrar = crear("button", "cierra-aviso", "×");
    cerrar.type = "button";
    cerrar.setAttribute("aria-label", "Cerrar aviso");
    renglon.appendChild(cerrar);
    var tiempo = crear("span", "tiempo");
    tiempo.style.animationDuration = ms + "ms";
    renglon.appendChild(tiempo);
    var listo = false;
    function fuera(motivo) {
      if (listo) { return; }
      listo = true;
      window.clearTimeout(reloj);
      renglon.classList.add("saliendo");
      window.setTimeout(function () { renglon.remove(); }, 220);
      if (opciones.alTerminar) { opciones.alTerminar(motivo); }
    }
    var reloj = window.setTimeout(function () { fuera("tiempo"); }, ms);
    cerrar.addEventListener("click", function () { fuera("cerrar"); });
    if (accion) {
      accion.addEventListener("click", function () {
        if (listo) { return; }
        if (opciones.alAccionar) { opciones.alAccionar(); }
        fuera("accion");
      });
    }
    caja.appendChild(renglon);
    return { cerrar: fuera, nodo: renglon };
  }

  function avisosDelServidor() {
    $$("[data-aviso-breve]").forEach(function (renglon) {
      if ($(".tiempo", renglon)) { return; }
      var tiempo = crear("span", "tiempo");
      tiempo.style.animationDuration = "6000ms";
      renglon.appendChild(tiempo);
    });
  }

  function resaltar(base, texto) {
    var buscado = llano((texto || "").trim());
    $$("[data-resaltar]", base).forEach(function (elemento) {
      var original = elemento.getAttribute("data-original");
      if (original === null) {
        original = elemento.textContent;
        elemento.setAttribute("data-original", original);
      }
      var indice = buscado ? llano(original).indexOf(buscado) : -1;
      if (indice < 0) { elemento.textContent = original; return; }
      var marca = crear("mark", "", original.slice(indice, indice + buscado.length));
      elemento.replaceChildren(document.createTextNode(original.slice(0, indice)), marca, document.createTextNode(original.slice(indice + buscado.length)));
    });
  }

  function destellar(elemento, clase) { reiniciar(elemento, clase || "destello"); }

  function sustituir(region, nueva, opciones) {
    opciones = opciones || {};
    var previos = new Map($$("[data-id]", region).map(function (e) { return [e.getAttribute("data-id"), e.textContent]; }));
    var hayPrevios = previos.size > 0;
    mover(region, "[data-id]", function () {
      region.replaceChildren.apply(region, importar(nueva.childNodes));
    });
    mostrarConJs(region);
    var filtro = opciones.filtro !== undefined ? opciones.filtro : valorFiltro();
    resaltar(region, filtro);
    if (opciones.destello && hayPrevios) {
      $$("[data-id]", region).forEach(function (e) {
        var antes = previos.get(e.getAttribute("data-id"));
        if (antes !== undefined && antes !== e.textContent) { destellar(e); }
      });
    }
    enriquecer(region);
    if (opciones.filtro !== undefined) { cobro.activo = filtro.trim() ? 0 : -1; }
    marcarLista();
  }

  function valorFiltro() {
    var campo = $("[data-filtro-lista]");
    return campo ? campo.value : "";
  }

  var cobro = { activo: -1, abierto: null, url: null, cargando: 0 };

  function rejilla() { return $("[data-cobro-rejilla]"); }
  function cajaPanel() { return $("#panel-cobro > .panel"); }
  function renglones() { var r = rejilla(); return r ? $$(".lista-titulares .renglon-titular", r) : []; }

  function marcarLista() {
    renglones().forEach(function (renglon, indice) {
      renglon.classList.toggle("activo", indice === cobro.activo);
      renglon.classList.toggle("elegido", cobro.abierto !== null && renglon.getAttribute("data-id") === cobro.abierto);
    });
  }

  function pedirPanel(direccion, opciones) {
    opciones = opciones || {};
    var numero = ++cobro.cargando;
    return window.fetch(direccion, { method: opciones.metodo || "GET", body: opciones.cuerpo, credentials: "same-origin", headers: { "X-Requested-With": "fetch" } })
      .then(function (respuesta) {
        return respuesta.text().then(function (texto) { return { respuesta: respuesta, texto: texto }; });
      })
      .then(function (resultado) {
        if (numero !== cobro.cargando) { return; }
        if (!resultado.respuesta.ok) {
          aviso("No se pudo abrir. Vuelve a intentarlo.");
          liberarPanel();
          return;
        }
        ponerPanel(resultado.texto, resultado.respuesta.url, opciones);
      })
      .catch(function () {
        aviso("No hubo respuesta del programa. Revisa la conexión y vuelve a intentarlo.");
        liberarPanel();
      });
  }

  function liberarPanel() {
    $$("form[data-panel-enviando]").forEach(function (formulario) {
      delete formulario.dataset.panelEnviando;
      delete formulario.dataset.enviando;
      $$(".trabajando", formulario).forEach(function (b) { b.classList.remove("trabajando"); b.removeAttribute("aria-busy"); b.removeAttribute("aria-disabled"); });
    });
  }

  function ponerPanel(texto, direccionFinal, opciones) {
    var documento = new DOMParser().parseFromString(texto, "text/html");
    var region = documento.getElementById("panel-cobro-region");
    var caja = cajaPanel();
    if (!region || !caja) { window.location.assign(direccionFinal); return; }
    var previo = $("[data-metodos] [aria-pressed='true']", caja);
    var conservar = opciones && opciones.conservarMetodo && previo ? previo.getAttribute("data-metodo") : null;
    caja.replaceChildren.apply(caja, importar(region.childNodes));
    cobro.abierto = region.getAttribute("data-titular");
    mostrarConJs(caja);
    $$("[data-accion='cerrar-panel'], [data-accion='siguiente'], [data-metodos]", caja).forEach(function (e) { e.hidden = false; });
    enriquecer(caja);
    prepararPanel(caja, conservar);
    var malla = rejilla();
    if (malla) { malla.classList.add("abierta"); }
    marcarLista();
    var exito = $("[data-exito]", caja);
    if (exito) {
      var primero = $(".boton", exito);
      if (primero) { primero.focus({ preventScroll: true }); }
      if (A.alCobrar) { A.alCobrar(); }
    } else if (opciones && opciones.enfocar) {
      var importe = $("[data-importe-cobro]", caja);
      (importe || caja).focus({ preventScroll: true });
    }
  }

  function abrirPanel(renglon) {
    var caja = cajaPanel();
    if (caja && (!A.panelAbierto() || cobro.abierto !== renglon.getAttribute("data-id"))) { caja.replaceChildren(); }
    cobro.abierto = renglon.getAttribute("data-id");
    cobro.activo = renglones().indexOf(renglon);
    marcarLista();
    pedirPanel(renglon.getAttribute("data-abre-panel"), { enfocar: true });
  }

  function cerrarPanel() {
    var malla = rejilla();
    if (!malla || !malla.classList.contains("abierta")) { return false; }
    malla.classList.remove("abierta");
    cobro.abierto = null;
    cobro.cargando += 1;
    marcarLista();
    if (A.alCerrarPanel) { A.alCerrarPanel(); }
    return true;
  }
  A.panelAbierto = function () { var malla = rejilla(); return !!(malla && malla.classList.contains("abierta")); };

  function moverPastilla(grupo) {
    var boton = $("[aria-pressed='true']", grupo);
    var pastilla = $(".pastilla", grupo);
    if (!boton || !pastilla) { return; }
    pastilla.style.width = boton.offsetWidth + "px";
    pastilla.style.transform = "translateX(" + boton.offsetLeft + "px)";
  }

  function elegirMetodo(caja, metodo) {
    var grupo = $("[data-metodos]", caja);
    if (!grupo) { return; }
    $$("button[data-metodo]", grupo).forEach(function (b) { b.setAttribute("aria-pressed", b.getAttribute("data-metodo") === metodo ? "true" : "false"); });
    $$("[data-metodo-cuerpo]", caja).forEach(function (cuerpo) { cuerpo.hidden = cuerpo.getAttribute("data-metodo-cuerpo") !== metodo; });
    moverPastilla(grupo);
  }

  function totalCargos(caja) {
    return $$("[data-cargo-centavos]", caja).reduce(function (suma, casilla) { return suma + (casilla.checked ? parseInt(casilla.getAttribute("data-cargo-centavos"), 10) || 0 : 0); }, 0);
  }

  function recibidoEn(formulario) {
    return $$(".pieza[data-centavos] input[name^='r_']", formulario).reduce(function (suma, campo) {
      var piezas = /^[0-9]{1,6}$/.test((campo.value || "").trim()) ? parseInt(campo.value, 10) : 0;
      return suma + piezas * (parseInt(campo.closest(".pieza").getAttribute("data-centavos"), 10) || 0);
    }, 0);
  }

  function actualizarEfectivo(formulario) {
    var cuadros = $("[data-cuadros-cobro]", formulario);
    var campo = $("[data-importe-cobro]", formulario);
    var boton = $("[data-boton-cobro]", formulario);
    if (!campo || !boton) { return; }
    var total = aCentavos(campo.value) || 0;
    if (!cuadros) {
      boton.textContent = boton.getAttribute("data-texto-exacto");
      return;
    }
    var recibido = recibidoEn(formulario);
    var diferencia = recibido - total;
    var rotulo = $("[data-rotulo-falta]", cuadros);
    var cuadro = $("[data-cuadro-falta]", cuadros);
    var recibidoValor = $("[data-recibido-cobro]", cuadros);
    if (recibidoValor) { animarCifra(recibidoValor, recibido); }
    cuadro.classList.toggle("aviso", total > 0 && diferencia > 0);
    cuadro.classList.toggle("bien", total > 0 && diferencia === 0);
    rotulo.textContent = !total ? rotulo.getAttribute("data-sin-importe") : diferencia < 0 ? rotulo.getAttribute("data-falta") : diferencia === 0 ? rotulo.getAttribute("data-exacto") : rotulo.getAttribute("data-cambio");
    animarCifra($("[data-falta-valor]", cuadros), Math.abs(diferencia));
    boton.textContent = diferencia > 0 ? boton.getAttribute("data-texto-cambio") : boton.getAttribute("data-texto-exacto");
    boton.setAttribute("aria-disabled", total > 0 && diferencia >= 0 ? "false" : "true");
    boton.classList.toggle("en-espera", !(total > 0 && diferencia >= 0));
    var ayuda = $("[data-aviso-cambio]", formulario);
    if (ayuda) { ayuda.hidden = !(total > 0 && diferencia > 0); }
  }

  function prepararPanel(caja, metodo) {
    var grupo = $("[data-metodos]", caja);
    if (grupo) {
      elegirMetodo(caja, metodo || "efectivo");
      requestAnimationFrame(function () { moverPastilla(grupo); });
    }
    var formulario = $("[data-cobro-efectivo]", caja);
    if (formulario) { actualizarEfectivo(formulario); }
  }

  function ajustarCargos(casilla) {
    var caja = casilla.closest(".panel");
    var todas = $$("[data-cargo-centavos]", caja);
    var indice = todas.indexOf(casilla);
    todas.forEach(function (otra, i) {
      if (casilla.checked && i < indice) { otra.checked = true; }
      if (!casilla.checked && i > indice) { otra.checked = false; }
    });
    var campo = $("[data-importe-cobro]", caja);
    var total = totalCargos(caja);
    if (campo) {
      campo.value = total ? plano(total) : "";
      var formulario = campo.closest("form");
      if (formulario) { actualizarEfectivo(formulario); }
    }
  }

  function enviarPanel(evento) {
    var formulario = evento.target;
    if (!(formulario instanceof HTMLFormElement) || !formulario.matches("[data-panel-formulario]") || !cajaPanel() || !cajaPanel().contains(formulario)) { return; }
    evento.preventDefault();
    if (formulario.dataset.panelEnviando === "1") { return; }
    var boton = $("[data-boton-cobro]", formulario);
    if (boton && boton.getAttribute("aria-disabled") === "true") {
      reiniciar($("[data-cuadro-falta]", formulario), "cambia");
      return;
    }
    formulario.dataset.panelEnviando = "1";
    var pulsado = evento.submitter || boton;
    if (pulsado) { pulsado.classList.add("trabajando"); pulsado.setAttribute("aria-busy", "true"); }
    var datos = evento.submitter ? new FormData(formulario, evento.submitter) : new FormData(formulario);
    pedirPanel(formulario.getAttribute("action") || window.location.pathname, { metodo: "POST", cuerpo: datos });
  }

  function siguienteCobro() {
    cerrarPanel();
    var campo = $("[data-filtro-lista]");
    if (campo) {
      if (campo.value) {
        campo.value = "";
        campo.dispatchEvent(new Event("input", { bubbles: true }));
      }
      campo.focus();
    }
  }

  function copiar(boton) {
    var texto = boton.getAttribute("data-copiar") || "";
    var bien = function () { aviso(boton.getAttribute("data-copiado") || ""); };
    var mal = function () { aviso(boton.getAttribute("data-no-copiado") || ""); };
    if (navigator.clipboard && navigator.clipboard.writeText) { navigator.clipboard.writeText(texto).then(bien, mal); } else { mal(); }
  }

  function alternarComo(boton) {
    var pliegue = document.getElementById(boton.getAttribute("data-como"));
    if (!pliegue) { return; }
    var abierto = pliegue.classList.toggle("visible");
    boton.setAttribute("aria-expanded", abierto ? "true" : "false");
  }

  function tecladoLista(evento) {
    var campo = evento.target;
    var enFiltro = campo && campo.matches && campo.matches("[data-filtro-lista]");
    var enCampo = campo && campo.matches && campo.matches("input, textarea, select");
    var dentroPanel = cajaPanel() && cajaPanel().contains(campo);
    var lista = renglones();
    if (!rejilla()) { return; }
    if ((enFiltro || (!enCampo && !dentroPanel)) && (evento.key === "ArrowDown" || evento.key === "ArrowUp") && lista.length) {
      evento.preventDefault();
      cobro.activo = Math.max(0, Math.min(lista.length - 1, cobro.activo + (evento.key === "ArrowDown" ? 1 : -1)));
      marcarLista();
      lista[cobro.activo].scrollIntoView({ block: "nearest" });
      return;
    }
    if (enFiltro && evento.key === "Enter") {
      evento.preventDefault();
      var elegido = lista[Math.max(0, cobro.activo)];
      if (elegido && elegido.hasAttribute("data-abre-panel")) { abrirPanel(elegido); } else if (elegido) { window.location.assign(elegido.href); }
      return;
    }
    if (evento.key === "Escape" && !$("dialog[open]")) {
      if (cerrarPanel()) {
        evento.preventDefault();
        var filtro = $("[data-filtro-lista]");
        if (filtro) { filtro.focus({ preventScroll: true }); }
      } else if (enFiltro && campo.value) {
        evento.preventDefault();
        campo.value = "";
        cobro.activo = -1;
        campo.dispatchEvent(new Event("input", { bubbles: true }));
      }
    }
  }

  document.addEventListener("click", function (evento) {
    if (evento.defaultPrevented || evento.button !== 0) { return; }
    var objetivo = evento.target;
    var renglon = objetivo.closest && objetivo.closest("[data-abre-panel]");
    if (renglon && !(evento.ctrlKey || evento.metaKey || evento.shiftKey || evento.altKey) && window.fetch && window.DOMParser) {
      evento.preventDefault();
      abrirPanel(renglon);
      return;
    }
    var recargar = objetivo.closest && objetivo.closest("[data-recargar-panel]");
    if (recargar && cajaPanel() && cajaPanel().contains(recargar)) {
      evento.preventDefault();
      pedirPanel(recargar.href, { enfocar: true });
      return;
    }
    var accion = objetivo.closest && objetivo.closest("[data-accion]");
    if (accion) {
      var nombre = accion.getAttribute("data-accion");
      if (nombre === "cerrar-panel") { cerrarPanel(); var filtro = $("[data-filtro-lista]"); if (filtro) { filtro.focus({ preventScroll: true }); } return; }
      if (nombre === "siguiente") { siguienteCobro(); return; }
    }
    var metodo = objetivo.closest && objetivo.closest("[data-metodos] button[data-metodo]");
    if (metodo) { elegirMetodo(metodo.closest(".panel"), metodo.getAttribute("data-metodo")); if (A.alElegirMetodo) { A.alElegirMetodo(metodo.getAttribute("data-metodo")); } return; }
    var copia = objetivo.closest && objetivo.closest("[data-copiar]");
    if (copia) { copiar(copia); return; }
    var como = objetivo.closest && objetivo.closest("[data-como]");
    if (como) { alternarComo(como); }
  });

  document.addEventListener("change", function (evento) {
    if (evento.target.matches && evento.target.matches("[data-cargo-centavos]")) { ajustarCargos(evento.target); }
  });
  document.addEventListener("input", function (evento) {
    var campo = evento.target;
    if (campo.matches && campo.matches("[data-importe-cobro]")) { actualizarEfectivo(campo.closest("form")); }
    if (campo.matches && campo.matches("[data-filtro-lista]")) { resaltar(rejilla() || document, campo.value); }
  });
  document.addEventListener("piezas-cambio", function (evento) {
    if (evento.target.matches && evento.target.matches("[data-cobro-efectivo]")) { actualizarEfectivo(evento.target); }
  });
  document.addEventListener("keydown", tecladoLista);
  window.addEventListener("resize", function () { $$("[data-metodos]").forEach(moverPastilla); });

  A.$ = $;
  A.$$ = $$;
  A.crear = crear;
  A.quieto = quieto;
  A.dinero = dinero;
  A.aviso = aviso;
  A.animarCifra = animarCifra;
  A.mover = mover;
  A.reiniciar = reiniciar;
  A.destellar = destellar;
  A.enriquecer = enriquecer;
  A.importar = importar;
  A.sustituir = sustituir;
  A.mostrarConJs = mostrarConJs;
  A.pedirPanel = pedirPanel;
  A.cerrarPanel = cerrarPanel;
  A.cobro = cobro;

  document.addEventListener("submit", enviarPanel);
  document.addEventListener("DOMContentLoaded", function () {
    mostrarConJs(document);
    avisosDelServidor();
    var campo = $("[data-filtro-lista]");
    if (campo) { resaltar(rejilla() || document, campo.value); }
    marcarLista();
    A.alIniciar.forEach(function (f) { f(); });
  });
}());

(function () {
  "use strict";

  var A = window.Ariasmos;
  var $ = A.$;
  var $$ = A.$$;
  var crear = A.crear;
  var estado = { items: [], indice: 0, pedido: 0, espera: null };
  var ICONOS = {
    persona: "M12 4a4 4 0 110 8 4 4 0 010-8zM4 20c1.5-4 4.5-5 8-5s6.5 1 8 5",
    accion: "M13 3L5 14h6l-1 7 8-11h-6l1-7z",
    pantalla: "M3 5h18v12H3zM9 21h6"
  };

  function icono(tipo) {
    var espacio = "http://www.w3.org/2000/svg";
    var svg = document.createElementNS(espacio, "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("width", "18");
    svg.setAttribute("height", "18");
    svg.setAttribute("aria-hidden", "true");
    var trazo = document.createElementNS(espacio, "path");
    trazo.setAttribute("d", ICONOS[tipo] || ICONOS.pantalla);
    trazo.setAttribute("fill", "none");
    trazo.setAttribute("stroke", "currentColor");
    trazo.setAttribute("stroke-width", "2");
    trazo.setAttribute("stroke-linejoin", "round");
    trazo.setAttribute("stroke-linecap", "round");
    svg.appendChild(trazo);
    return svg;
  }

  function iniciales(texto) {
    var palabras = String(texto || "").split(/\s+/).filter(function (p) { return /^\p{L}/u.test(p); });
    if (!palabras.length) { return ""; }
    if (palabras.length === 1) { return palabras[0][0].toUpperCase(); }
    var segunda = palabras.length === 2 ? palabras[1] : palabras[palabras.length - 2];
    return (palabras[0][0] + segunda[0]).toUpperCase();
  }

  function conMarca(texto, buscado) {
    var fuerte = crear("strong");
    var plano = String(texto).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
    var b = String(buscado || "").trim().normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
    var i = b ? plano.indexOf(b) : -1;
    if (i < 0) { fuerte.textContent = texto; return fuerte; }
    fuerte.appendChild(document.createTextNode(texto.slice(0, i)));
    fuerte.appendChild(crear("mark", "", texto.slice(i, i + b.length)));
    fuerte.appendChild(document.createTextNode(texto.slice(i + b.length)));
    return fuerte;
  }

  function dialogo() { return $("#paleta"); }
  function disparador() { return $("[data-paleta]"); }

  function pintar(items, buscado) {
    var lista = $("#paleta-lista");
    estado.items = items;
    estado.indice = 0;
    var grupo = "";
    var nodos = [];
    items.forEach(function (item, i) {
      if (item.grupo !== grupo) {
        grupo = item.grupo;
        nodos.push(crear("div", "paleta-grupo", grupo));
      }
      var boton = crear("a", "paleta-item");
      boton.href = item.url;
      boton.id = "paleta-item-" + i;
      boton.setAttribute("role", "option");
      boton.setAttribute("aria-selected", i === 0 ? "true" : "false");
      boton.setAttribute("data-i", String(i));
      boton.tabIndex = -1;
      if (item.tipo === "persona") { boton.appendChild(crear("span", "avatar chico", iniciales(item.titulo))); } else { var caja = crear("span", "icono"); caja.appendChild(icono(item.tipo)); boton.appendChild(caja); }
      var textos = crear("span");
      textos.appendChild(conMarca(item.titulo, buscado));
      if (item.detalle) { textos.appendChild(crear("span", "sub", item.detalle)); }
      boton.appendChild(textos);
      boton.appendChild(crear("span", "lado", item.lado || ""));
      nodos.push(boton);
    });
    lista.replaceChildren.apply(lista, nodos);
    $("#paleta-vacio").hidden = items.length > 0;
    marcar();
  }

  function marcar() {
    $$(".paleta-item").forEach(function (e, i) {
      e.setAttribute("aria-selected", i === estado.indice ? "true" : "false");
      if (i === estado.indice) { e.scrollIntoView({ block: "nearest" }); $("#paleta-texto").setAttribute("aria-activedescendant", e.id); }
    });
  }

  function pedir() {
    var texto = $("#paleta-texto").value;
    var numero = ++estado.pedido;
    var url = disparador().getAttribute("data-paleta") + "?q=" + encodeURIComponent(texto);
    window.fetch(url, { credentials: "same-origin", headers: { "Accept": "application/json", "X-Requested-With": "fetch" } })
      .then(function (r) {
        $("#paleta-espera").hidden = r.status !== 429;
        return r.ok ? r.json() : null;
      })
      .then(function (datos) {
        if (numero !== estado.pedido || !datos) { return; }
        pintar(datos.resultados || [], texto);
      })
      .catch(function () { return null; });
  }

  function abrir() {
    var caja = dialogo();
    if (!caja || !disparador() || caja.open) { return; }
    $("#paleta-texto").value = "";
    $("#paleta-espera").hidden = true;
    pedir();
    caja.showModal();
    $("#paleta-texto").focus();
  }

  function ir(i) {
    var item = estado.items[i];
    if (!item) { return; }
    dialogo().close();
    window.location.assign(item.url);
  }

  document.addEventListener("click", function (evento) {
    var abre = evento.target.closest && evento.target.closest("[data-paleta], [data-accion='paleta']");
    if (abre && dialogo() && !evento.ctrlKey && !evento.metaKey) { evento.preventDefault(); abrir(); return; }
    var item = evento.target.closest && evento.target.closest(".paleta-item");
    if (item) { evento.preventDefault(); ir(Number(item.getAttribute("data-i"))); return; }
    var cerrar = evento.target.closest && evento.target.closest("[data-cerrar-dialogo]");
    if (cerrar) { cerrar.closest("dialog").close(); return; }
    if (evento.target.tagName === "DIALOG" && evento.target.classList.contains("dialogo") && evento.target.id) { evento.target.close(); }
  });

  document.addEventListener("input", function (evento) {
    if (evento.target.id !== "paleta-texto") { return; }
    window.clearTimeout(estado.espera);
    estado.espera = window.setTimeout(pedir, 140);
  });

  document.addEventListener("keydown", function (evento) {
    var objetivo = evento.target;
    var enCampo = objetivo.matches && objetivo.matches("input, textarea, select, [contenteditable]");
    if ((evento.ctrlKey || evento.metaKey) && !evento.altKey && evento.key.toLowerCase() === "k") {
      if (dialogo() && disparador()) { evento.preventDefault(); abrir(); }
      return;
    }
    var abierto = $("dialog[open]");
    if (abierto && abierto.id === "paleta") {
      var n = estado.items.length;
      if (evento.key === "ArrowDown" && n) { evento.preventDefault(); estado.indice = (estado.indice + 1) % n; marcar(); }
      if (evento.key === "ArrowUp" && n) { evento.preventDefault(); estado.indice = (estado.indice - 1 + n) % n; marcar(); }
      if (evento.key === "Enter") { evento.preventDefault(); window.clearTimeout(estado.espera); ir(estado.indice); }
      return;
    }
    if (abierto || enCampo || evento.ctrlKey || evento.metaKey || evento.altKey) { return; }
    if (evento.key === "?" && $("#atajos")) { evento.preventDefault(); $("#atajos").showModal(); return; }
    if (evento.key === "/" && document.body.getAttribute("data-cobrar")) {
      var filtro = $("[data-cobro-rejilla] [data-filtro-lista]");
      evento.preventDefault();
      if (filtro) { filtro.focus(); filtro.select(); } else { window.location.assign(document.body.getAttribute("data-cobrar")); }
    }
  });

  A.alIniciar.push(function () {
    var parametros = new URLSearchParams(window.location.search);
    var abrirId = parametros.get("abrir");
    if (abrirId && /^[0-9]{1,12}$/.test(abrirId)) {
      var renglon = $("[data-cobro-rejilla] .renglon-titular[data-id='" + abrirId + "'][data-abre-panel]");
      if (renglon) { renglon.click(); } else if ($("[data-cobro-rejilla]")) { A.pedirPanel(window.location.pathname + abrirId + "/?panel=1", { enfocar: true }); }
    }
  });
}());
