using System;
using System.Globalization;

namespace Ariasmos.Nucleo
{
    public static class Direcciones
    {
        public static string Normalizar(string direccion)
        {
            if (string.IsNullOrEmpty(direccion) || direccion.Length > 253)
            {
                return null;
            }
            string minusculas = direccion.ToLowerInvariant();
            if (EsIPv4(minusculas))
            {
                return minusculas;
            }
            string[] partes = minusculas.Split('.');
            bool todoNumeros = true;
            foreach (string parte in partes)
            {
                if (parte.Length < 1 || parte.Length > 63 || parte[0] == '-' || parte[parte.Length - 1] == '-')
                {
                    return null;
                }
                bool soloDigitos = true;
                foreach (char c in parte)
                {
                    bool letra = c >= 'a' && c <= 'z';
                    bool digito = c >= '0' && c <= '9';
                    if (!letra && !digito && c != '-')
                    {
                        return null;
                    }
                    if (!digito)
                    {
                        soloDigitos = false;
                    }
                }
                if (!soloDigitos)
                {
                    todoNumeros = false;
                }
            }
            if (todoNumeros || (partes.Length > 1 && char.IsDigit(partes[partes.Length - 1][0])))
            {
                return null;
            }
            return minusculas;
        }

        public static bool EsIPv4(string texto)
        {
            string[] partes = texto.Split('.');
            if (partes.Length != 4)
            {
                return false;
            }
            foreach (string parte in partes)
            {
                int valor;
                if (parte.Length < 1 || parte.Length > 3 || (parte.Length > 1 && parte[0] == '0') ||
                    !int.TryParse(parte, NumberStyles.None, CultureInfo.InvariantCulture, out valor) || valor > 255)
                {
                    return false;
                }
            }
            return true;
        }

        public static bool Permitida(string direccion, Conexion conexion)
        {
            if (string.IsNullOrEmpty(direccion) || conexion == null || direccion.Length > 8192)
            {
                return false;
            }
            Uri uri;
            if (!Uri.TryCreate(direccion, UriKind.Absolute, out uri))
            {
                return false;
            }
            return Permitida(uri, conexion);
        }

        public static bool Permitida(Uri uri, Conexion conexion)
        {
            if (uri == null || conexion == null || !uri.IsAbsoluteUri)
            {
                return false;
            }
            if (!string.Equals(uri.Scheme, "https", StringComparison.Ordinal))
            {
                return false;
            }
            if (!string.IsNullOrEmpty(uri.UserInfo))
            {
                return false;
            }
            if (!string.Equals(uri.Host, conexion.Direccion, StringComparison.OrdinalIgnoreCase))
            {
                return false;
            }
            return uri.Port == conexion.Puerto;
        }
    }
}
