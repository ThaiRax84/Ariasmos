using System;
using System.Collections.Generic;
using System.Security.Cryptography;
using System.Text;

namespace Ariasmos.Nucleo
{
    public static class Huella
    {
        public const int Largo = 32;

        public static byte[] Sha256(byte[] der)
        {
            if (der == null || der.Length == 0)
            {
                throw new ErrorFormato("Certificado vacío.");
            }
            using (var sha = SHA256.Create())
            {
                return sha.ComputeHash(der);
            }
        }

        public static bool Coincide(byte[] der, byte[] esperada)
        {
            if (der == null || der.Length == 0 || esperada == null || esperada.Length != Largo)
            {
                return false;
            }
            return Iguales(Sha256(der), esperada);
        }

        public static bool Iguales(byte[] a, byte[] b)
        {
            if (a == null || b == null || a.Length != b.Length)
            {
                return false;
            }
            int diferencia = 0;
            for (int i = 0; i < a.Length; i++)
            {
                diferencia |= a[i] ^ b[i];
            }
            return diferencia == 0;
        }

        public static byte[] DesdeTexto(string texto)
        {
            if (texto == null || texto.Length != Largo * 2)
            {
                throw new ErrorFormato("La huella debe tener 64 dígitos hexadecimales.");
            }
            var bytes = new byte[Largo];
            for (int i = 0; i < Largo; i++)
            {
                bytes[i] = (byte)((Digito(texto[2 * i]) << 4) | Digito(texto[2 * i + 1]));
            }
            return bytes;
        }

        public static string ATexto(byte[] huella)
        {
            var salida = new StringBuilder(huella.Length * 2);
            foreach (byte b in huella)
            {
                salida.Append(b.ToString("X2", System.Globalization.CultureInfo.InvariantCulture));
            }
            return salida.ToString();
        }

        private static int Digito(char c)
        {
            if (c >= '0' && c <= '9')
            {
                return c - '0';
            }
            if (c >= 'A' && c <= 'F')
            {
                return c - 'A' + 10;
            }
            throw new ErrorFormato("La huella solo admite dígitos y letras A a F mayúsculas.");
        }

        public static byte[] DerDePem(string pem)
        {
            const string inicio = "-----BEGIN CERTIFICATE-----";
            const string fin = "-----END CERTIFICATE-----";
            if (pem == null)
            {
                throw new ErrorFormato("Sin certificado.");
            }
            int a = pem.IndexOf(inicio, StringComparison.Ordinal);
            int b = pem.IndexOf(fin, StringComparison.Ordinal);
            if (a < 0 || b < a || pem.IndexOf(inicio, a + inicio.Length, StringComparison.Ordinal) >= 0)
            {
                throw new ErrorFormato("No es un único certificado PEM.");
            }
            string cuerpo = pem.Substring(a + inicio.Length, b - a - inicio.Length);
            var limpio = new StringBuilder(cuerpo.Length);
            foreach (char c in cuerpo)
            {
                if (c == '\r' || c == '\n' || c == ' ' || c == '\t')
                {
                    continue;
                }
                limpio.Append(c);
            }
            try
            {
                return Convert.FromBase64String(limpio.ToString());
            }
            catch (FormatException)
            {
                throw new ErrorFormato("El certificado PEM no es base64 válido.");
            }
        }

        public static IList<byte[]> CertificadosDeCdp(string respuesta)
        {
            var objeto = Json.Analizar(respuesta) as Dictionary<string, object>;
            if (objeto == null)
            {
                throw new ErrorFormato("Respuesta sin objeto.");
            }
            object lista;
            if (!objeto.TryGetValue("tableNames", out lista) || !(lista is List<object>))
            {
                throw new ErrorFormato("Respuesta sin certificados.");
            }
            var resultado = new List<byte[]>();
            foreach (object elemento in (List<object>)lista)
            {
                var texto = elemento as string;
                if (string.IsNullOrEmpty(texto))
                {
                    throw new ErrorFormato("Certificado vacío en la respuesta.");
                }
                try
                {
                    resultado.Add(Convert.FromBase64String(texto));
                }
                catch (FormatException)
                {
                    throw new ErrorFormato("Certificado no válido en la respuesta.");
                }
            }
            return resultado;
        }

        public static bool CoincideEstadoSeguridad(string evento, byte[] esperada)
        {
            try
            {
                var raiz = Json.Analizar(evento) as Dictionary<string, object>;
                object visible;
                object estado;
                object lista;
                if (raiz == null || !raiz.TryGetValue("visibleSecurityState", out visible) || !(visible is Dictionary<string, object>))
                {
                    return false;
                }
                if (!((Dictionary<string, object>)visible).TryGetValue("certificateSecurityState", out estado) || !(estado is Dictionary<string, object>))
                {
                    return false;
                }
                if (!((Dictionary<string, object>)estado).TryGetValue("certificate", out lista) || !(lista is List<object>))
                {
                    return false;
                }
                var certificados = (List<object>)lista;
                var primero = certificados.Count > 0 ? certificados[0] as string : null;
                return !string.IsNullOrEmpty(primero) && Coincide(Convert.FromBase64String(primero), esperada);
            }
            catch (ErrorFormato)
            {
                return false;
            }
            catch (FormatException)
            {
                return false;
            }
        }

        public static bool CoincideCdp(string respuesta, byte[] esperada)
        {
            try
            {
                var certificados = CertificadosDeCdp(respuesta);
                return certificados.Count > 0 && Coincide(certificados[0], esperada);
            }
            catch (ErrorFormato)
            {
                return false;
            }
        }
    }
}
