using System;
using System.IO;
using System.Net.Security;
using System.Net.Sockets;
using System.Security.Authentication;
using Ariasmos.Nucleo;

namespace Ariasmos
{
    internal enum ResultadoIdentidad
    {
        Correcta,
        SinRespuesta,
        Distinta,
    }

    internal static class Identidad
    {
        private static readonly TimeSpan Espera = TimeSpan.FromSeconds(8);

        public static ResultadoIdentidad Comprobar(Conexion conexion)
        {
            byte[] recibido = null;
            try
            {
                using (var cliente = new TcpClient())
                {
                    var intento = cliente.ConnectAsync(conexion.Direccion, conexion.Puerto);
                    if (!intento.Wait(Espera) || !cliente.Connected)
                    {
                        return ResultadoIdentidad.SinRespuesta;
                    }
                    cliente.ReceiveTimeout = (int)Espera.TotalMilliseconds;
                    cliente.SendTimeout = (int)Espera.TotalMilliseconds;
                    using (var flujo = new SslStream(cliente.GetStream(), false, (origen, certificado, cadena, errores) =>
                    {
                        if (certificado != null)
                        {
                            recibido = certificado.GetRawCertData();
                        }
                        return recibido != null && Huella.Coincide(recibido, conexion.Huella);
                    }))
                    {
                        flujo.AuthenticateAsClient(conexion.Direccion, null, SslProtocols.None, false);
                    }
                }
            }
            catch (Exception error) when (error is IOException || error is SocketException || error is AuthenticationException || error is AggregateException || error is ObjectDisposedException || error is InvalidOperationException)
            {
                Registro.Escribir("Comprobación previa: " + error.GetType().Name + ": " + error.Message);
            }
            if (recibido == null)
            {
                return ResultadoIdentidad.SinRespuesta;
            }
            return Huella.Coincide(recibido, conexion.Huella) ? ResultadoIdentidad.Correcta : ResultadoIdentidad.Distinta;
        }
    }
}
