using System;

namespace Ariasmos.Nucleo
{
    public enum EstadoArranque
    {
        Cargando,
        Lista,
        Error,
    }

    public enum AccionArranque
    {
        Nada,
        Esperar,
        Mostrar,
    }

    public enum Frente
    {
        Nada,
        Ventana,
        Splash,
    }

    public struct PasoArranque
    {
        public PasoArranque(AccionArranque accion, TimeSpan espera)
        {
            Accion = accion;
            Espera = espera;
        }

        public AccionArranque Accion { get; private set; }

        public TimeSpan Espera { get; private set; }
    }

    public static class Arranque
    {
        public static readonly TimeSpan MinimoSplash = TimeSpan.FromMilliseconds(1200);
        public static readonly TimeSpan MaximoSplash = TimeSpan.FromSeconds(30);

        public static PasoArranque Decidir(EstadoArranque estado, TimeSpan transcurrido, bool verificar, bool ventanaVisible)
        {
            if (ventanaVisible || verificar)
            {
                return new PasoArranque(AccionArranque.Nada, TimeSpan.Zero);
            }
            if (transcurrido < TimeSpan.Zero)
            {
                transcurrido = TimeSpan.Zero;
            }
            TimeSpan limite = estado == EstadoArranque.Cargando ? MaximoSplash : MinimoSplash;
            if (transcurrido >= limite)
            {
                return new PasoArranque(AccionArranque.Mostrar, TimeSpan.Zero);
            }
            return new PasoArranque(AccionArranque.Esperar, limite - transcurrido);
        }

        public static Frente AlPedirFrente(bool ventanaVisible, bool splashAbierto)
        {
            if (ventanaVisible)
            {
                return Frente.Ventana;
            }
            return splashAbierto ? Frente.Splash : Frente.Nada;
        }

        public static bool CerrarAlCancelarSplash(bool ventanaVisible)
        {
            return !ventanaVisible;
        }
    }
}
