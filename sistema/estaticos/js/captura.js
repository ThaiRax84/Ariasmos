(function () {
  var ALFABETO_CODIGO = "ABCDEFGHJKMNPQRSTUVWXYZ23456789-";

  function soloDigitos(texto) {
    return texto.replace(/[^0-9]/g, "");
  }

  function decimal(texto, permitirComa) {
    var limpio = texto.replace(permitirComa ? /[^0-9.,]/g : /[^0-9.]/g, "");
    var punto = limpio.indexOf(".");
    if (punto === -1) {
      return limpio;
    }
    var entero = limpio.slice(0, punto);
    var fraccion = limpio.slice(punto + 1).replace(/[.,]/g, "").slice(0, 2);
    return entero + "." + fraccion;
  }

  var LIMPIEZA = {
    digitos: soloDigitos,
    entero: soloDigitos,
    matricula: function (texto) { return texto.replace(/[^0-9 \-]/g, ""); },
    dinero: function (texto) { return decimal(texto, true); },
    porcentaje: function (texto) {
      var limpio = decimal(texto, false);
      if (limpio !== "" && parseFloat(limpio) > 100) {
        return "100";
      }
      return limpio;
    },
    usuario: function (texto) { return texto.replace(/[^A-Za-z0-9._\-]/g, ""); },
    codigo_activacion: function (texto) {
      return texto.toUpperCase().split("").filter(function (c) { return ALFABETO_CODIGO.indexOf(c) !== -1; }).join("");
    },
    recibo: function (texto) { return texto.toUpperCase().replace(/[^A-Z0-9|\-]/g, ""); },
    folio: function (texto) { return texto.toUpperCase().replace(/[^A-Z0-9\-]/g, ""); },
    hora: function (texto) {
      var limpio = texto.replace(/[^0-9:]/g, "");
      var dos = limpio.indexOf(":");
      if (dos === -1) {
        return limpio.slice(0, 2);
      }
      return limpio.slice(0, Math.min(dos, 2)) + ":" + limpio.slice(dos + 1).replace(/:/g, "").slice(0, 2);
    }
  };

  function quitarSeparadores(tipo, texto) {
    if (tipo === "digitos" || tipo === "entero") {
      return texto.replace(/[\s\-.()+]/g, "");
    }
    if (tipo === "dinero") {
      return texto.replace(/^\s*[^0-9.,\-]+/, "").replace(/\s*[A-Za-z]{3}\s*$/, "");
    }
    if (tipo === "porcentaje") {
      return texto.replace(/%/g, "");
    }
    return texto;
  }

  function maximo(campo) {
    var valor = parseInt(campo.getAttribute("maxlength"), 10);
    return isNaN(valor) ? Infinity : valor;
  }

  function aplicar(campo) {
    var limpiar = LIMPIEZA[campo.getAttribute("data-acepta")];
    if (!limpiar) {
      return;
    }
    var original = campo.value;
    var limpio = limpiar(original).slice(0, maximo(campo));
    if (limpio !== original) {
      var posicion = campo.selectionStart;
      var antes = posicion === null ? limpio.length : limpiar(original.slice(0, posicion)).length;
      campo.value = limpio;
      try {
        campo.setSelectionRange(antes, antes);
      } catch (error) {
      }
    }
  }

  function alPegar(evento) {
    var campo = evento.target;
    var tipo = campo.getAttribute("data-acepta");
    var datos = evento.clipboardData || window.clipboardData;
    if (!LIMPIEZA[tipo] || !datos) {
      return;
    }
    evento.preventDefault();
    var texto = LIMPIEZA[tipo](quitarSeparadores(tipo, datos.getData("text") || ""));
    var inicio = campo.selectionStart || 0;
    var fin = campo.selectionEnd || 0;
    var espacio = maximo(campo) - (campo.value.length - (fin - inicio));
    campo.setRangeText(texto.slice(0, Math.max(espacio, 0)), inicio, fin, "end");
    aplicar(campo);
  }

  function antesDeEscribir(evento) {
    var campo = evento.target;
    var limpiar = LIMPIEZA[campo.getAttribute("data-acepta")];
    if (!limpiar || evento.inputType !== "insertText" || !evento.data) {
      return;
    }
    var inicio = campo.selectionStart || 0;
    var fin = campo.selectionEnd || 0;
    var propuesto = campo.value.slice(0, inicio) + evento.data + campo.value.slice(fin);
    if (limpiar(propuesto) !== propuesto && limpiar(propuesto).length < propuesto.length) {
      evento.preventDefault();
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("input[data-acepta]").forEach(function (campo) {
      if (campo.type === "number") {
        return;
      }
      campo.addEventListener("beforeinput", antesDeEscribir);
      campo.addEventListener("input", function () { aplicar(campo); });
      campo.addEventListener("paste", alPegar);
    });
  });
})();
