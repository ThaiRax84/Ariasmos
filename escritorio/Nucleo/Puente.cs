using System;
using System.Collections.Generic;

namespace Ariasmos.Nucleo
{
    public enum TipoMensaje
    {
        ElegirCarpeta,
        DarPermiso,
    }

    public sealed class MensajePuente
    {
        public MensajePuente(TipoMensaje tipo, string id, string ruta)
        {
            Tipo = tipo;
            Id = id;
            Ruta = ruta;
        }

        public TipoMensaje Tipo { get; private set; }

        public string Id { get; private set; }

        public string Ruta { get; private set; }
    }

    public static class Puente
    {
        public const int LargoMaximo = 1024;

        public static MensajePuente Validar(string json, string origen, Conexion conexion, bool principal, bool documentoVerificado)
        {
            if (!principal || !documentoVerificado || conexion == null)
            {
                return null;
            }
            if (!Direcciones.Permitida(origen, conexion))
            {
                return null;
            }
            if (json == null || json.Length > LargoMaximo)
            {
                return null;
            }
            Dictionary<string, object> objeto;
            try
            {
                objeto = Json.ObjetoPlano(json);
            }
            catch (ErrorFormato)
            {
                return null;
            }
            string tipo = objeto.ContainsKey("tipo") ? objeto["tipo"] as string : null;
            string id = objeto.ContainsKey("id") ? objeto["id"] as string : null;
            if (!IdValido(id))
            {
                return null;
            }
            if (tipo == "elegir_carpeta" && objeto.Count == 2)
            {
                return new MensajePuente(TipoMensaje.ElegirCarpeta, id, null);
            }
            if (tipo == "dar_permiso" && objeto.Count == 3 && objeto.ContainsKey("ruta"))
            {
                string ruta = objeto["ruta"] as string;
                if (!Rutas.EsCarpetaLocal(ruta))
                {
                    return null;
                }
                return new MensajePuente(TipoMensaje.DarPermiso, id, ruta);
            }
            return null;
        }

        public static bool IdValido(string id)
        {
            if (string.IsNullOrEmpty(id) || id.Length > 32)
            {
                return false;
            }
            foreach (char c in id)
            {
                bool valido = (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9');
                if (!valido)
                {
                    return false;
                }
            }
            return true;
        }

        public static string RespuestaCarpeta(string id, string ruta)
        {
            return "{\"id\":" + Json.Texto(id) + ",\"ruta\":" + Json.Texto(ruta ?? string.Empty) + "}";
        }

        public static string RespuestaPermiso(string id)
        {
            return "{\"id\":" + Json.Texto(id) + "}";
        }
    }
}
