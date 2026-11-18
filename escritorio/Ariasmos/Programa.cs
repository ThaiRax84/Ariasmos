using System;
using System.IO;
using System.Reflection;
using System.Threading;
using System.Windows.Forms;
using Ariasmos.Nucleo;
using Microsoft.Win32;

namespace Ariasmos
{
    internal static class Codigos
    {
        public const int Bien = 0;
        public const int Conexion = 2;
        public const int Componente = 3;
        public const int SinServidor = 4;
        public const int HuellaDistinta = 5;
        public const int SinComprobar = 6;
        public const int Navegacion = 7;
        public const int Tiempo = 8;
        public const int Inesperado = 9;
        public const int Uso = 64;
    }

    internal static class Programa
    {
        public static string Version
        {
            get
            {
                var version = Assembly.GetExecutingAssembly().GetName().Version;
                return version.Major + "." + version.Minor + "." + version.Build;
            }
        }

        public static string CarpetaUsuario
        {
            get { return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Ariasmos"); }
        }

        public static string ArchivoConexion
        {
            get { return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), "Ariasmos", "conexion.json"); }
        }

        [STAThread]
        private static int Main(string[] argumentos)
        {
            bool verificar = argumentos.Length == 1 && argumentos[0] == "--verificar";
            if (argumentos.Length != 0 && !verificar)
            {
                return Codigos.Uso;
            }
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.SetUnhandledExceptionMode(UnhandledExceptionMode.CatchException);
            Application.ThreadException += (origen, evento) => Inesperado(evento.Exception, verificar);
            Registro.Escribir("Inicio de Ariasmos " + Version + (verificar ? " (verificar)" : string.Empty));

            Mutex unica = null;
            EventWaitHandle aviso = null;
            if (!verificar)
            {
                bool nueva;
                unica = new Mutex(true, @"Local\Ariasmos.Ventana", out nueva);
                aviso = new EventWaitHandle(false, EventResetMode.AutoReset, @"Local\Ariasmos.Mostrar");
                if (!nueva)
                {
                    aviso.Set();
                    return Codigos.Bien;
                }
            }

            Conexion conexion;
            try
            {
                conexion = Nucleo.Conexion.Leer(ArchivoConexion);
            }
            catch (Exception error) when (error is ErrorFormato || error is IOException || error is UnauthorizedAccessException)
            {
                Registro.Escribir("Archivo de conexión no válido: " + error.Message);
                if (!verificar)
                {
                    MessageBox.Show(
                        "No se pudo leer el archivo de conexión de esta computadora:\n\n" + error.Message +
                        "\n\nVuelve a ejecutar el instalador de Ariasmos y elige el archivo de conexión que se genera en la computadora principal (Equipos, «Conectar otra computadora»).",
                        "Ariasmos", MessageBoxButtons.OK, MessageBoxIcon.Error);
                }
                return Codigos.Conexion;
            }

            bool principal = EsPrincipal();
            Registro.Escribir("Servidor " + conexion.Origen + (principal ? " (computadora principal)" : " (computadora adicional)"));
            int resultado;
            using (var ventana = new VentanaPrincipal(conexion, principal, verificar, aviso))
            {
                Application.Run(ventana);
                resultado = ventana.Resultado;
            }
            GC.KeepAlive(unica);
            Registro.Escribir("Fin con código " + resultado);
            return resultado;
        }

        private static bool EsPrincipal()
        {
            try
            {
                using (var raiz = RegistryKey.OpenBaseKey(RegistryHive.LocalMachine, RegistryView.Registry64))
                using (var clave = raiz.OpenSubKey(@"SOFTWARE\Ariasmos"))
                {
                    return clave != null && string.Equals(clave.GetValue("Modo") as string, "principal", StringComparison.Ordinal);
                }
            }
            catch (Exception error) when (error is System.Security.SecurityException || error is UnauthorizedAccessException || error is IOException)
            {
                return false;
            }
        }

        private static void Inesperado(Exception error, bool verificar)
        {
            Registro.Escribir("Error inesperado: " + error.GetType().Name + ": " + error.Message);
            if (verificar)
            {
                Environment.Exit(Codigos.Inesperado);
            }
            MessageBox.Show("Ocurrió un error inesperado en la ventana de Ariasmos:\n\n" + error.Message, "Ariasmos", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }

    internal static class Registro
    {
        private const long TamanoMaximo = 512 * 1024;
        private static readonly object Cerrojo = new object();

        public static void Escribir(string mensaje)
        {
            try
            {
                lock (Cerrojo)
                {
                    Directory.CreateDirectory(Programa.CarpetaUsuario);
                    string ruta = Path.Combine(Programa.CarpetaUsuario, "registro.log");
                    var info = new FileInfo(ruta);
                    if (info.Exists && info.Length > TamanoMaximo)
                    {
                        File.Copy(ruta, ruta + ".1", true);
                        File.Delete(ruta);
                    }
                    string limpio = mensaje.Replace('\r', ' ').Replace('\n', ' ');
                    if (limpio.Length > 500)
                    {
                        limpio = limpio.Substring(0, 500);
                    }
                    File.AppendAllText(ruta, DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss", System.Globalization.CultureInfo.InvariantCulture) + " " + limpio + Environment.NewLine);
                }
            }
            catch (IOException)
            {
            }
            catch (UnauthorizedAccessException)
            {
            }
        }
    }
}
