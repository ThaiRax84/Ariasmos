using System;
using System.Globalization;

namespace Ariasmos.Nucleo
{
    public sealed class EstadoVentana
    {
        public const int AnchoMinimo = 900;
        public const int AltoMinimo = 600;

        public EstadoVentana(int x, int y, int ancho, int alto, bool maximizada)
        {
            X = x;
            Y = y;
            Ancho = ancho;
            Alto = alto;
            Maximizada = maximizada;
        }

        public int X { get; private set; }

        public int Y { get; private set; }

        public int Ancho { get; private set; }

        public int Alto { get; private set; }

        public bool Maximizada { get; private set; }

        public static EstadoVentana Leer(string texto)
        {
            if (string.IsNullOrEmpty(texto) || texto.Length > 100)
            {
                return null;
            }
            string[] partes = texto.Trim().Split(',');
            if (partes.Length != 5)
            {
                return null;
            }
            int[] numeros = new int[4];
            for (int i = 0; i < 4; i++)
            {
                if (!int.TryParse(partes[i], NumberStyles.AllowLeadingSign, CultureInfo.InvariantCulture, out numeros[i]))
                {
                    return null;
                }
            }
            if (partes[4] != "0" && partes[4] != "1")
            {
                return null;
            }
            if (numeros[2] < AnchoMinimo || numeros[3] < AltoMinimo || numeros[2] > 20000 || numeros[3] > 20000 ||
                Math.Abs(numeros[0]) > 40000 || Math.Abs(numeros[1]) > 40000)
            {
                return null;
            }
            return new EstadoVentana(numeros[0], numeros[1], numeros[2], numeros[3], partes[4] == "1");
        }

        public string Escribir()
        {
            return string.Format(CultureInfo.InvariantCulture, "{0},{1},{2},{3},{4}", X, Y, Ancho, Alto, Maximizada ? 1 : 0);
        }
    }

    public static class Agente
    {
        public static string Sufijo(string version, bool principal)
        {
            return "Ariasmos/" + version + (principal ? " principal" : " adicional");
        }

        public static bool VersionValida(string version)
        {
            if (string.IsNullOrEmpty(version))
            {
                return false;
            }
            string[] partes = version.Split('.');
            if (partes.Length != 3)
            {
                return false;
            }
            foreach (string parte in partes)
            {
                int valor;
                if (parte.Length == 0 || parte.Length > 5 || !int.TryParse(parte, NumberStyles.None, CultureInfo.InvariantCulture, out valor))
                {
                    return false;
                }
            }
            return true;
        }
    }
}
