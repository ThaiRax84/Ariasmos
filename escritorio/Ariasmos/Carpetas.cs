using System;
using System.Runtime.InteropServices;
using System.Windows.Forms;

namespace Ariasmos
{
    internal static class Carpetas
    {
        private const uint OpcionNoCambiarCarpeta = 0x8;
        private const uint OpcionCarpetas = 0x20;
        private const uint OpcionSoloArchivos = 0x40;
        private const uint OpcionDebeExistir = 0x800;
        private const uint OpcionNoRecientes = 0x2000000;
        private const uint RutaDeArchivo = 0x80058000;
        private const int Cancelado = unchecked((int)0x800704C7);

        public static string Elegir(IWin32Window duena)
        {
            try
            {
                return ElegirModerna(duena);
            }
            catch (Exception error) when (error is COMException || error is InvalidCastException)
            {
                Registro.Escribir("Ventana moderna de carpetas no disponible: " + error.Message);
            }
            using (var dialogo = new FolderBrowserDialog { Description = "Elige la carpeta", ShowNewFolderButton = true })
            {
                return dialogo.ShowDialog(duena) == DialogResult.OK ? dialogo.SelectedPath : null;
            }
        }

        private static string ElegirModerna(IWin32Window duena)
        {
            var dialogo = (IDialogoArchivo)new DialogoAbrir();
            try
            {
                uint opciones;
                dialogo.GetOptions(out opciones);
                dialogo.SetOptions(opciones | OpcionCarpetas | OpcionSoloArchivos | OpcionDebeExistir | OpcionNoCambiarCarpeta | OpcionNoRecientes);
                dialogo.SetTitle("Elige la carpeta");
                dialogo.SetOkButtonLabel("Elegir esta carpeta");
                int resultado = dialogo.Show(duena != null ? duena.Handle : IntPtr.Zero);
                if (resultado == Cancelado)
                {
                    return null;
                }
                if (resultado != 0)
                {
                    throw new COMException("La ventana de carpetas falló.", resultado);
                }
                IElementoShell elemento;
                dialogo.GetResult(out elemento);
                string ruta;
                elemento.GetDisplayName(RutaDeArchivo, out ruta);
                Marshal.ReleaseComObject(elemento);
                return ruta;
            }
            finally
            {
                Marshal.ReleaseComObject(dialogo);
            }
        }

        [ComImport]
        [Guid("DC1C5A9C-E88A-4dde-A5A1-60F82A20AEF7")]
        private class DialogoAbrir
        {
        }

        [ComImport]
        [Guid("42f85136-db7e-439c-85f1-e4075d135fc8")]
        [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
        private interface IDialogoArchivo
        {
            [PreserveSig]
            int Show(IntPtr padre);

            void SetFileTypes(uint cantidad, IntPtr filtros);

            void SetFileTypeIndex(uint indice);

            void GetFileTypeIndex(out uint indice);

            void Advise(IntPtr eventos, out uint galleta);

            void Unadvise(uint galleta);

            void SetOptions(uint opciones);

            void GetOptions(out uint opciones);

            void SetDefaultFolder(IElementoShell elemento);

            void SetFolder(IElementoShell elemento);

            void GetFolder(out IElementoShell elemento);

            void GetCurrentSelection(out IElementoShell elemento);

            void SetFileName([MarshalAs(UnmanagedType.LPWStr)] string nombre);

            void GetFileName([MarshalAs(UnmanagedType.LPWStr)] out string nombre);

            void SetTitle([MarshalAs(UnmanagedType.LPWStr)] string titulo);

            void SetOkButtonLabel([MarshalAs(UnmanagedType.LPWStr)] string texto);

            void SetFileNameLabel([MarshalAs(UnmanagedType.LPWStr)] string texto);

            void GetResult(out IElementoShell elemento);

            void AddPlace(IElementoShell elemento, int lugar);

            void SetDefaultExtension([MarshalAs(UnmanagedType.LPWStr)] string extension);

            void Close(int resultado);

            void SetClientGuid(ref Guid guid);

            void ClearClientData();

            void SetFilter(IntPtr filtro);
        }

        [ComImport]
        [Guid("43826D1E-E718-42EE-BC55-A1E261C37BFE")]
        [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
        private interface IElementoShell
        {
            void BindToHandler(IntPtr contexto, ref Guid manejador, ref Guid interfaz, out IntPtr resultado);

            void GetParent(out IElementoShell padre);

            void GetDisplayName(uint forma, [MarshalAs(UnmanagedType.LPWStr)] out string nombre);

            void GetAttributes(uint mascara, out uint atributos);

            void Compare(IElementoShell otro, uint indicacion, out int orden);
        }
    }
}
