using System;
using System.ComponentModel;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;
using Ariasmos.Nucleo;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace Ariasmos
{
    internal sealed class VentanaPrincipal : Form
    {
        private static readonly Color Oscuro = Color.FromArgb(0x14, 0x10, 0x0D);
        private static readonly Color Claro = Color.FromArgb(0xF6, 0xED, 0xE3);
        private static readonly Color Terracota = Color.FromArgb(0x9E, 0x43, 0x1C);

        private readonly Conexion conexion;
        private readonly bool principal;
        private readonly bool verificar;
        private readonly EventWaitHandle aviso;
        private readonly Panel cubierta;
        private readonly Label textoCubierta;
        private readonly Button reintentar;
        private readonly System.Windows.Forms.Timer limite;
        private WebView2 vista;
        private Splash splash;
        private bool documentoVerificado;
        private bool primeraCarga = true;
        private bool limpiando;
        private bool cerrando;
        private bool recreando;
        private DateTime ultimaDescarga = DateTime.MinValue;

        public VentanaPrincipal(Conexion conexion, bool principal, bool verificar, EventWaitHandle aviso)
        {
            this.conexion = conexion;
            this.principal = principal;
            this.verificar = verificar;
            this.aviso = aviso;
            Resultado = Codigos.Inesperado;
            Text = "Ariasmos";
            try
            {
                Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
            }
            catch (ArgumentException)
            {
            }
            BackColor = Oscuro;
            MinimumSize = new Size(EstadoVentana.AnchoMinimo, EstadoVentana.AltoMinimo);
            StartPosition = FormStartPosition.Manual;
            KeyPreview = false;
            RestaurarEstado();

            cubierta = new Panel { Dock = DockStyle.Fill, BackColor = Oscuro };
            textoCubierta = new Label
            {
                AutoSize = false,
                ForeColor = Claro,
                Font = new Font("Segoe UI", 12f),
                TextAlign = ContentAlignment.MiddleCenter,
                Text = "Conectando con el servidor…",
            };
            reintentar = new Button
            {
                Text = "Reintentar",
                AutoSize = false,
                Size = new Size(180, 44),
                FlatStyle = FlatStyle.Flat,
                BackColor = Terracota,
                ForeColor = Color.White,
                Font = new Font("Segoe UI", 11f, FontStyle.Bold),
                Visible = false,
            };
            reintentar.FlatAppearance.BorderSize = 0;
            reintentar.Click += (origen, evento) => Reintentar();
            cubierta.Controls.Add(textoCubierta);
            cubierta.Controls.Add(reintentar);
            cubierta.Resize += (origen, evento) => AcomodarCubierta();
            Controls.Add(cubierta);
            CrearVista();

            limite = new System.Windows.Forms.Timer { Interval = 120000 };
            limite.Tick += (origen, evento) =>
            {
                limite.Stop();
                if (primeraCarga)
                {
                    Fallar(Codigos.Tiempo, "El sistema no terminó de abrir a tiempo.", true);
                }
            };
        }

        public int Resultado { get; private set; }

        private void CrearVista()
        {
            vista = new WebView2 { Dock = DockStyle.Fill, DefaultBackgroundColor = Claro };
            Controls.Add(vista);
            cubierta.BringToFront();
        }

        protected override void OnLoad(EventArgs e)
        {
            base.OnLoad(e);
            splash = new Splash(Programa.Version);
            splash.Show();
            splash.Refresh();
            if (aviso != null)
            {
                var hilo = new Thread(EsperarAviso) { IsBackground = true, Name = "Ariasmos.Mostrar" };
                hilo.Start();
            }
        }

        protected override async void OnShown(EventArgs e)
        {
            base.OnShown(e);
            if (verificar)
            {
                limite.Start();
            }
            await IniciarAsync();
        }

        private void EsperarAviso()
        {
            while (true)
            {
                try
                {
                    aviso.WaitOne();
                }
                catch (ObjectDisposedException)
                {
                    return;
                }
                if (cerrando || IsDisposed)
                {
                    return;
                }
                try
                {
                    BeginInvoke(new Action(TraerAlFrente));
                }
                catch (InvalidOperationException)
                {
                    return;
                }
            }
        }

        private void TraerAlFrente()
        {
            if (WindowState == FormWindowState.Minimized)
            {
                WindowState = FormWindowState.Normal;
            }
            Activate();
            BringToFront();
        }

        private async Task IniciarAsync()
        {
            string disponible = null;
            try
            {
                disponible = CoreWebView2Environment.GetAvailableBrowserVersionString();
            }
            catch (WebView2RuntimeNotFoundException)
            {
            }
            if (string.IsNullOrEmpty(disponible))
            {
                Fallar(Codigos.Componente, "Falta el componente WebView2 de Microsoft, que la ventana de Ariasmos necesita. Vuelve a ejecutar el instalador de Ariasmos para instalarlo.", false);
                return;
            }
            try
            {
                var opciones = new CoreWebView2EnvironmentOptions
                {
                    Language = "es-MX",
                    AllowSingleSignOnUsingOSPrimaryAccount = false,
                };
                var entorno = await CoreWebView2Environment.CreateAsync(null, Path.Combine(Programa.CarpetaUsuario, "WebView2"), opciones);
                await vista.EnsureCoreWebView2Async(entorno);
                Configurar(vista.CoreWebView2);
            }
            catch (Exception error) when (error is WebView2RuntimeNotFoundException || error is COMException || error is InvalidOperationException || error is ArgumentException || error is UnauthorizedAccessException)
            {
                Registro.Escribir("No se pudo iniciar WebView2: " + error.GetType().Name + ": " + error.Message);
                Fallar(Codigos.Componente, "No se pudo iniciar el componente de la ventana (WebView2): " + error.Message, false);
                return;
            }
            await ConectarAsync();
        }

        private void Configurar(CoreWebView2 nucleo)
        {
            var ajustes = nucleo.Settings;
            ajustes.AreDevToolsEnabled = false;
            ajustes.AreDefaultContextMenusEnabled = false;
            ajustes.AreBrowserAcceleratorKeysEnabled = false;
            ajustes.AreDefaultScriptDialogsEnabled = true;
            ajustes.AreHostObjectsAllowed = false;
            ajustes.IsBuiltInErrorPageEnabled = false;
            ajustes.IsGeneralAutofillEnabled = false;
            ajustes.IsPasswordAutosaveEnabled = false;
            ajustes.IsStatusBarEnabled = false;
            ajustes.IsSwipeNavigationEnabled = false;
            ajustes.IsWebMessageEnabled = principal;
            ajustes.IsZoomControlEnabled = true;
            ajustes.IsScriptEnabled = true;
            ajustes.UserAgent = ajustes.UserAgent + " " + Agente.Sufijo(Programa.Version, principal);

            nucleo.NavigationStarting += AlEmpezarNavegacion;
            nucleo.FrameNavigationStarting += AlEmpezarNavegacionDeMarco;
            nucleo.NavigationCompleted += AlTerminarNavegacion;
            nucleo.NewWindowRequested += AlPedirVentana;
            nucleo.LaunchingExternalUriScheme += (origen, evento) =>
            {
                evento.Cancel = true;
                Registro.Escribir("Protocolo externo bloqueado.");
            };
            nucleo.PermissionRequested += (origen, evento) =>
            {
                evento.State = CoreWebView2PermissionState.Deny;
            };
            nucleo.DownloadStarting += AlEmpezarDescarga;
            nucleo.ProcessFailed += AlFallarProceso;
            nucleo.ServerCertificateErrorDetected += AlDetectarErrorDeCertificado;
            nucleo.WebMessageReceived += AlRecibirMensaje;
            nucleo.WindowCloseRequested += (origen, evento) => Registro.Escribir("La página pidió cerrar la ventana; se ignora.");
        }

        private async Task ConectarAsync()
        {
            documentoVerificado = false;
            MostrarCubierta("Conectando con el servidor…", false);
            var resultado = await Task.Run(() => Identidad.Comprobar(conexion));
            if (resultado == ResultadoIdentidad.SinRespuesta)
            {
                Fallar(Codigos.SinServidor, "No se pudo conectar con el servidor (" + conexion.Direccion + ", puerto " + conexion.Puerto + "). Revisa que la computadora principal esté encendida y en la misma red.", true);
                return;
            }
            if (resultado == ResultadoIdentidad.Distinta)
            {
                Fallar(Codigos.HuellaDistinta, "El servidor respondió con un certificado distinto al del archivo de conexión y no se conectó. Si el certificado de la computadora principal cambió, genera allá un archivo de conexión nuevo y vuelve a ejecutar el instalador en esta computadora.", true);
                return;
            }
            if (vista.CoreWebView2 == null)
            {
                return;
            }
            vista.CoreWebView2.Navigate(conexion.Inicio.AbsoluteUri);
        }

        private void AlEmpezarNavegacion(object origen, CoreWebView2NavigationStartingEventArgs evento)
        {
            if (limpiando && evento.Uri == "about:blank")
            {
                limpiando = false;
                return;
            }
            if (!Direcciones.Permitida(evento.Uri, conexion))
            {
                evento.Cancel = true;
                Registro.Escribir("Navegación bloqueada hacia " + Recortar(evento.Uri));
                return;
            }
            documentoVerificado = false;
        }

        private void AlEmpezarNavegacionDeMarco(object origen, CoreWebView2NavigationStartingEventArgs evento)
        {
            if (!Direcciones.Permitida(evento.Uri, conexion))
            {
                evento.Cancel = true;
                Registro.Escribir("Marco bloqueado hacia " + Recortar(evento.Uri));
            }
        }

        private async void AlTerminarNavegacion(object origen, CoreWebView2NavigationCompletedEventArgs evento)
        {
            var nucleo = vista.CoreWebView2;
            if (nucleo == null || cerrando)
            {
                return;
            }
            if (nucleo.Source == "about:blank")
            {
                return;
            }
            if (!evento.IsSuccess)
            {
                bool cancelada = evento.WebErrorStatus == CoreWebView2WebErrorStatus.OperationCanceled;
                bool descarga = (DateTime.UtcNow - ultimaDescarga) < TimeSpan.FromSeconds(30);
                if (!primeraCarga && (cancelada || descarga))
                {
                    documentoVerificado = Direcciones.Permitida(nucleo.Source, conexion) && await CertificadoCorrectoAsync(nucleo);
                    return;
                }
                Registro.Escribir("La navegación falló: " + evento.WebErrorStatus);
                Fallar(Codigos.Navegacion, "No se pudo abrir el sistema (" + evento.WebErrorStatus + "). Revisa que la computadora principal esté encendida y en la misma red.", true);
                return;
            }
            if (!Direcciones.Permitida(nucleo.Source, conexion) || !await CertificadoCorrectoAsync(nucleo))
            {
                Fallar(Codigos.SinComprobar, "No se pudo comprobar la identidad del servidor. Por seguridad, la ventana no muestra el sistema.", true);
                return;
            }
            documentoVerificado = true;
            OcultarCubierta();
            if (primeraCarga)
            {
                primeraCarga = false;
                Resultado = Codigos.Bien;
                limite.Stop();
                CerrarSplash();
                Registro.Escribir("Primera pantalla cargada y huella comprobada.");
                if (verificar)
                {
                    Close();
                }
            }
        }

        private async Task<bool> CertificadoCorrectoAsync(CoreWebView2 nucleo)
        {
            try
            {
                await nucleo.CallDevToolsProtocolMethodAsync("Network.enable", "{}");
                string respuesta = await nucleo.CallDevToolsProtocolMethodAsync("Network.getCertificate", "{\"origin\":" + Json.Texto(conexion.Origen) + "}");
                bool correcto = Huella.CoincideCdp(respuesta, conexion.Huella);
                if (!correcto)
                {
                    Registro.Escribir("El certificado de la página no coincide con la huella o no se pudo leer.");
                }
                return correcto;
            }
            catch (Exception error) when (error is COMException || error is ArgumentException || error is InvalidOperationException)
            {
                Registro.Escribir("No se pudo leer el certificado de la página: " + error.Message);
                return false;
            }
        }

        private void AlDetectarErrorDeCertificado(object origen, CoreWebView2ServerCertificateErrorDetectedEventArgs evento)
        {
            bool aceptar = false;
            try
            {
                if (Direcciones.Permitida(evento.RequestUri, conexion))
                {
                    aceptar = Huella.Coincide(Huella.DerDePem(evento.ServerCertificate.ToPemEncoding()), conexion.Huella);
                }
            }
            catch (Exception error) when (error is ErrorFormato || error is COMException || error is ArgumentException)
            {
                Registro.Escribir("Certificado ilegible: " + error.Message);
            }
            if (aceptar)
            {
                evento.Action = CoreWebView2ServerCertificateErrorAction.AlwaysAllow;
            }
            else
            {
                evento.Action = CoreWebView2ServerCertificateErrorAction.Cancel;
                Registro.Escribir("Certificado rechazado para " + Recortar(evento.RequestUri) + " (" + evento.ErrorStatus + ")");
            }
        }

        private void AlPedirVentana(object origen, CoreWebView2NewWindowRequestedEventArgs evento)
        {
            evento.Handled = true;
            if (Direcciones.Permitida(evento.Uri, conexion) && vista.CoreWebView2 != null)
            {
                vista.CoreWebView2.Navigate(evento.Uri);
                return;
            }
            Registro.Escribir("Ventana nueva bloqueada hacia " + Recortar(evento.Uri));
        }

        private void AlEmpezarDescarga(object origen, CoreWebView2DownloadStartingEventArgs evento)
        {
            evento.Handled = true;
            if (!Direcciones.Permitida(evento.DownloadOperation.Uri, conexion))
            {
                evento.Cancel = true;
                Registro.Escribir("Descarga bloqueada desde " + Recortar(evento.DownloadOperation.Uri));
                return;
            }
            ultimaDescarga = DateTime.UtcNow;
            var aplazo = evento.GetDeferral();
            BeginInvoke(new Action(() =>
            {
                try
                {
                    string propuesto = evento.ResultFilePath ?? string.Empty;
                    string nombre = Path.GetFileName(propuesto);
                    string extension = Path.GetExtension(nombre);
                    using (var dialogo = new SaveFileDialog
                    {
                        Title = "Guardar como",
                        FileName = nombre,
                        OverwritePrompt = true,
                        AddExtension = true,
                        Filter = string.IsNullOrEmpty(extension) ? "Todos los archivos|*.*" : "Archivo " + extension + "|*" + extension + "|Todos los archivos|*.*",
                    })
                    {
                        string carpeta = Path.GetDirectoryName(propuesto);
                        if (!string.IsNullOrEmpty(carpeta) && Directory.Exists(carpeta))
                        {
                            dialogo.InitialDirectory = carpeta;
                        }
                        if (dialogo.ShowDialog(this) == DialogResult.OK)
                        {
                            evento.ResultFilePath = dialogo.FileName;
                        }
                        else
                        {
                            evento.Cancel = true;
                        }
                    }
                }
                catch (Exception error) when (error is ArgumentException || error is IOException || error is InvalidOperationException)
                {
                    evento.Cancel = true;
                    Registro.Escribir("Descarga cancelada: " + error.Message);
                }
                finally
                {
                    aplazo.Complete();
                }
            }));
        }

        private void AlFallarProceso(object origen, CoreWebView2ProcessFailedEventArgs evento)
        {
            Registro.Escribir("Falló un proceso del componente: " + evento.ProcessFailedKind);
            documentoVerificado = false;
            if (evento.ProcessFailedKind == CoreWebView2ProcessFailedKind.BrowserProcessExited)
            {
                BeginInvoke(new Action(async () => await RecrearAsync()));
                return;
            }
            if (evento.ProcessFailedKind == CoreWebView2ProcessFailedKind.RenderProcessExited ||
                evento.ProcessFailedKind == CoreWebView2ProcessFailedKind.RenderProcessUnresponsive)
            {
                BeginInvoke(new Action(async () =>
                {
                    MostrarCubierta("La ventana dejó de responder; se está recuperando…", false);
                    await ConectarAsync();
                }));
            }
        }

        private async Task RecrearAsync()
        {
            if (recreando || cerrando)
            {
                return;
            }
            recreando = true;
            try
            {
                MostrarCubierta("La ventana se está recuperando…", false);
                var anterior = vista;
                Controls.Remove(anterior);
                anterior.Dispose();
                CrearVista();
                await IniciarAsync();
            }
            finally
            {
                recreando = false;
            }
        }

        private async void AlRecibirMensaje(object origen, CoreWebView2WebMessageReceivedEventArgs evento)
        {
            string json;
            try
            {
                json = evento.WebMessageAsJson;
            }
            catch (ArgumentException)
            {
                json = null;
            }
            var mensaje = Puente.Validar(json, evento.Source, conexion, principal, documentoVerificado);
            if (mensaje == null)
            {
                Registro.Escribir("Mensaje de la página descartado (origen " + Recortar(evento.Source) + ").");
                return;
            }
            var nucleo = vista.CoreWebView2;
            if (mensaje.Tipo == TipoMensaje.ElegirCarpeta)
            {
                string ruta = Carpetas.Elegir(this);
                if (nucleo != null && documentoVerificado)
                {
                    nucleo.PostWebMessageAsJson(Puente.RespuestaCarpeta(mensaje.Id, ruta));
                }
                return;
            }
            await DarPermisoAsync(mensaje.Ruta);
            if (vista.CoreWebView2 != null && documentoVerificado)
            {
                vista.CoreWebView2.PostWebMessageAsJson(Puente.RespuestaPermiso(mensaje.Id));
            }
        }

        private async Task DarPermisoAsync(string ruta)
        {
            string herramienta = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "herramientas", "permiso-carpeta.ps1");
            if (!File.Exists(herramienta))
            {
                MessageBox.Show(this, "No se encontró la herramienta para dar permiso en esta computadora.", "Ariasmos", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return;
            }
            var respuesta = MessageBox.Show(this,
                "El sistema va a poder escribir en esta carpeta:\n\n" + ruta + "\n\nWindows pedirá la confirmación de un administrador. ¿Continuar?",
                "Dar permiso", MessageBoxButtons.YesNo, MessageBoxIcon.Question, MessageBoxDefaultButton.Button2);
            if (respuesta != DialogResult.Yes)
            {
                return;
            }
            var inicio = new ProcessStartInfo
            {
                FileName = Path.Combine(Environment.SystemDirectory, "WindowsPowerShell", "v1.0", "powershell.exe"),
                Arguments = "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File \"" + herramienta + "\" -Carpeta \"" + ruta + "\"",
                UseShellExecute = true,
                Verb = "runas",
                WindowStyle = ProcessWindowStyle.Hidden,
            };
            int codigo;
            try
            {
                using (var proceso = Process.Start(inicio))
                {
                    if (proceso == null)
                    {
                        return;
                    }
                    await Task.Run(() => proceso.WaitForExit());
                    codigo = proceso.ExitCode;
                }
            }
            catch (Win32Exception error)
            {
                Registro.Escribir("Dar permiso no se ejecutó: " + error.Message);
                return;
            }
            Registro.Escribir("Dar permiso terminó con código " + codigo);
            if (codigo == 0)
            {
                MessageBox.Show(this, "Listo: el sistema ya puede escribir en\n\n" + ruta + "\n\nVuelve a guardar la pantalla.", "Ariasmos", MessageBoxButtons.OK, MessageBoxIcon.Information);
            }
            else
            {
                MessageBox.Show(this, "No se dio el permiso sobre esa carpeta. Elige una carpeta propia (no del sistema ni del programa) en un disco de esta computadora.", "Ariasmos", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            }
        }

        private void Fallar(int codigo, string mensaje, bool conReintento)
        {
            Resultado = codigo;
            documentoVerificado = false;
            Registro.Escribir("Código " + codigo + ": " + mensaje);
            if (vista != null && vista.CoreWebView2 != null)
            {
                try
                {
                    vista.CoreWebView2.Stop();
                    limpiando = true;
                    vista.CoreWebView2.Navigate("about:blank");
                }
                catch (Exception error) when (error is COMException || error is InvalidOperationException)
                {
                    limpiando = false;
                }
            }
            if (verificar)
            {
                Close();
                return;
            }
            CerrarSplash();
            MostrarCubierta(mensaje, conReintento);
        }

        private async void Reintentar()
        {
            reintentar.Visible = false;
            if (vista.CoreWebView2 == null)
            {
                await RecrearAsync();
                return;
            }
            await ConectarAsync();
        }

        private void MostrarCubierta(string texto, bool conReintento)
        {
            textoCubierta.Text = texto;
            reintentar.Visible = conReintento;
            cubierta.Visible = true;
            cubierta.BringToFront();
            AcomodarCubierta();
        }

        private void OcultarCubierta()
        {
            cubierta.Visible = false;
            if (vista != null)
            {
                vista.Focus();
            }
        }

        private void AcomodarCubierta()
        {
            int ancho = Math.Min(720, Math.Max(200, cubierta.ClientSize.Width - 80));
            textoCubierta.Size = new Size(ancho, 120);
            textoCubierta.Location = new Point((cubierta.ClientSize.Width - ancho) / 2, cubierta.ClientSize.Height / 2 - 120);
            reintentar.Location = new Point((cubierta.ClientSize.Width - reintentar.Width) / 2, cubierta.ClientSize.Height / 2 + 16);
        }

        private void CerrarSplash()
        {
            if (splash != null && !splash.IsDisposed)
            {
                splash.Desvanecer();
            }
            splash = null;
        }

        protected override bool ProcessCmdKey(ref Message mensaje, Keys teclas)
        {
            if (vista != null && vista.CoreWebView2 != null)
            {
                if (teclas == (Keys.Control | Keys.Oemplus) || teclas == (Keys.Control | Keys.Add) || teclas == (Keys.Control | Keys.Shift | Keys.Oemplus))
                {
                    vista.ZoomFactor = Math.Min(3.0, vista.ZoomFactor * 1.1);
                    return true;
                }
                if (teclas == (Keys.Control | Keys.OemMinus) || teclas == (Keys.Control | Keys.Subtract))
                {
                    vista.ZoomFactor = Math.Max(0.5, vista.ZoomFactor / 1.1);
                    return true;
                }
                if (teclas == (Keys.Control | Keys.D0) || teclas == (Keys.Control | Keys.NumPad0))
                {
                    vista.ZoomFactor = 1.0;
                    return true;
                }
            }
            return base.ProcessCmdKey(ref mensaje, teclas);
        }

        private void RestaurarEstado()
        {
            EstadoVentana estado = null;
            try
            {
                string archivo = Path.Combine(Programa.CarpetaUsuario, "ventana.txt");
                if (File.Exists(archivo) && new FileInfo(archivo).Length < 200)
                {
                    estado = EstadoVentana.Leer(File.ReadAllText(archivo));
                }
            }
            catch (Exception error) when (error is IOException || error is UnauthorizedAccessException)
            {
                estado = null;
            }
            var area = Screen.PrimaryScreen.WorkingArea;
            if (estado != null)
            {
                var rectangulo = new Rectangle(estado.X, estado.Y, estado.Ancho, estado.Alto);
                foreach (var pantalla in Screen.AllScreens)
                {
                    if (pantalla.WorkingArea.IntersectsWith(rectangulo))
                    {
                        Bounds = rectangulo;
                        WindowState = estado.Maximizada ? FormWindowState.Maximized : FormWindowState.Normal;
                        return;
                    }
                }
            }
            int ancho = Math.Max(EstadoVentana.AnchoMinimo, Math.Min(1366, area.Width - 40));
            int alto = Math.Max(EstadoVentana.AltoMinimo, Math.Min(860, area.Height - 40));
            Bounds = new Rectangle(area.Left + (area.Width - ancho) / 2, area.Top + (area.Height - alto) / 2, ancho, alto);
            WindowState = area.Width < 1500 ? FormWindowState.Maximized : FormWindowState.Normal;
        }

        private void GuardarEstado()
        {
            if (verificar)
            {
                return;
            }
            try
            {
                var limites = WindowState == FormWindowState.Normal ? Bounds : RestoreBounds;
                if (limites.Width < EstadoVentana.AnchoMinimo || limites.Height < EstadoVentana.AltoMinimo)
                {
                    return;
                }
                var estado = new EstadoVentana(limites.X, limites.Y, limites.Width, limites.Height, WindowState == FormWindowState.Maximized);
                Directory.CreateDirectory(Programa.CarpetaUsuario);
                File.WriteAllText(Path.Combine(Programa.CarpetaUsuario, "ventana.txt"), estado.Escribir());
            }
            catch (Exception error) when (error is IOException || error is UnauthorizedAccessException)
            {
                Registro.Escribir("No se guardó el tamaño de la ventana: " + error.Message);
            }
        }

        protected override void OnFormClosing(FormClosingEventArgs e)
        {
            cerrando = true;
            GuardarEstado();
            limite.Stop();
            if (splash != null && !splash.IsDisposed)
            {
                splash.Close();
            }
            if (aviso != null)
            {
                aviso.Set();
            }
            base.OnFormClosing(e);
        }

        private static string Recortar(string texto)
        {
            if (string.IsNullOrEmpty(texto))
            {
                return "(vacío)";
            }
            return texto.Length > 200 ? texto.Substring(0, 200) : texto;
        }
    }
}
