using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;

namespace Ariasmos.Nucleo
{
    public sealed class Conexion
    {
        public const int TamanoMaximo = 2048;
        public const string Producto = "ariasmos";
        public const int Formato = 1;
        private static readonly string[] Campos = { "producto", "formato", "direccion", "puerto", "huella" };

        private readonly byte[] huella;

        private Conexion(string direccion, int puerto, byte[] huella)
        {
            Direccion = direccion;
            Puerto = puerto;
            this.huella = huella;
        }

        public string Direccion { get; private set; }

        public int Puerto { get; private set; }

        public byte[] Huella
        {
            get { return (byte[])huella.Clone(); }
        }

        public string HuellaTexto
        {
            get { return Nucleo.Huella.ATexto(huella); }
        }

        public Uri Inicio
        {
            get { return new UriBuilder("https", Direccion, Puerto, "/").Uri; }
        }

        public string Origen
        {
            get { return Inicio.GetLeftPart(UriPartial.Authority); }
        }

        public static Conexion Crear(string direccion, int puerto, byte[] huella)
        {
            string limpia = Direcciones.Normalizar(direccion);
            if (limpia == null)
            {
                throw new ErrorFormato("La dirección del servidor no es un nombre de equipo ni una IP válidos.");
            }
            if (puerto < 1 || puerto > 65535)
            {
                throw new ErrorFormato("El puerto no es válido.");
            }
            if (huella == null || huella.Length != Nucleo.Huella.Largo)
            {
                throw new ErrorFormato("La huella no es válida.");
            }
            return new Conexion(limpia, puerto, (byte[])huella.Clone());
        }

        public static Conexion Leer(string ruta)
        {
            var info = new FileInfo(ruta);
            if (!info.Exists)
            {
                throw new ErrorFormato("No existe el archivo de conexión.");
            }
            if (info.Length > TamanoMaximo)
            {
                throw new ErrorFormato("El archivo de conexión es demasiado grande.");
            }
            return Desde(File.ReadAllBytes(ruta));
        }

        public static Conexion Desde(byte[] datos)
        {
            if (datos == null || datos.Length == 0)
            {
                throw new ErrorFormato("El archivo de conexión está vacío.");
            }
            if (datos.Length > TamanoMaximo)
            {
                throw new ErrorFormato("El archivo de conexión es demasiado grande.");
            }
            int inicio = datos.Length >= 3 && datos[0] == 0xEF && datos[1] == 0xBB && datos[2] == 0xBF ? 3 : 0;
            string texto;
            try
            {
                texto = new UTF8Encoding(false, true).GetString(datos, inicio, datos.Length - inicio);
            }
            catch (ArgumentException)
            {
                throw new ErrorFormato("El archivo de conexión no es UTF-8.");
            }
            var objeto = Json.ObjetoPlano(texto);
            if (objeto.Count != Campos.Length)
            {
                throw new ErrorFormato("El archivo de conexión debe tener exactamente los campos " + string.Join(", ", Campos) + ".");
            }
            foreach (string campo in Campos)
            {
                if (!objeto.ContainsKey(campo))
                {
                    throw new ErrorFormato("Falta el campo " + campo + ".");
                }
            }
            if (Cadena(objeto, "producto") != Producto)
            {
                throw new ErrorFormato("El archivo no es de Ariasmos.");
            }
            if (Entero(objeto, "formato") != Formato)
            {
                throw new ErrorFormato("Formato de archivo de conexión no soportado.");
            }
            string direccion = Cadena(objeto, "direccion");
            if (Direcciones.Normalizar(direccion) != direccion)
            {
                throw new ErrorFormato("La dirección del servidor no es válida.");
            }
            long puerto = Entero(objeto, "puerto");
            if (puerto < 1 || puerto > 65535)
            {
                throw new ErrorFormato("El puerto no es válido.");
            }
            return Crear(direccion, (int)puerto, Nucleo.Huella.DesdeTexto(Cadena(objeto, "huella")));
        }

        public string AJson()
        {
            return "{\"producto\": " + Json.Texto(Producto) + ", \"formato\": " + Formato.ToString(CultureInfo.InvariantCulture) +
                ", \"direccion\": " + Json.Texto(Direccion) + ", \"puerto\": " + Puerto.ToString(CultureInfo.InvariantCulture) +
                ", \"huella\": " + Json.Texto(HuellaTexto) + "}\n";
        }

        private static string Cadena(Dictionary<string, object> objeto, string campo)
        {
            var valor = objeto[campo] as string;
            if (valor == null)
            {
                throw new ErrorFormato("El campo " + campo + " debe ser texto.");
            }
            return valor;
        }

        private static long Entero(Dictionary<string, object> objeto, string campo)
        {
            var numero = objeto[campo] as JsonNumero;
            long valor;
            if (numero == null || !numero.EsEntero || numero.Texto.StartsWith("-", StringComparison.Ordinal) || numero.Texto.Length > 6 ||
                !long.TryParse(numero.Texto, NumberStyles.None, CultureInfo.InvariantCulture, out valor))
            {
                throw new ErrorFormato("El campo " + campo + " debe ser un número entero.");
            }
            return valor;
        }
    }
}
