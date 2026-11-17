using System;

namespace Ariasmos.Nucleo
{
    public static class Rutas
    {
        public const int LargoMaximo = 240;
        private const string Prohibidos = "<>:\"/\\|?*~";
        private static readonly string[] Reservados = { "CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$" };

        public static bool EsCarpetaLocal(string ruta)
        {
            if (string.IsNullOrEmpty(ruta) || ruta.Length < 4 || ruta.Length > LargoMaximo)
            {
                return false;
            }
            char unidad = char.ToUpperInvariant(ruta[0]);
            if (unidad < 'A' || unidad > 'Z' || ruta[1] != ':' || ruta[2] != '\\')
            {
                return false;
            }
            string[] segmentos = ruta.Substring(3).Split('\\');
            foreach (string segmento in segmentos)
            {
                if (!SegmentoValido(segmento))
                {
                    return false;
                }
            }
            return true;
        }

        private static bool SegmentoValido(string segmento)
        {
            if (segmento.Length == 0 || segmento == "." || segmento == "..")
            {
                return false;
            }
            char ultimo = segmento[segmento.Length - 1];
            if (ultimo == '.' || ultimo == ' ' || segmento[0] == ' ')
            {
                return false;
            }
            foreach (char c in segmento)
            {
                if (c < 0x20 || c == 0x7F || Prohibidos.IndexOf(c) >= 0)
                {
                    return false;
                }
            }
            string raiz = segmento;
            int punto = segmento.IndexOf('.');
            if (punto >= 0)
            {
                raiz = segmento.Substring(0, punto);
            }
            raiz = raiz.TrimEnd(' ').ToUpperInvariant();
            foreach (string reservado in Reservados)
            {
                if (raiz == reservado)
                {
                    return false;
                }
            }
            if (raiz.Length == 4 && (raiz.StartsWith("COM", StringComparison.Ordinal) || raiz.StartsWith("LPT", StringComparison.Ordinal)) &&
                "0123456789¹²³".IndexOf(raiz[3]) >= 0)
            {
                return false;
            }
            return true;
        }
    }
}
