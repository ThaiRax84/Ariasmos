using System;
using System.IO;
using System.Text;
using Ariasmos.Nucleo;
using Xunit;

namespace Ariasmos.Pruebas
{
    public class PruebasConexion
    {
        private const string HuellaAbc = "BA7816BF8F01CFEA414140DE5DAE2223B00361A396177A9CB410FF61F20015AD";

        private static string Archivo(string direccion = "servidor", string puerto = "443", string huella = HuellaAbc, string extra = "")
        {
            return "{\"producto\": \"ariasmos\", \"formato\": 1, \"direccion\": \"" + direccion + "\", \"puerto\": " + puerto + ", \"huella\": \"" + huella + "\"" + extra + "}";
        }

        private static Conexion Leer(string texto)
        {
            return Conexion.Desde(Encoding.UTF8.GetBytes(texto));
        }

        [Fact]
        public void LeeUnArchivoCorrecto()
        {
            var conexion = Leer(Archivo());
            Assert.Equal("servidor", conexion.Direccion);
            Assert.Equal(443, conexion.Puerto);
            Assert.Equal(HuellaAbc, conexion.HuellaTexto);
            Assert.Equal("https://servidor/", conexion.Inicio.AbsoluteUri);
            Assert.Equal("https://servidor", conexion.Origen);
        }

        [Fact]
        public void PuertoDistintoQuedaEnElOrigen()
        {
            var conexion = Leer(Archivo("192.168.1.20", "8443"));
            Assert.Equal("https://192.168.1.20:8443/", conexion.Inicio.AbsoluteUri);
            Assert.Equal("https://192.168.1.20:8443", conexion.Origen);
        }

        [Fact]
        public void AceptaMarcaDeOrdenDeBytes()
        {
            var bytes = Encoding.UTF8.GetPreamble();
            var cuerpo = Encoding.UTF8.GetBytes(Archivo());
            var todo = new byte[bytes.Length + cuerpo.Length];
            bytes.CopyTo(todo, 0);
            cuerpo.CopyTo(todo, bytes.Length);
            Assert.Equal("servidor", Conexion.Desde(todo).Direccion);
        }

        [Theory]
        [InlineData(", \"otro\": \"x\"")]
        [InlineData(", \"producto\": \"ariasmos\"")]
        public void RechazaCamposDeMasORepetidos(string extra)
        {
            Assert.Throws<ErrorFormato>(() => Leer(Archivo(extra: extra)));
        }

        [Fact]
        public void RechazaCamposDeMenos()
        {
            Assert.Throws<ErrorFormato>(() => Leer("{\"producto\": \"ariasmos\", \"formato\": 1, \"direccion\": \"servidor\", \"puerto\": 443}"));
        }

        [Theory]
        [InlineData("{\"producto\": \"otro\", \"formato\": 1, \"direccion\": \"servidor\", \"puerto\": 443, \"huella\": \"" + HuellaAbc + "\"}")]
        [InlineData("{\"producto\": \"ariasmos\", \"formato\": 2, \"direccion\": \"servidor\", \"puerto\": 443, \"huella\": \"" + HuellaAbc + "\"}")]
        [InlineData("{\"producto\": \"ariasmos\", \"formato\": \"1\", \"direccion\": \"servidor\", \"puerto\": 443, \"huella\": \"" + HuellaAbc + "\"}")]
        [InlineData("{\"producto\": \"ariasmos\", \"formato\": 1, \"direccion\": \"servidor\", \"puerto\": \"443\", \"huella\": \"" + HuellaAbc + "\"}")]
        [InlineData("{\"producto\": \"ariasmos\", \"formato\": 1, \"direccion\": \"servidor\", \"puerto\": 443.0, \"huella\": \"" + HuellaAbc + "\"}")]
        [InlineData("{\"producto\": \"ariasmos\", \"formato\": 1, \"direccion\": [\"servidor\"], \"puerto\": 443, \"huella\": \"" + HuellaAbc + "\"}")]
        [InlineData("{\"producto\": \"ariasmos\", \"formato\": 1, \"direccion\": \"servidor\", \"puerto\": 443, \"huella\": \"" + HuellaAbc + "\"} x")]
        [InlineData("[]")]
        [InlineData("")]
        public void RechazaFormatosIncorrectos(string texto)
        {
            Assert.Throws<ErrorFormato>(() => Leer(texto));
        }

        [Theory]
        [InlineData("0")]
        [InlineData("65536")]
        [InlineData("-443")]
        [InlineData("0443")]
        public void RechazaPuertosInvalidos(string puerto)
        {
            Assert.Throws<ErrorFormato>(() => Leer(Archivo(puerto: puerto)));
        }

        [Theory]
        [InlineData("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")]
        [InlineData("BA:78:16:BF")]
        [InlineData("BA7816BF8F01CFEA414140DE5DAE2223B00361A396177A9CB410FF61F20015")]
        [InlineData("ZZ7816BF8F01CFEA414140DE5DAE2223B00361A396177A9CB410FF61F20015AD")]
        public void RechazaHuellasInvalidas(string huella)
        {
            Assert.Throws<ErrorFormato>(() => Leer(Archivo(huella: huella)));
        }

        [Theory]
        [InlineData("Servidor")]
        [InlineData("servidor.")]
        [InlineData("-servidor")]
        [InlineData("serv idor")]
        [InlineData("serv_idor")]
        [InlineData("256.1.1.1")]
        [InlineData("1.2.3")]
        [InlineData("192.168.001.1")]
        [InlineData("evil.com/x")]
        [InlineData("user@servidor")]
        [InlineData("[::1]")]
        [InlineData("")]
        public void RechazaDireccionesInvalidas(string direccion)
        {
            Assert.Throws<ErrorFormato>(() => Leer(Archivo(direccion: direccion)));
        }

        [Fact]
        public void RechazaArchivosGrandes()
        {
            var texto = Archivo(extra: ", \"relleno\": \"" + new string('a', Conexion.TamanoMaximo) + "\"");
            Assert.Throws<ErrorFormato>(() => Leer(texto));
        }

        [Fact]
        public void RechazaUtf8Invalido()
        {
            var bytes = Encoding.UTF8.GetBytes(Archivo());
            bytes[30] = 0xFF;
            Assert.Throws<ErrorFormato>(() => Conexion.Desde(bytes));
        }

        [Fact]
        public void LeeDesdeDisco()
        {
            string ruta = Path.GetTempFileName();
            try
            {
                File.WriteAllText(ruta, Archivo("localhost", "9443"));
                var conexion = Conexion.Leer(ruta);
                Assert.Equal("localhost", conexion.Direccion);
                Assert.Equal(9443, conexion.Puerto);
            }
            finally
            {
                File.Delete(ruta);
            }
        }

        [Fact]
        public void IdaYVuelta()
        {
            var conexion = Leer(Archivo("caja-1", "8443"));
            var otra = Leer(conexion.AJson());
            Assert.Equal(conexion.Direccion, otra.Direccion);
            Assert.Equal(conexion.Puerto, otra.Puerto);
            Assert.Equal(conexion.HuellaTexto, otra.HuellaTexto);
        }
    }

    public class PruebasHuella
    {
        private static readonly byte[] Abc = Encoding.ASCII.GetBytes("abc");
        private const string HuellaAbc = "BA7816BF8F01CFEA414140DE5DAE2223B00361A396177A9CB410FF61F20015AD";

        [Fact]
        public void CalculaSha256()
        {
            Assert.Equal(HuellaAbc, Huella.ATexto(Huella.Sha256(Abc)));
        }

        [Fact]
        public void ComparaContraLaEsperada()
        {
            Assert.True(Huella.Coincide(Abc, Huella.DesdeTexto(HuellaAbc)));
            Assert.False(Huella.Coincide(Encoding.ASCII.GetBytes("abd"), Huella.DesdeTexto(HuellaAbc)));
            Assert.False(Huella.Coincide(new byte[0], Huella.DesdeTexto(HuellaAbc)));
            Assert.False(Huella.Coincide(Abc, new byte[31]));
            Assert.False(Huella.Coincide(null, Huella.DesdeTexto(HuellaAbc)));
        }

        [Fact]
        public void LeeElCertificadoDeUnPem()
        {
            string pem = "-----BEGIN CERTIFICATE-----\r\n" + Convert.ToBase64String(Abc) + "\r\n-----END CERTIFICATE-----\r\n";
            Assert.Equal(Abc, Huella.DerDePem(pem));
            Assert.Throws<ErrorFormato>(() => Huella.DerDePem(pem + pem));
            Assert.Throws<ErrorFormato>(() => Huella.DerDePem("sin certificado"));
            Assert.Throws<ErrorFormato>(() => Huella.DerDePem("-----BEGIN CERTIFICATE-----\n!!!\n-----END CERTIFICATE-----"));
        }

        [Fact]
        public void LeeLaRespuestaDelProtocolo()
        {
            string respuesta = "{\"tableNames\":[\"" + Convert.ToBase64String(Abc) + "\",\"" + Convert.ToBase64String(new byte[] { 1, 2 }) + "\"]}";
            Assert.True(Huella.CoincideCdp(respuesta, Huella.DesdeTexto(HuellaAbc)));
            Assert.False(Huella.CoincideCdp("{\"tableNames\":[]}", Huella.DesdeTexto(HuellaAbc)));
            Assert.False(Huella.CoincideCdp("{}", Huella.DesdeTexto(HuellaAbc)));
            Assert.False(Huella.CoincideCdp("no es json", Huella.DesdeTexto(HuellaAbc)));
            Assert.False(Huella.CoincideCdp("{\"tableNames\":[\"" + Convert.ToBase64String(new byte[] { 9 }) + "\"]}", Huella.DesdeTexto(HuellaAbc)));
        }
    }

    public class PruebasDirecciones
    {
        private static Conexion Con(string direccion, int puerto)
        {
            return Conexion.Crear(direccion, puerto, Huella.Sha256(new byte[] { 1 }));
        }

        [Theory]
        [InlineData("https://servidor/", true)]
        [InlineData("https://servidor:443/cobros/1/?a=b#x", true)]
        [InlineData("https://SERVIDOR/inicio/", true)]
        [InlineData("http://servidor/", false)]
        [InlineData("https://servidor:8443/", false)]
        [InlineData("https://otro/", false)]
        [InlineData("https://servidor.evil.com/", false)]
        [InlineData("https://evil.com/servidor", false)]
        [InlineData("https://usuario@servidor/", false)]
        [InlineData("file:///C:/Windows/", false)]
        [InlineData("about:blank", false)]
        [InlineData("data:text/html,hola", false)]
        [InlineData("javascript:alert(1)", false)]
        [InlineData("mailto:a@b.c", false)]
        [InlineData("/relativa", false)]
        [InlineData("", false)]
        [InlineData(null, false)]
        public void SoloLaDireccionConfigurada(string url, bool esperado)
        {
            Assert.Equal(esperado, Direcciones.Permitida(url, Con("servidor", 443)));
        }

        [Fact]
        public void RespetaElPuertoYLaIp()
        {
            var conexion = Con("192.168.0.10", 8443);
            Assert.True(Direcciones.Permitida("https://192.168.0.10:8443/", conexion));
            Assert.False(Direcciones.Permitida("https://192.168.0.10/", conexion));
            Assert.False(Direcciones.Permitida("https://192.168.0.11:8443/", conexion));
        }

        [Theory]
        [InlineData("localhost", "localhost")]
        [InlineData("Caja-1", "caja-1")]
        [InlineData("servidor.local", "servidor.local")]
        [InlineData("10.0.0.1", "10.0.0.1")]
        [InlineData("1234", null)]
        [InlineData("a..b", null)]
        [InlineData("host.123", null)]
        public void NormalizaDirecciones(string entrada, string esperada)
        {
            Assert.Equal(esperada, Direcciones.Normalizar(entrada));
        }
    }

    public class PruebasPuente
    {
        private static readonly Conexion Servidor = Conexion.Crear("servidor", 443, Huella.Sha256(new byte[] { 1 }));
        private const string Origen = "https://servidor/configuracion/";

        [Fact]
        public void AceptaElegirCarpeta()
        {
            var mensaje = Puente.Validar("{\"tipo\":\"elegir_carpeta\",\"id\":\"a1\"}", Origen, Servidor, true, true);
            Assert.NotNull(mensaje);
            Assert.Equal(TipoMensaje.ElegirCarpeta, mensaje.Tipo);
            Assert.Equal("a1", mensaje.Id);
        }

        [Fact]
        public void AceptaDarPermiso()
        {
            var mensaje = Puente.Validar("{\"tipo\":\"dar_permiso\",\"id\":\"b2\",\"ruta\":\"D:\\\\Cortes\\\\2026\"}", Origen, Servidor, true, true);
            Assert.NotNull(mensaje);
            Assert.Equal(TipoMensaje.DarPermiso, mensaje.Tipo);
            Assert.Equal("D:\\Cortes\\2026", mensaje.Ruta);
        }

        [Theory]
        [InlineData("{\"tipo\":\"elegir_carpeta\",\"id\":\"a1\"}", "https://otro/", true, true)]
        [InlineData("{\"tipo\":\"elegir_carpeta\",\"id\":\"a1\"}", "http://servidor/", true, true)]
        [InlineData("{\"tipo\":\"elegir_carpeta\",\"id\":\"a1\"}", "https://servidor:8443/", true, true)]
        [InlineData("{\"tipo\":\"elegir_carpeta\",\"id\":\"a1\"}", Origen, false, true)]
        [InlineData("{\"tipo\":\"elegir_carpeta\",\"id\":\"a1\"}", Origen, true, false)]
        [InlineData("{\"tipo\":\"elegir_carpeta\",\"id\":\"a1\",\"extra\":\"x\"}", Origen, true, true)]
        [InlineData("{\"tipo\":\"ejecutar\",\"id\":\"a1\"}", Origen, true, true)]
        [InlineData("{\"tipo\":\"elegir_carpeta\",\"id\":\"a-1\"}", Origen, true, true)]
        [InlineData("{\"tipo\":\"elegir_carpeta\",\"id\":\"\"}", Origen, true, true)]
        [InlineData("{\"tipo\":\"elegir_carpeta\"}", Origen, true, true)]
        [InlineData("{\"tipo\":\"elegir_carpeta\",\"id\":1}", Origen, true, true)]
        [InlineData("\"elegir_carpeta\"", Origen, true, true)]
        [InlineData("{\"tipo\":\"dar_permiso\",\"id\":\"a1\"}", Origen, true, true)]
        [InlineData("{\"tipo\":\"dar_permiso\",\"id\":\"a1\",\"ruta\":\"C:\\\\\"}", Origen, true, true)]
        [InlineData("{\"tipo\":\"dar_permiso\",\"id\":\"a1\",\"ruta\":\"\\\\\\\\servidor\\\\c$\"}", Origen, true, true)]
        [InlineData("{\"tipo\":\"dar_permiso\",\"id\":\"a1\",\"ruta\":\"C:\\\\a\\\\..\\\\Windows\"}", Origen, true, true)]
        [InlineData("{\"tipo\":\"dar_permiso\",\"id\":\"a1\",\"ruta\":\"C:\\\\a\\\" -x \\\"b\"}", Origen, true, true)]
        [InlineData("{\"tipo\":\"dar_permiso\",\"id\":\"a1\",\"ruta\":\"C:\\\\a\",\"ruta2\":\"x\"}", Origen, true, true)]
        [InlineData(null, Origen, true, true)]
        public void DescartaLoDemas(string json, string origen, bool principal, bool verificado)
        {
            Assert.Null(Puente.Validar(json, origen, Servidor, principal, verificado));
        }

        [Fact]
        public void DescartaMensajesLargos()
        {
            string json = "{\"tipo\":\"elegir_carpeta\",\"id\":\"a1\"" + new string(' ', Puente.LargoMaximo) + "}";
            Assert.Null(Puente.Validar(json, Origen, Servidor, true, true));
        }

        [Fact]
        public void LasRespuestasSoloLlevanLaRuta()
        {
            Assert.Equal("{\"id\":\"a1\",\"ruta\":\"C:\\\\Datos\"}", Puente.RespuestaCarpeta("a1", "C:\\Datos"));
            Assert.Equal("{\"id\":\"a1\",\"ruta\":\"\"}", Puente.RespuestaCarpeta("a1", null));
            Assert.Equal("{\"id\":\"a1\",\"ruta\":\"C:\\\\\\u003cx\\u003e\"}", Puente.RespuestaCarpeta("a1", "C:\\<x>"));
            Assert.Equal("{\"id\":\"a1\"}", Puente.RespuestaPermiso("a1"));
        }
    }

    public class PruebasRutas
    {
        [Theory]
        [InlineData("C:\\Cortes")]
        [InlineData("d:\\Respaldos\\Ariasmos 2026")]
        [InlineData("E:\\Banco\\Descargas\\Estados de cuenta")]
        [InlineData("C:\\Users\\Caja\\OneDrive\\Cortes")]
        public void AceptaCarpetasLocales(string ruta)
        {
            Assert.True(Rutas.EsCarpetaLocal(ruta));
        }

        [Theory]
        [InlineData("C:\\")]
        [InlineData("C:")]
        [InlineData("C:Cortes")]
        [InlineData("\\\\servidor\\compartida")]
        [InlineData("\\\\?\\C:\\Cortes")]
        [InlineData("\\\\.\\PhysicalDrive0")]
        [InlineData("C:\\Cortes\\")]
        [InlineData("C:\\Cortes\\\\Otro")]
        [InlineData("C:\\Cortes\\..\\Windows")]
        [InlineData("C:\\Cortes\\.")]
        [InlineData("C:\\Cortes\\a\"b")]
        [InlineData("C:\\Cortes\\a|b")]
        [InlineData("C:\\Cortes\\a*")]
        [InlineData("C:\\Cortes\\a?")]
        [InlineData("C:\\Cortes\\a:flujo")]
        [InlineData("C:\\Cortes/otra")]
        [InlineData("C:\\PROGRA~1\\Ariasmos")]
        [InlineData("C:\\Cortes\\CON")]
        [InlineData("C:\\Cortes\\nul.txt")]
        [InlineData("C:\\Cortes\\COM1")]
        [InlineData("C:\\Cortes\\punto.")]
        [InlineData("C:\\Cortes\\espacio ")]
        [InlineData("C:\\Cortes\\\tTab")]
        [InlineData("1:\\Cortes")]
        [InlineData("")]
        [InlineData(null)]
        public void RechazaRutasPeligrosas(string ruta)
        {
            Assert.False(Rutas.EsCarpetaLocal(ruta));
        }

        [Fact]
        public void RechazaRutasLargas()
        {
            Assert.False(Rutas.EsCarpetaLocal("C:\\" + new string('a', Rutas.LargoMaximo)));
        }
    }

    public class PruebasVentana
    {
        [Fact]
        public void LeeYEscribeElEstado()
        {
            var estado = EstadoVentana.Leer("10,-20,1280,800,1");
            Assert.NotNull(estado);
            Assert.Equal(-20, estado.Y);
            Assert.True(estado.Maximizada);
            Assert.Equal("10,-20,1280,800,1", estado.Escribir());
        }

        [Theory]
        [InlineData("")]
        [InlineData("1,2,3")]
        [InlineData("0,0,100,100,0")]
        [InlineData("0,0,1280,800,2")]
        [InlineData("0,0,99999,800,0")]
        [InlineData("a,0,1280,800,0")]
        public void RechazaEstadosRaros(string texto)
        {
            Assert.Null(EstadoVentana.Leer(texto));
        }

        [Fact]
        public void ElAgenteLlevaLaVersion()
        {
            Assert.Equal("Ariasmos/0.9.0 principal", Agente.Sufijo("0.9.0", true));
            Assert.Equal("Ariasmos/0.9.0 adicional", Agente.Sufijo("0.9.0", false));
            Assert.True(Agente.VersionValida("0.9.0"));
            Assert.False(Agente.VersionValida("0.9"));
        }
    }

    public class PruebasJson
    {
        [Fact]
        public void EscapaTextos()
        {
            Assert.Equal("\"a\\\"b\\\\c\\n\\u0001\"", Json.Texto("a\"b\\c\n\u0001"));
        }

        [Theory]
        [InlineData("{\"a\":1,}")]
        [InlineData("{\"a\":01}")]
        [InlineData("{\"a\":\"\\x\"}")]
        [InlineData("{\"a\":\"\u0001\"}")]
        [InlineData("{a:1}")]
        [InlineData("{\"a\":1}{")]
        [InlineData("{\"a\":tru}")]
        public void RechazaJsonInvalido(string texto)
        {
            Assert.Throws<ErrorFormato>(() => Json.Analizar(texto));
        }

        [Fact]
        public void RechazaDemasiadosNiveles()
        {
            Assert.Throws<ErrorFormato>(() => Json.Analizar(new string('[', 40) + new string(']', 40)));
        }
    }
}
