using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace Ariasmos.Nucleo
{
    public sealed class ErrorFormato : Exception
    {
        public ErrorFormato(string mensaje) : base(mensaje)
        {
        }
    }

    public sealed class JsonNumero
    {
        public JsonNumero(string texto)
        {
            Texto = texto;
        }

        public string Texto { get; private set; }

        public bool EsEntero
        {
            get
            {
                foreach (char c in Texto)
                {
                    if (c == '.' || c == 'e' || c == 'E')
                    {
                        return false;
                    }
                }
                return true;
            }
        }
    }

    public static class Json
    {
        public const int ProfundidadMaxima = 16;

        public static object Analizar(string texto)
        {
            if (texto == null)
            {
                throw new ErrorFormato("Sin contenido.");
            }
            var lector = new Lector(texto);
            lector.Espacios();
            object valor = lector.Valor(0);
            lector.Espacios();
            if (!lector.Fin)
            {
                throw new ErrorFormato("Hay contenido después del final.");
            }
            return valor;
        }

        public static Dictionary<string, object> ObjetoPlano(string texto)
        {
            var objeto = Analizar(texto) as Dictionary<string, object>;
            if (objeto == null)
            {
                throw new ErrorFormato("No es un objeto.");
            }
            foreach (var par in objeto)
            {
                if (!(par.Value is string) && !(par.Value is JsonNumero))
                {
                    throw new ErrorFormato("El campo " + par.Key + " no es texto ni número.");
                }
            }
            return objeto;
        }

        public static string Texto(string valor)
        {
            var salida = new StringBuilder(valor.Length + 2);
            salida.Append('"');
            foreach (char c in valor)
            {
                switch (c)
                {
                    case '"':
                        salida.Append("\\\"");
                        break;
                    case '\\':
                        salida.Append("\\\\");
                        break;
                    case '\n':
                        salida.Append("\\n");
                        break;
                    case '\r':
                        salida.Append("\\r");
                        break;
                    case '\t':
                        salida.Append("\\t");
                        break;
                    default:
                        if (c < 0x20 || c == '<' || c == '>' || c == '&' || c == ' ' || c == ' ')
                        {
                            salida.Append("\\u").Append(((int)c).ToString("x4", CultureInfo.InvariantCulture));
                        }
                        else
                        {
                            salida.Append(c);
                        }
                        break;
                }
            }
            salida.Append('"');
            return salida.ToString();
        }

        private sealed class Lector
        {
            private readonly string texto;
            private int posicion;

            public Lector(string texto)
            {
                this.texto = texto;
            }

            public bool Fin
            {
                get { return posicion >= texto.Length; }
            }

            public void Espacios()
            {
                while (posicion < texto.Length)
                {
                    char c = texto[posicion];
                    if (c == ' ' || c == '\t' || c == '\r' || c == '\n')
                    {
                        posicion++;
                    }
                    else
                    {
                        break;
                    }
                }
            }

            private char Actual()
            {
                if (posicion >= texto.Length)
                {
                    throw new ErrorFormato("El contenido termina antes de tiempo.");
                }
                return texto[posicion];
            }

            private void Esperar(char c)
            {
                if (Actual() != c)
                {
                    throw new ErrorFormato("Se esperaba '" + c + "' en la posición " + posicion + ".");
                }
                posicion++;
            }

            private void Palabra(string palabra)
            {
                if (string.CompareOrdinal(texto, posicion, palabra, 0, palabra.Length) != 0)
                {
                    throw new ErrorFormato("Valor no válido en la posición " + posicion + ".");
                }
                posicion += palabra.Length;
            }

            public object Valor(int profundidad)
            {
                if (profundidad > ProfundidadMaxima)
                {
                    throw new ErrorFormato("Demasiados niveles.");
                }
                char c = Actual();
                switch (c)
                {
                    case '{':
                        return Objeto(profundidad);
                    case '[':
                        return Lista(profundidad);
                    case '"':
                        return Cadena();
                    case 't':
                        Palabra("true");
                        return true;
                    case 'f':
                        Palabra("false");
                        return false;
                    case 'n':
                        Palabra("null");
                        return null;
                    default:
                        if (c == '-' || (c >= '0' && c <= '9'))
                        {
                            return Numero();
                        }
                        throw new ErrorFormato("Valor no válido en la posición " + posicion + ".");
                }
            }

            private Dictionary<string, object> Objeto(int profundidad)
            {
                Esperar('{');
                var resultado = new Dictionary<string, object>(StringComparer.Ordinal);
                Espacios();
                if (Actual() == '}')
                {
                    posicion++;
                    return resultado;
                }
                while (true)
                {
                    Espacios();
                    if (Actual() != '"')
                    {
                        throw new ErrorFormato("Se esperaba el nombre de un campo en la posición " + posicion + ".");
                    }
                    string clave = Cadena();
                    if (resultado.ContainsKey(clave))
                    {
                        throw new ErrorFormato("El campo " + clave + " está repetido.");
                    }
                    Espacios();
                    Esperar(':');
                    Espacios();
                    resultado[clave] = Valor(profundidad + 1);
                    Espacios();
                    char c = Actual();
                    posicion++;
                    if (c == '}')
                    {
                        return resultado;
                    }
                    if (c != ',')
                    {
                        throw new ErrorFormato("Se esperaba ',' o '}' en la posición " + (posicion - 1) + ".");
                    }
                }
            }

            private List<object> Lista(int profundidad)
            {
                Esperar('[');
                var resultado = new List<object>();
                Espacios();
                if (Actual() == ']')
                {
                    posicion++;
                    return resultado;
                }
                while (true)
                {
                    Espacios();
                    resultado.Add(Valor(profundidad + 1));
                    Espacios();
                    char c = Actual();
                    posicion++;
                    if (c == ']')
                    {
                        return resultado;
                    }
                    if (c != ',')
                    {
                        throw new ErrorFormato("Se esperaba ',' o ']' en la posición " + (posicion - 1) + ".");
                    }
                }
            }

            private string Cadena()
            {
                Esperar('"');
                var salida = new StringBuilder();
                while (true)
                {
                    char c = Actual();
                    posicion++;
                    if (c == '"')
                    {
                        return salida.ToString();
                    }
                    if (c < 0x20)
                    {
                        throw new ErrorFormato("Carácter de control dentro de un texto.");
                    }
                    if (c != '\\')
                    {
                        salida.Append(c);
                        continue;
                    }
                    char escape = Actual();
                    posicion++;
                    switch (escape)
                    {
                        case '"':
                            salida.Append('"');
                            break;
                        case '\\':
                            salida.Append('\\');
                            break;
                        case '/':
                            salida.Append('/');
                            break;
                        case 'b':
                            salida.Append('\b');
                            break;
                        case 'f':
                            salida.Append('\f');
                            break;
                        case 'n':
                            salida.Append('\n');
                            break;
                        case 'r':
                            salida.Append('\r');
                            break;
                        case 't':
                            salida.Append('\t');
                            break;
                        case 'u':
                            if (posicion + 4 > texto.Length)
                            {
                                throw new ErrorFormato("Escape \\u incompleto.");
                            }
                            int codigo;
                            if (!int.TryParse(texto.Substring(posicion, 4), NumberStyles.AllowHexSpecifier, CultureInfo.InvariantCulture, out codigo))
                            {
                                throw new ErrorFormato("Escape \\u no válido.");
                            }
                            posicion += 4;
                            salida.Append((char)codigo);
                            break;
                        default:
                            throw new ErrorFormato("Escape no válido dentro de un texto.");
                    }
                }
            }

            private JsonNumero Numero()
            {
                int inicio = posicion;
                if (Actual() == '-')
                {
                    posicion++;
                }
                if (Actual() == '0')
                {
                    posicion++;
                }
                else
                {
                    Digitos();
                }
                if (posicion < texto.Length && texto[posicion] == '.')
                {
                    posicion++;
                    Digitos();
                }
                if (posicion < texto.Length && (texto[posicion] == 'e' || texto[posicion] == 'E'))
                {
                    posicion++;
                    if (Actual() == '+' || Actual() == '-')
                    {
                        posicion++;
                    }
                    Digitos();
                }
                return new JsonNumero(texto.Substring(inicio, posicion - inicio));
            }

            private void Digitos()
            {
                int inicio = posicion;
                while (posicion < texto.Length && texto[posicion] >= '0' && texto[posicion] <= '9')
                {
                    posicion++;
                }
                if (posicion == inicio)
                {
                    throw new ErrorFormato("Número no válido en la posición " + inicio + ".");
                }
            }
        }
    }
}
