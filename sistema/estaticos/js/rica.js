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

  function cuentas(base) {
    var mapa = new Map();
    $$("[data-cuenta], [data-cuenta-entero], [data-cuenta-por]", base).forEach(function (e) {
      var duenio = e.closest("[data-id]");
      if (duenio) { mapa.set(duenio.getAttribute("data-id") + "|" + cuentaTipo(e), Number(e.getAttribute("data-valor") || cuentaValor(e))); }
    });
    return mapa;
  }
  function cuentaTipo(e) { return e.hasAttribute("data-cuenta") ? "d" : e.hasAttribute("data-cuenta-por") ? "p" : "e"; }
  function cuentaValor(e) { return Number(e.getAttribute("data-cuenta") || e.getAttribute("data-cuenta-entero") || e.getAttribute("data-cuenta-por") || 0); }
  function contar(base, previos) {
    $$("[data-cuenta], [data-cuenta-entero], [data-cuenta-por]", base).forEach(function (e) {
      var tipo = cuentaTipo(e);
      var duenio = e.closest("[data-id]");
      var clave = duenio ? duenio.getAttribute("data-id") + "|" + tipo : null;
      var hasta = cuentaValor(e);
      var desde = previos && clave && previos.has(clave) ? previos.get(clave) : 0;
      if (previos && desde === hasta) { e.setAttribute("data-valor", String(hasta)); return; }
      e.setAttribute("data-valor", String(desde));
      var formato = tipo === "d" ? dinero : tipo === "p" ? function (n) { return n + " %"; } : String;
      animarCifra(e, hasta, formato);
      if (previos && duenio) { reiniciar(duenio.closest(".cifra") || duenio, "cambia"); }
    });
    $$("[data-alto-ef]", base).forEach(function (dia) {
      var ef = $(".tramo.ef", dia);
      var tr = $(".tramo.tr", dia);
      requestAnimationFrame(function () { requestAnimationFrame(function () {
        ef.style.height = (Number(dia.getAttribute("data-alto-ef")) / 10) + "%";
        tr.style.height = (Number(dia.getAttribute("data-alto-tr")) / 10) + "%";
      }); });
    });
    $$(".anillo .avance[data-porcentaje]", base).forEach(function (circulo) {
      var largo = 2 * Math.PI * 40;
      var porcentaje = Math.min(100, Math.max(0, Number(circulo.getAttribute("data-porcentaje"))));
      circulo.style.strokeDasharray = String(largo);
      circulo.style.strokeDashoffset = String(largo);
      requestAnimationFrame(function () { requestAnimationFrame(function () { circulo.style.strokeDashoffset = String(largo * (1 - porcentaje / 100)); }); });
    });
  }

  function sustituir(region, nueva, opciones) {
    opciones = opciones || {};
    var numeros = cuentas(region);
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
    contar(region, numeros);
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
  A.panelConFormulario = function () {
    var c = cajaPanel();
    return !!c && $$("[data-panel-formulario]", c).some(function (f) { var cuerpo = f.closest("[data-metodo-cuerpo]"); return !cuerpo || !cuerpo.hidden; });
  };
  A.cajaPanelContiene = function (nodo) { var c = cajaPanel(); return !!(c && c.contains(nodo)); };
  A.alPulso = function (cambiados) {
    var caja = cajaPanel();
    if (!caja || !A.panelAbierto()) { return; }
    var espera = $("[data-espera-transferencia]", caja);
    var cuerpo = espera && espera.closest("[data-metodo-cuerpo]");
    if (!espera || (cuerpo && cuerpo.hidden)) { return; }
    if (cambiados.indexOf("transferencias") === -1 && cambiados.indexOf("cobros") === -1) { return; }
    pedirPanel(espera.getAttribute("data-direccion"), { conservarMetodo: true });
  };
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
    var chip = objetivo.closest && objetivo.closest("[data-lista-viva] a.filtro[data-estado]");
    if (chip && !(evento.ctrlKey || evento.metaKey || evento.shiftKey)) {
      var oculto = $("[data-estado-lista]");
      var buscador = oculto && oculto.form && $("input[type='search']", oculto.form);
      if (oculto && buscador && window.fetch) {
        evento.preventDefault();
        oculto.value = chip.getAttribute("data-estado");
        $$("a.filtro[data-estado]", chip.parentElement).forEach(function (c) { c.setAttribute("aria-pressed", c === chip ? "true" : "false"); });
        buscador.dispatchEvent(new Event("input", { bubbles: true }));
        return;
      }
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
  A.llano = llano;
  A.mostrarConJs = mostrarConJs;
  A.pedirPanel = pedirPanel;
  A.cerrarPanel = cerrarPanel;
  A.cobro = cobro;

  document.addEventListener("submit", enviarPanel);
  document.addEventListener("DOMContentLoaded", function () {
    mostrarConJs(document);
    avisosDelServidor();
    contar(document, null);
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
  function icono(tipo) {
    var span = crear("span", "icono-svg icono-" + (["persona", "accion", "pantalla"].indexOf(tipo) !== -1 ? tipo : "pantalla"));
    span.setAttribute("aria-hidden", "true");
    return span;
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

(function () {
  "use strict";

  var A = window.Ariasmos;
  var $ = A.$;
  var $$ = A.$$;
  var INTERVALO = 5000;
  var vivo = { valores: null, reloj: null, espera: INTERVALO, avisoPendiente: null, nuevos: 0, pidiendo: false };

  function temasDePagina() {
    var temas = {};
    $$("[data-vivo][id]").forEach(function (region) {
      (region.getAttribute("data-vivo") || "").split(/\s+/).forEach(function (t) { if (t) { temas[t] = true; } });
    });
    return temas;
  }

  function regionTocada() {
    if ($("[data-vivo-pausa]")) { return true; }
    if (A.hayEnvioEnEspera && A.hayEnvioEnEspera()) { return true; }
    if (A.panelAbierto && A.panelAbierto() && A.panelConFormulario()) { return true; }
    var activo = document.activeElement;
    if (activo && activo.closest && activo.closest("[data-vivo][id] form") && activo.matches("input, textarea, select")) { return true; }
    return $$("[data-vivo][id] form").some(function (formulario) { return formulario.dataset.tocado === "1"; });
  }

  function avisarCambios() {
    if (vivo.avisoPendiente) { return; }
    vivo.avisoPendiente = A.aviso("Hay cambios", {
      accion: "Actualizar",
      ms: 120000,
      vivo: true,
      alAccionar: function () { actualizarPagina(true); },
      alTerminar: function () { vivo.avisoPendiente = null; }
    });
  }

  function pedirHtml(direccion) {
    return window.fetch(direccion, { credentials: "same-origin", headers: { "X-Requested-With": "fetch", "X-Ariasmos-Vivo": "1" } })
      .then(function (r) {
        if (r.redirected && new URL(r.url).pathname !== new URL(direccion, window.location.href).pathname) { return null; }
        return r.ok ? r.text() : null;
      })
      .then(function (texto) { return texto === null ? null : new DOMParser().parseFromString(texto, "text/html"); });
  }

  function actualizarPagina(forzar) {
    if (!forzar && regionTocada()) { avisarCambios(); return; }
    pedirHtml(window.location.href).then(function (documento) {
      if (!documento) { return; }
      $$("[data-vivo][id]").forEach(function (region) {
        if (A.cajaPanelContiene && A.cajaPanelContiene(region)) { return; }
        var nueva = documento.getElementById(region.id);
        if (nueva) { A.sustituir(region, nueva, { destello: true }); }
      });
      document.dispatchEvent(new CustomEvent("ariasmos:vivo"));
    }).catch(function () { return null; });
  }

  function globo(salta) {
    var g = $("#globo");
    if (!g) { return; }
    g.hidden = !vivo.nuevos;
    g.textContent = String(vivo.nuevos);
    if (salta) {
      A.reiniciar(g, "salta");
      var c = $(".campana");
      if (c) { A.reiniciar(c, "suena"); }
    }
  }

  function pintarCampana() {
    var boton = $("[data-campana]");
    var lista = $("#campana-lista");
    if (!boton || !lista) { return Promise.resolve(null); }
    return pedirHtml(boton.getAttribute("data-campana")).then(function (documento) {
      var region = documento && documento.getElementById("ultimo-region");
      if (!region) { return null; }
      var antes = new Map($$("li[data-id]", lista).map(function (li) { return [li.getAttribute("data-id"), true]; }));
      lista.replaceChildren.apply(lista, A.importar(region.childNodes));
      if (antes.size) { $$("li[data-id]", lista).forEach(function (li) { if (!antes.has(li.getAttribute("data-id"))) { li.classList.add("entra"); } }); }
      return lista;
    });
  }

  function alCambiarCobros(transferencia) {
    vivo.nuevos += 1;
    globo(true);
    var panel = $("#campana-panel");
    var abierto = panel && !panel.hidden;
    if (abierto || transferencia) {
      pintarCampana().then(function (lista) {
        if (!lista || !transferencia) { return; }
        var llegada = $("li[data-medio='banco']", lista);
        if (!llegada) { return; }
        var ver = llegada.getAttribute("data-ver");
        A.aviso(llegada.getAttribute("data-aviso"), ver ? { vivo: true, accion: "Ver", ms: 6500, alAccionar: function () { window.location.assign(ver); } } : { vivo: true, ms: 6500 });
      });
    }
  }

  function comparar(nuevos) {
    var previos = vivo.valores;
    vivo.valores = nuevos;
    if (!previos) { return; }
    var cambiados = Object.keys(nuevos).filter(function (t) { return previos[t] !== nuevos[t]; });
    if (!cambiados.length) { return; }
    var transferencia = cambiados.indexOf("transferencias") !== -1;
    if (cambiados.indexOf("cobros") !== -1 || transferencia) { alCambiarCobros(transferencia); }
    if (A.alPulso) { A.alPulso(cambiados); }
    var temas = temasDePagina();
    if (cambiados.some(function (t) { return temas[t]; })) { actualizarPagina(false); }
  }

  function consultar() {
    var direccion = document.body.getAttribute("data-pulso");
    if (!direccion || document.hidden || vivo.pidiendo) { programar(); return; }
    vivo.pidiendo = true;
    window.fetch(direccion, { credentials: "same-origin", headers: { "Accept": "application/json", "X-Requested-With": "fetch" } })
      .then(function (r) {
        if (r.redirected) { window.location.reload(); return null; }
        if (r.status === 429) { vivo.espera = Math.min(vivo.espera * 2, 60000); return null; }
        vivo.espera = INTERVALO;
        return r.ok ? r.json() : null;
      })
      .then(function (datos) { if (datos && datos.t) { comparar(datos.t); } })
      .catch(function () { vivo.espera = Math.min(vivo.espera * 2, 60000); })
      .then(function () { vivo.pidiendo = false; programar(); });
  }

  function programar() {
    window.clearTimeout(vivo.reloj);
    vivo.reloj = window.setTimeout(consultar, vivo.espera);
  }

  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) { window.clearTimeout(vivo.reloj); consultar(); }
  });

  document.addEventListener("input", function (evento) {
    var formulario = evento.target.closest && evento.target.closest("[data-vivo][id] form");
    if (formulario && !formulario.matches("[data-filtro-vivo]")) { formulario.dataset.tocado = "1"; }
  });

  document.addEventListener("click", function (evento) {
    var boton = evento.target.closest && evento.target.closest("[data-campana]");
    var panel = $("#campana-panel");
    if (boton && panel) {
      panel.hidden = !panel.hidden;
      boton.setAttribute("aria-expanded", panel.hidden ? "false" : "true");
      if (!panel.hidden) { pintarCampana(); vivo.nuevos = 0; globo(false); }
      return;
    }
    if (panel && !panel.hidden && !(evento.target.closest && evento.target.closest(".campana-caja"))) {
      panel.hidden = true;
      var c = $("[data-campana]");
      if (c) { c.setAttribute("aria-expanded", "false"); }
    }
  });

  document.addEventListener("keydown", function (evento) {
    var panel = $("#campana-panel");
    if (evento.key === "Escape" && panel && !panel.hidden) {
      panel.hidden = true;
      var c = $("[data-campana]");
      if (c) { c.setAttribute("aria-expanded", "false"); c.focus(); }
    }
  });

  A.alCerrarPanel = function () {
    if (vivo.avisoPendiente) {
      vivo.avisoPendiente.cerrar("panel");
      actualizarPagina(true);
    }
  };
  A.vivo = vivo;
  A.consultarPulso = consultar;
  A.alIniciar.push(function () {
    if (document.body.getAttribute("data-pulso") && window.fetch) { consultar(); }
  });
}());

(function () {
  "use strict";

  var A = window.Ariasmos;
  var $ = A.$;
  var $$ = A.$$;
  var pendiente = null;
  var ESPERA = 5000;

  function restaurar(envio) {
    envio.nodo.classList.remove("sale");
    envio.nodo.hidden = false;
  }

  function enviar(envio, alSalir) {
    if (!envio || envio.enviado) { return; }
    envio.enviado = true;
    if (pendiente === envio) { pendiente = null; }
    var promesa = window.fetch(envio.formulario.action, { method: "POST", body: envio.datos, credentials: "same-origin", keepalive: true, headers: { "X-Requested-With": "fetch" } });
    if (alSalir) { return; }
    promesa.then(function (r) { return r.ok ? r.text() : null; })
      .then(function (texto) {
        var error = null;
        if (texto === null) {
          error = "No se pudo guardar. Vuelve a intentarlo.";
        } else {
          var documento = new DOMParser().parseFromString(texto, "text/html");
          var mensaje = documento.querySelector(".mensajes .mensaje.error, .mensajes .mensaje.warning");
          if (mensaje) { error = mensaje.textContent.trim(); }
        }
        if (error) {
          restaurar(envio);
          A.aviso(error, { ms: 8000 });
        } else {
          envio.nodo.remove();
        }
        if (A.consultarPulso) { A.consultarPulso(); }
      })
      .catch(function () {
        restaurar(envio);
        A.aviso("No hubo respuesta del programa. La solicitud sigue pendiente.", { ms: 8000 });
      });
  }

  function soltarPendiente() {
    if (pendiente) {
      var envio = pendiente;
      if (envio.aviso) { envio.aviso.cerrar("otra"); }
      enviar(envio);
    }
  }

  A.hayEnvioEnEspera = function () { return !!pendiente; };

  document.addEventListener("submit", function (evento) {
    var formulario = evento.target;
    if (!(formulario instanceof HTMLFormElement)) { return; }
    if (!formulario.matches("[data-en-espera]") || !window.fetch) {
      soltarPendiente();
      return;
    }
    evento.preventDefault();
    soltarPendiente();
    var nodo = formulario.closest("[data-solicitud]") || formulario;
    var envio = { formulario: formulario, datos: new FormData(formulario), nodo: nodo, enviado: false };
    pendiente = envio;
    nodo.classList.add("sale");
    window.setTimeout(function () { if (!envio.enviado || pendiente === envio) { nodo.hidden = true; } }, 360);
    envio.aviso = A.aviso(formulario.getAttribute("data-hecho"), {
      accion: "Deshacer",
      ms: ESPERA,
      alAccionar: function () {
        if (envio.enviado) { return; }
        envio.enviado = true;
        pendiente = null;
        restaurar(envio);
        $$(".trabajando", formulario).forEach(function (b) { b.classList.remove("trabajando"); b.removeAttribute("aria-busy"); b.removeAttribute("aria-disabled"); });
        delete formulario.dataset.enviando;
      },
      alTerminar: function (motivo) {
        if (motivo !== "accion" && motivo !== "otra") { enviar(envio); }
      }
    });
  });

  window.addEventListener("pagehide", function () {
    if (pendiente) { enviar(pendiente, true); }
  });

  document.addEventListener("click", function (evento) {
    var cabeza = evento.target.closest && evento.target.closest("[data-abrir-solicitud]");
    if (cabeza) {
      var caja = cabeza.closest("[data-solicitud]");
      var abierta = caja.classList.toggle("abierta");
      cabeza.setAttribute("aria-expanded", abierta ? "true" : "false");
      return;
    }
    var rechazar = evento.target.closest && evento.target.closest("[data-rechazar]");
    if (rechazar) {
      var motivo = $("[data-motivo]", rechazar.closest("[data-solicitud]"));
      motivo.classList.add("visible");
      var texto = $("textarea", motivo);
      if (texto) { texto.focus(); }
    }
  });
}());

(function () {
  "use strict";

  var A = window.Ariasmos;
  var $ = A.$;
  var $$ = A.$$;

  function moverRaya(nav) {
    var activa = $("[data-pestana][aria-current='page']", nav);
    var raya = $(".raya", nav);
    if (!activa || !raya) { return; }
    raya.style.width = activa.offsetWidth + "px";
    raya.style.transform = "translateX(" + activa.offsetLeft + "px)";
  }

  function escalonar(base) {
    $$(".linea-tiempo > li", base).forEach(function (li, i) { li.style.animationDelay = Math.min(i, 20) * 70 + "ms"; });
  }

  function elegir(nav, enlace) {
    var clave = enlace.getAttribute("data-pestana");
    $$("[data-pestana]", nav).forEach(function (e) { if (e === enlace) { e.setAttribute("aria-current", "page"); } else { e.removeAttribute("aria-current"); } });
    $$("[data-hoja]").forEach(function (hoja) {
      var visible = hoja.getAttribute("data-hoja") === clave;
      hoja.hidden = !visible;
      if (visible) { A.reiniciar(hoja, "hoja-pestana"); }
    });
    moverRaya(nav);
    if (clave === "historial") {
      var hoja = $("[data-hoja='historial']");
      if (hoja && !hoja.dataset.cargado) {
        window.fetch(enlace.href, { credentials: "same-origin", headers: { "X-Requested-With": "fetch" } })
          .then(function (r) { return r.ok ? r.text() : null; })
          .then(function (texto) {
            if (!texto) { window.location.assign(enlace.href); return; }
            var region = new DOMParser().parseFromString(texto, "text/html").getElementById("historial-region");
            if (!region) { window.location.assign(enlace.href); return; }
            hoja.dataset.cargado = "1";
            hoja.replaceChildren(document.importNode(region, true));
            escalonar(hoja);
          })
          .catch(function () { window.location.assign(enlace.href); });
      }
    }
  }

  function prepararPestanas() {
    var nav = $("[data-pestanas]");
    if (!nav) { escalonar(document); return; }
    nav.setAttribute("role", "tablist");
    $$("[data-hoja]").forEach(function (hoja) { hoja.hidden = hoja.getAttribute("data-hoja") !== "cuenta"; });
    requestAnimationFrame(function () { moverRaya(nav); });
    window.addEventListener("resize", function () { moverRaya(nav); });
    nav.addEventListener("click", function (evento) {
      var enlace = evento.target.closest("[data-pestana]");
      if (!enlace || evento.ctrlKey || evento.metaKey || evento.shiftKey) { return; }
      evento.preventDefault();
      elegir(nav, enlace);
    });
  }

  function textoError(documento) {
    var errores = $$(".error, .errores p, .mensaje.error", documento).map(function (e) { return e.textContent.trim(); }).filter(Boolean);
    return errores.length ? errores[0] : null;
  }

  function guardarDato(direccion, campo, valor) {
    return window.fetch(direccion, { credentials: "same-origin", headers: { "X-Requested-With": "fetch" } })
      .then(function (r) { return r.ok ? r.text() : Promise.reject(new Error("abrir")); })
      .then(function (texto) {
        var documento = new DOMParser().parseFromString(texto, "text/html");
        var entrada = documento.querySelector("form [name='" + campo + "']");
        if (!entrada) { return Promise.reject(new Error("campo")); }
        var formulario = entrada.closest("form");
        entrada.value = valor;
        var datos = new FormData(formulario);
        return window.fetch(direccion, { method: "POST", body: datos, credentials: "same-origin", headers: { "X-Requested-With": "fetch" } });
      })
      .then(function (r) {
        return r.text().then(function (texto) {
          var documento = new DOMParser().parseFromString(texto, "text/html");
          if (new URL(r.url).pathname === new URL(direccion, window.location.href).pathname) {
            return Promise.reject(new Error(textoError(documento) || "No se pudo guardar."));
          }
          var error = $(".mensajes .mensaje.error", documento);
          if (error) { return Promise.reject(new Error(error.textContent.trim())); }
          return documento;
        });
      });
  }

  function refrescarDatos(documento) {
    var region = $("#ficha-datos");
    var nueva = documento && documento.getElementById("ficha-datos");
    if (region && nueva) { A.sustituir(region, nueva, {}); }
  }

  function editar(boton) {
    var dd = boton.parentElement;
    var antes = boton.getAttribute("data-valor");
    var direccion = boton.getAttribute("data-editar");
    var campo = boton.getAttribute("data-campo");
    var rotulo = boton.getAttribute("data-rotulo");
    var entrada = A.crear("input");
    entrada.type = boton.getAttribute("data-tipo") === "correo" ? "email" : "text";
    entrada.value = antes;
    entrada.setAttribute("aria-label", rotulo);
    entrada.className = "edicion-en-linea";
    var guardado = boton.cloneNode(true);
    boton.replaceWith(entrada);
    entrada.focus();
    entrada.select();
    var listo = false;
    function cerrar(guardar) {
      if (listo) { return; }
      listo = true;
      var nuevo = entrada.value.trim();
      if (!guardar || !nuevo || nuevo === antes) { entrada.replaceWith(guardado); guardado.focus(); return; }
      entrada.disabled = true;
      guardarDato(direccion, campo, nuevo).then(function (documento) {
        refrescarDatos(documento);
        var marcado = $("[data-editar][data-campo='" + campo + "'][data-editar='" + direccion + "']");
        if (marcado) { A.reiniciar(marcado.parentElement, "guardado"); }
        A.aviso(rotulo + " actualizado", {
          accion: "Deshacer",
          alAccionar: function () {
            guardarDato(direccion, campo, antes).then(function (otro) { refrescarDatos(otro); A.aviso(rotulo + ": se regresó el valor anterior"); })
              .catch(function (error) { A.aviso(error.message || "No se pudo regresar el valor."); });
          }
        });
      }).catch(function (error) {
        entrada.replaceWith(guardado);
        A.aviso(error && error.message && error.message.length > 8 ? error.message : "No se pudo guardar el cambio.", { ms: 8000 });
      });
    }
    entrada.addEventListener("keydown", function (evento) {
      if (evento.key === "Enter") { evento.preventDefault(); cerrar(true); }
      if (evento.key === "Escape") { evento.preventDefault(); evento.stopPropagation(); cerrar(false); }
    });
    entrada.addEventListener("blur", function () { cerrar(true); });
  }

  document.addEventListener("click", function (evento) {
    var boton = evento.target.closest && evento.target.closest("button[data-editar]");
    if (boton) { editar(boton); }
  });

  A.alIniciar.push(prepararPestanas);
}());

(function () {
  "use strict";

  var A = window.Ariasmos;
  var $ = A.$;
  var $$ = A.$$;

  function pintarFlotante(formulario) {
    var barra = $("[data-flotante]", formulario);
    if (!barra) { return; }
    var elegidas = $$("input[name='movimiento']:checked", formulario);
    var total = elegidas.reduce(function (s, c) { return s + (Number(c.getAttribute("data-importe")) || 0); }, 0);
    barra.hidden = !elegidas.length;
    $("[data-flotante-texto]", barra).textContent = elegidas.length + " " + (elegidas.length === 1 ? barra.getAttribute("data-uno") : barra.getAttribute("data-varios")) + " · " + A.dinero(total);
  }

  function prepararCola(base) {
    $$("form[data-cola-banco]", base).forEach(function (formulario) {
      $$(".tabla-banco tbody tr", formulario).forEach(function (fila, i) { fila.style.animationDelay = Math.min(i, 15) * 70 + "ms"; });
      requestAnimationFrame(function () { requestAnimationFrame(function () { $$("[data-ancho]", formulario).forEach(function (b) { b.style.width = b.getAttribute("data-ancho") + "%"; }); }); });
      pintarFlotante(formulario);
    });
  }

  document.addEventListener("click", function (evento) {
    var fila = evento.target.closest && evento.target.closest("form[data-cola-banco] tr[data-mov]");
    if (fila && !evento.target.closest("a, input, button, label")) {
      var casilla = $("input[name='movimiento']", fila);
      if (casilla && !casilla.disabled) {
        casilla.checked = !casilla.checked;
        casilla.dispatchEvent(new Event("change", { bubbles: true }));
      }
    }
    var zona = evento.target.closest && evento.target.closest("[data-zona-soltar]");
    if (zona) {
      var entrada = $("input[type='file']", zona.closest("form"));
      if (entrada) { entrada.click(); }
    }
  });

  document.addEventListener("change", function (evento) {
    var casilla = evento.target;
    if (casilla.matches && casilla.matches("form[data-cola-banco] input[name='movimiento']")) {
      casilla.closest("tr").classList.toggle("elegida", casilla.checked);
      pintarFlotante(casilla.closest("form"));
      if (casilla.form) { casilla.form.dataset.tocado = "1"; }
    }
  });

  document.addEventListener("submit", function (evento) {
    var formulario = evento.target;
    if (formulario.matches && formulario.matches("form[data-subida-banco]")) {
      var leyendo = $("[data-leyendo]", formulario);
      var zona = $("[data-zona-soltar]", formulario);
      if (leyendo) {
        leyendo.hidden = false;
        if (zona) { zona.hidden = true; }
        requestAnimationFrame(function () { requestAnimationFrame(function () { var b = $(".barra-progreso span", leyendo); if (b) { b.style.width = "100%"; } }); });
      }
    }
    if (formulario.matches && formulario.matches("form[data-cola-banco]") && !evento.defaultPrevented) {
      $$("tr.elegida", formulario).forEach(function (fila) { fila.style.animationDelay = "0ms"; fila.classList.add("sale"); });
    }
  });

  document.addEventListener("dragover", function (evento) {
    var zona = evento.target.closest && evento.target.closest("[data-zona-soltar]");
    if (zona) { evento.preventDefault(); zona.classList.add("encima"); }
  });
  document.addEventListener("dragleave", function (evento) {
    var zona = evento.target.closest && evento.target.closest("[data-zona-soltar]");
    if (zona && !zona.contains(evento.relatedTarget)) { zona.classList.remove("encima"); }
  });
  document.addEventListener("drop", function (evento) {
    var zona = evento.target.closest && evento.target.closest("[data-zona-soltar]");
    if (!zona) { return; }
    evento.preventDefault();
    zona.classList.remove("encima");
    var formulario = zona.closest("form");
    var entrada = $("input[type='file']", formulario);
    if (!entrada || !evento.dataTransfer || !evento.dataTransfer.files.length) { return; }
    entrada.files = evento.dataTransfer.files;
    if (formulario.requestSubmit) { formulario.requestSubmit(); } else { formulario.submit(); }
  });

  document.addEventListener("ariasmos:contenido", function (evento) { prepararCola(evento.target); });
  A.alIniciar.push(function () { prepararCola(document); });
}());

(function () {
  "use strict";

  var A = window.Ariasmos;
  var $ = A.$;
  var $$ = A.$$;
  var crear = A.crear;
  var raiz = document.documentElement;
  var VARIABLES = ["--primario", "--acento", "--tinte", "--boton-texto", "--boton-fondo"];
  var estado = { formulario: null, barra: null, arrastrado: null };

  function luz(hex) {
    var v = [1, 3, 5].map(function (i) { return parseInt(hex.slice(i, i + 2), 16) / 255; }).map(function (c) { return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); });
    return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2];
  }

  function hexValido(texto) { return /^#[0-9A-Fa-f]{6}$/.test(texto || ""); }

  function vistaColores(principal, acento) {
    if (!hexValido(principal) || !hexValido(acento)) { return; }
    raiz.style.setProperty("--primario", principal);
    raiz.style.setProperty("--boton-fondo", principal);
    raiz.style.setProperty("--acento", acento);
    raiz.style.setProperty("--tinte", "color-mix(in srgb, " + principal + " 13%, #fff)");
    raiz.style.setProperty("--boton-texto", luz(principal) > 0.5 ? "#1F1813" : "#FFFFFF");
  }

  function quitarVista() { VARIABLES.forEach(function (v) { raiz.style.removeProperty(v); }); }

  function coloresDe(imagen) {
    var k = 64;
    var lienzo = document.createElement("canvas");
    lienzo.width = k;
    lienzo.height = k;
    var x = lienzo.getContext("2d", { willReadFrequently: true });
    x.drawImage(imagen, 0, 0, k, k);
    var d = x.getImageData(0, 0, k, k).data;
    var m = new Map();
    for (var i = 0; i < d.length; i += 4) {
      var r = d[i], g = d[i + 1], b = d[i + 2];
      if (d[i + 3] < 128) { continue; }
      var mx = Math.max(r, g, b), mn = Math.min(r, g, b);
      if (mn > 232 || mx < 30) { continue; }
      var clave = (r >> 4) << 8 | (g >> 4) << 4 | (b >> 4);
      var e = m.get(clave) || { peso: 0, n: 0, r: 0, g: 0, b: 0 };
      e.peso += 1 + (mx - mn) / mx * 4; e.n += 1; e.r += r; e.g += g; e.b += b;
      m.set(clave, e);
    }
    var lista = Array.from(m.values()).map(function (e) { return { peso: e.peso, r: e.r / e.n, g: e.g / e.n, b: e.b / e.n }; }).sort(function (a, b) { return b.peso - a.peso; });
    if (!lista.length) { return null; }
    var hex = function (c) { return "#" + [c.r, c.g, c.b].map(function (v) { return Math.round(Math.max(0, Math.min(255, v))).toString(16).padStart(2, "0"); }).join("").toUpperCase(); };
    var lejos = function (a, b) { return Math.abs(a.r - b.r) + Math.abs(a.g - b.g) + Math.abs(a.b - b.b); };
    var uno = lista[0];
    var dos = lista.find(function (c) { return lejos(c, uno) > 110; }) || { r: uno.r * 0.6 + 100, g: uno.g * 0.6 + 100, b: uno.b * 0.6 + 100 };
    return [hex(uno), hex(dos)].sort(function (a, b) { return luz(a) - luz(b); });
  }

  function camposColor() {
    return { principal: $("input[name='color_principal']"), acento: $("input[name='color_acento']") };
  }

  function aplicarDeCampos() {
    var c = camposColor();
    if (c.principal && c.acento) { vistaColores(c.principal.value.toUpperCase(), c.acento.value.toUpperCase()); }
  }

  function vistaLogo(archivo) {
    if (!archivo || !/^image\/(png|jpeg)$/.test(archivo.type)) { return; }
    var lector = new FileReader();
    lector.onload = function () {
      var imagen = new Image();
      imagen.onload = function () {
        var destino = $(".marca-negocio .logo-negocio");
        if (!destino) {
          destino = crear("img", "logo-negocio");
          destino.width = 56;
          destino.height = 56;
          destino.alt = "";
          var caja = $(".marca-negocio");
          if (caja) { caja.insertBefore(destino, caja.firstChild); }
        }
        if (!destino.dataset.original) { destino.dataset.original = destino.getAttribute("src") || ""; }
        destino.src = lector.result;
        var par = coloresDe(imagen);
        var c = camposColor();
        if (par && c.principal && c.acento) {
          c.principal.value = par[0];
          c.acento.value = par[1];
          c.principal.dispatchEvent(new Event("input", { bubbles: true }));
          c.acento.dispatchEvent(new Event("input", { bubbles: true }));
          A.aviso("Colores tomados de tu logotipo: se ven aquí, pero se guardan hasta que lo confirmes.");
        }
      };
      imagen.src = lector.result;
    };
    lector.readAsDataURL(archivo);
  }

  function quitarVistaLogo() {
    var destino = $(".marca-negocio .logo-negocio");
    if (destino && destino.dataset.original !== undefined) {
      if (destino.dataset.original) { destino.src = destino.dataset.original; } else { destino.remove(); }
    }
  }

  function restaurar(formulario) {
    $$("input, textarea, select", formulario).forEach(function (campo) {
      if (campo.type === "hidden" || campo.type === "color" || campo.type === "submit" || campo.type === "button") { return; }
      if (campo.type === "checkbox" || campo.type === "radio") { campo.checked = campo.defaultChecked; return; }
      if (campo.type === "file") { campo.value = ""; return; }
      if (campo.tagName === "SELECT") { Array.prototype.forEach.call(campo.options, function (o) { o.selected = o.defaultSelected; }); return; }
      campo.value = campo.defaultValue;
    });
    $$("input.selector-color", formulario).forEach(function (selector) {
      var texto = selector.previousElementSibling;
      if (texto && hexValido(texto.value)) { selector.value = texto.value; }
    });
  }

  function barra() {
    if (estado.barra) { return estado.barra; }
    var caja = crear("div", "sin-guardar");
    caja.setAttribute("role", "region");
    caja.setAttribute("aria-label", "Cambios sin guardar");
    caja.appendChild(crear("span", "", "Tienes cambios sin guardar"));
    var descartar = crear("button", "boton chico secundario", "Descartar");
    descartar.type = "button";
    var guardar = crear("button", "boton chico", "Guardar");
    guardar.type = "button";
    caja.appendChild(descartar);
    caja.appendChild(guardar);
    caja.hidden = true;
    ($("main") || document.body).appendChild(caja);
    descartar.addEventListener("click", function () {
      var formulario = estado.formulario;
      if (formulario) {
        restaurar(formulario);
        $$("input[data-orden]", formulario).forEach(function (e) { pintarOrden(e); });
        formulario.dispatchEvent(new Event("change", { bubbles: true }));
      }
      quitarVista();
      quitarVistaLogo();
      estado.formulario = null;
      caja.hidden = true;
      A.aviso("Cambios descartados");
    });
    guardar.addEventListener("click", function () {
      var formulario = estado.formulario;
      if (!formulario) { return; }
      if (formulario.requestSubmit) { formulario.requestSubmit(); } else { formulario.submit(); }
    });
    estado.barra = caja;
    return caja;
  }

  function esConfiguracion(formulario) {
    if (!formulario || (formulario.method || "").toLowerCase() !== "post") { return false; }
    var ruta = window.location.pathname;
    if (ruta.indexOf("/configuracion/") !== 0 && ruta.indexOf("/rezagos/") !== 0 && ruta.indexOf("/banco/topes") !== 0) { return false; }
    return $$("input:not([type=hidden]), select, textarea", formulario).length > 1 || !!$("input[type=file], input[data-acepta='color']", formulario);
  }

  function hayCambios(formulario) {
    if (!esConfiguracion(formulario)) { return; }
    estado.formulario = formulario;
    barra().hidden = false;
  }

  function pintarOrden(entrada) {
    var etiquetas = {};
    try { etiquetas = JSON.parse(entrada.getAttribute("data-orden")) || {}; } catch (error) { etiquetas = {}; }
    var lista = entrada.nextElementSibling && entrada.nextElementSibling.matches("ol.orden-lista") ? entrada.nextElementSibling : null;
    if (!lista) {
      lista = crear("ol", "orden-lista");
      entrada.insertAdjacentElement("afterend", lista);
      entrada.hidden = true;
    }
    var claves = entrada.value.split(",").map(function (p) { return p.trim(); }).filter(Boolean);
    var nodos = claves.map(function (clave, i) {
      var item = crear("li", "orden-item");
      item.draggable = true;
      item.setAttribute("data-id", clave);
      var asa = crear("span", "asa");
      asa.setAttribute("aria-hidden", "true");
      for (var n = 0; n < 6; n += 1) { asa.appendChild(crear("i")); }
      item.appendChild(asa);
      item.appendChild(crear("span", "", (i + 1) + ". " + (etiquetas[clave] || clave)));
      var mover = crear("span", "mover");
      [["subir", "↑", "Subir "], ["bajar", "↓", "Bajar "]].forEach(function (d) {
        var b = crear("button", "", d[1]);
        b.type = "button";
        b.setAttribute("data-orden-mover", d[0]);
        b.setAttribute("aria-label", d[2] + (etiquetas[clave] || clave));
        b.disabled = d[0] === "subir" ? i === 0 : i === claves.length - 1;
        mover.appendChild(b);
      });
      item.appendChild(mover);
      return item;
    });
    lista.replaceChildren.apply(lista, nodos);
  }

  function moverOrden(entrada, clave, destino) {
    var claves = entrada.value.split(",").map(function (p) { return p.trim(); }).filter(Boolean);
    var desde = claves.indexOf(clave);
    if (desde < 0 || destino < 0 || destino >= claves.length || destino === desde) { return false; }
    claves.splice(destino, 0, claves.splice(desde, 1)[0]);
    var lista = entrada.nextElementSibling;
    A.mover(lista, ".orden-item", function () { entrada.value = claves.join(","); pintarOrden(entrada); });
    entrada.dispatchEvent(new Event("input", { bubbles: true }));
    return true;
  }

  document.addEventListener("click", function (evento) {
    var boton = evento.target.closest && evento.target.closest("[data-orden-mover]");
    if (!boton) { return; }
    var item = boton.closest(".orden-item");
    var entrada = item.parentElement.previousElementSibling;
    var clave = item.getAttribute("data-id");
    var indice = Array.prototype.indexOf.call(item.parentElement.children, item);
    var subir = boton.getAttribute("data-orden-mover") === "subir";
    if (moverOrden(entrada, clave, indice + (subir ? -1 : 1))) {
      var nuevo = $(".orden-item[data-id='" + clave + "'] [data-orden-mover='" + (subir ? "subir" : "bajar") + "']", entrada.nextElementSibling);
      if (nuevo && !nuevo.disabled) { nuevo.focus(); } else { var otro = $(".orden-item[data-id='" + clave + "'] [data-orden-mover]:not(:disabled)", entrada.nextElementSibling); if (otro) { otro.focus(); } }
    }
  });

  document.addEventListener("dragstart", function (evento) {
    var item = evento.target.closest && evento.target.closest(".orden-item");
    if (!item) { return; }
    estado.arrastrado = item.getAttribute("data-id");
    evento.dataTransfer.effectAllowed = "move";
    evento.dataTransfer.setData("text/plain", estado.arrastrado);
    requestAnimationFrame(function () { item.classList.add("arrastra"); });
  });
  document.addEventListener("dragover", function (evento) {
    var item = evento.target.closest && evento.target.closest(".orden-item");
    if (!estado.arrastrado || !item) { return; }
    evento.preventDefault();
    if (item.getAttribute("data-id") === estado.arrastrado) { return; }
    var lista = item.parentElement;
    var entrada = lista.previousElementSibling;
    var caja = item.getBoundingClientRect();
    var despues = evento.clientY > caja.top + caja.height / 2;
    var claves = entrada.value.split(",").map(function (p) { return p.trim(); });
    var de = claves.indexOf(estado.arrastrado);
    var a = claves.indexOf(item.getAttribute("data-id")) + (despues ? 1 : 0);
    if (de < a) { a -= 1; }
    if (moverOrden(entrada, estado.arrastrado, a)) {
      var nuevo = $(".orden-item[data-id='" + estado.arrastrado + "']", lista);
      if (nuevo) { nuevo.classList.add("arrastra"); }
    }
  });
  document.addEventListener("dragend", function () {
    if (!estado.arrastrado) { return; }
    var item = $(".orden-item[data-id='" + estado.arrastrado + "']");
    estado.arrastrado = null;
    if (item) { item.classList.remove("arrastra"); item.classList.add("suelta"); window.setTimeout(function () { item.classList.remove("suelta"); }, 500); }
  });

  document.addEventListener("input", function (evento) {
    var campo = evento.target;
    if (!campo.form) { return; }
    if (campo.matches("input[name='color_principal'], input[name='color_acento'], input.selector-color")) { aplicarDeCampos(); }
    hayCambios(campo.form);
  });
  document.addEventListener("change", function (evento) {
    var campo = evento.target;
    if (!campo.form || campo.matches("[data-filtro-lista]")) { return; }
    if (campo.type === "file" && campo.form.querySelector("input[name='accion'][value='logo']")) { vistaLogo(campo.files && campo.files[0]); }
    if (evento.isTrusted) { hayCambios(campo.form); }
  });
  document.addEventListener("submit", function () { if (estado.barra) { estado.barra.hidden = true; } });

  A.alIniciar.push(function () { $$("input[data-orden]").forEach(pintarOrden); });
}());
