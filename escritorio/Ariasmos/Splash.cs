using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Text;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Windows.Forms;

namespace Ariasmos
{
    internal static class Recursos
    {
        private static readonly PrivateFontCollection Cinzel = Cargar("Ariasmos.cinzel.ttf");
        private static readonly PrivateFontCollection Nunito = Cargar("Ariasmos.nunito.ttf");

        public static Font Marca(float pixeles)
        {
            return Crear(Cinzel, "Georgia", pixeles, FontStyle.Bold);
        }

        public static Font Texto(float pixeles)
        {
            return Crear(Nunito, "Segoe UI", pixeles, FontStyle.Regular);
        }

        public static Image Escena()
        {
            using (var flujo = Assembly.GetExecutingAssembly().GetManifestResourceStream("Ariasmos.escena-vasija.jpg"))
            {
                if (flujo == null)
                {
                    return null;
                }
                using (var imagen = Image.FromStream(flujo))
                {
                    return new Bitmap(imagen);
                }
            }
        }

        private static Font Crear(PrivateFontCollection coleccion, string reserva, float pixeles, FontStyle preferido)
        {
            if (coleccion != null && coleccion.Families.Length > 0)
            {
                var familia = coleccion.Families[0];
                foreach (var estilo in new[] { preferido, FontStyle.Regular, FontStyle.Bold })
                {
                    if (familia.IsStyleAvailable(estilo))
                    {
                        return new Font(familia, pixeles, estilo, GraphicsUnit.Pixel);
                    }
                }
            }
            return new Font(reserva, pixeles, preferido, GraphicsUnit.Pixel);
        }

        private static PrivateFontCollection Cargar(string nombre)
        {
            try
            {
                using (var flujo = Assembly.GetExecutingAssembly().GetManifestResourceStream(nombre))
                {
                    if (flujo == null)
                    {
                        return null;
                    }
                    var datos = new byte[flujo.Length];
                    int leidos = 0;
                    while (leidos < datos.Length)
                    {
                        int n = flujo.Read(datos, leidos, datos.Length - leidos);
                        if (n <= 0)
                        {
                            break;
                        }
                        leidos += n;
                    }
                    IntPtr memoria = Marshal.AllocCoTaskMem(datos.Length);
                    Marshal.Copy(datos, 0, memoria, datos.Length);
                    var coleccion = new PrivateFontCollection();
                    coleccion.AddMemoryFont(memoria, datos.Length);
                    return coleccion;
                }
            }
            catch (Exception error) when (error is IOException || error is ArgumentException || error is ExternalException)
            {
                Registro.Escribir("No se pudo cargar la letra " + nombre + ": " + error.Message);
                return null;
            }
        }
    }

    internal sealed class Splash : Form
    {
        private const float AnchoEscena = 1280f;
        private const float AltoEscena = 800f;
        private static readonly Color Fondo = Color.FromArgb(0x14, 0x10, 0x0D);
        private static readonly Color Terracota = Color.FromArgb(0xC4, 0x66, 0x2E);
        private static readonly Color ColorNombre = Color.FromArgb(0xD9, 0x81, 0x3F);
        private static readonly Color ColorTexto = Color.FromArgb(0xD9, 0xC7, 0xA6);
        private static readonly Color ColorVersion = Color.FromArgb(0xA8, 0x97, 0x7D);
        private static readonly PointF[] Meandro =
        {
            new PointF(0, 30), new PointF(42, 30), new PointF(42, 6), new PointF(12, 6), new PointF(12, 20), new PointF(30, 20), new PointF(30, 14),
        };

        private readonly string version;
        private readonly Image escena;
        private readonly Font letraMarca;
        private readonly Font letraTexto;
        private readonly Font letraVersion;
        private readonly Timer desvanecer;

        public Splash(string version)
        {
            this.version = version;
            escena = Recursos.Escena();
            letraMarca = Recursos.Marca(112f);
            letraTexto = Recursos.Texto(17f);
            letraVersion = Recursos.Texto(20f);
            float escala;
            using (var g = CreateGraphics())
            {
                escala = Math.Max(1f, g.DpiX / 96f);
            }
            FormBorderStyle = FormBorderStyle.None;
            StartPosition = FormStartPosition.CenterScreen;
            ClientSize = new Size((int)Math.Round(720 * escala), (int)Math.Round(450 * escala));
            BackColor = Fondo;
            ShowInTaskbar = false;
            TopMost = true;
            Text = "Ariasmos";
            DoubleBuffered = true;
            SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.UserPaint, true);
            desvanecer = new Timer { Interval = 15 };
            desvanecer.Tick += (origen, evento) =>
            {
                Opacity = Math.Max(0, Opacity - 0.07);
                if (Opacity <= 0)
                {
                    desvanecer.Stop();
                    Close();
                }
            };
        }

        public void Desvanecer()
        {
            if (!IsDisposed && !desvanecer.Enabled)
            {
                desvanecer.Start();
            }
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            var g = e.Graphics;
            g.Clear(Fondo);
            g.SmoothingMode = SmoothingMode.AntiAlias;
            g.InterpolationMode = InterpolationMode.HighQualityBicubic;
            g.PixelOffsetMode = PixelOffsetMode.HighQuality;
            g.TextRenderingHint = TextRenderingHint.AntiAliasGridFit;
            float escala = ClientSize.Width / AnchoEscena;
            g.ScaleTransform(escala, escala);

            Greca(g, 0, true);
            Greca(g, AltoEscena - 72, false);

            float alto = 375 + 8 + 112 + 8 + 4 + 8 + 6 + 23 + 8 + 27;
            float y = 72 + ((AltoEscena - 144) - alto) / 2;
            if (escena != null)
            {
                g.DrawImage(escena, new RectangleF((AnchoEscena - 760) / 2, y, 760, 375));
            }
            y += 375 + 8;
            Espaciado(g, "ARIASMOS", letraMarca, ColorNombre, y - 14, 12);
            y += 112 + 8;
            using (var pincel = new SolidBrush(Terracota))
            {
                g.FillRectangle(pincel, (AnchoEscena - 760) / 2, y, 760, 4);
            }
            y += 4 + 8 + 6;
            Centrado(g, "Iniciando el sistema…", letraTexto, ColorTexto, y);
            y += 23 + 8;
            Centrado(g, "ver. " + version, letraVersion, ColorVersion, y);
        }

        private static void Centrado(Graphics g, string texto, Font letra, Color color, float y)
        {
            using (var pincel = new SolidBrush(color))
            using (var formato = new StringFormat(StringFormat.GenericTypographic) { Alignment = StringAlignment.Center })
            {
                g.DrawString(texto, letra, pincel, new RectangleF(0, y, AnchoEscena, letra.GetHeight(g) * 1.4f), formato);
            }
        }

        private static void Espaciado(Graphics g, string texto, Font letra, Color color, float y, float separacion)
        {
            using (var pincel = new SolidBrush(color))
            using (var formato = new StringFormat(StringFormat.GenericTypographic))
            {
                formato.FormatFlags |= StringFormatFlags.MeasureTrailingSpaces;
                var anchos = new float[texto.Length];
                float total = 0;
                for (int i = 0; i < texto.Length; i++)
                {
                    anchos[i] = g.MeasureString(texto[i].ToString(), letra, PointF.Empty, formato).Width;
                    total += anchos[i] + separacion;
                }
                float x = (AnchoEscena - total) / 2 + separacion / 2;
                for (int i = 0; i < texto.Length; i++)
                {
                    g.DrawString(texto[i].ToString(), letra, pincel, x, y, formato);
                    x += anchos[i] + separacion;
                }
            }
        }

        private static void Greca(Graphics g, float y0, bool arriba)
        {
            using (var pincel = new SolidBrush(Terracota))
            using (var pluma = new Pen(Terracota, 4f) { LineJoin = LineJoin.Miter, StartCap = LineCap.Flat, EndCap = LineCap.Flat })
            {
                float banda = arriba ? 22 : 14;
                if (arriba)
                {
                    g.FillRectangle(pincel, 0, y0, AnchoEscena, 14);
                    g.FillRectangle(pincel, 0, y0 + 64, AnchoEscena, 6);
                }
                else
                {
                    g.FillRectangle(pincel, 0, y0 + 2, AnchoEscena, 6);
                    g.FillRectangle(pincel, 0, y0 + 58, AnchoEscena, 14);
                }
                var estado = g.Save();
                g.SetClip(new RectangleF(0, y0 + banda, AnchoEscena, 36));
                for (float fila = 0; fila < 72; fila += 36)
                {
                    for (float x = 0; x < AnchoEscena; x += 48)
                    {
                        var puntos = new PointF[Meandro.Length];
                        for (int i = 0; i < Meandro.Length; i++)
                        {
                            puntos[i] = new PointF(x + Meandro[i].X, y0 + fila + Meandro[i].Y);
                        }
                        g.DrawLines(pluma, puntos);
                    }
                }
                g.Restore(estado);
            }
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing)
            {
                desvanecer.Dispose();
                if (escena != null)
                {
                    escena.Dispose();
                }
                letraMarca.Dispose();
                letraTexto.Dispose();
                letraVersion.Dispose();
            }
            base.Dispose(disposing);
        }
    }
}
