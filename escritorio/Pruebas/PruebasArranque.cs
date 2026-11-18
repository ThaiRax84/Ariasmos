using System;
using Ariasmos.Nucleo;
using Xunit;

namespace Ariasmos.Pruebas
{
    public class PruebasArranque
    {
        private static TimeSpan Ms(int milisegundos)
        {
            return TimeSpan.FromMilliseconds(milisegundos);
        }

        [Fact]
        public void MientrasCargaNoMuestraLaVentanaYEsperaHastaElMaximo()
        {
            var paso = Arranque.Decidir(EstadoArranque.Cargando, Ms(500), false, false);
            Assert.Equal(AccionArranque.Esperar, paso.Accion);
            Assert.Equal(Arranque.MaximoSplash - Ms(500), paso.Espera);
        }

        [Fact]
        public void ListaAntesDelMinimoEsperaLoQueFalta()
        {
            var paso = Arranque.Decidir(EstadoArranque.Lista, Ms(200), false, false);
            Assert.Equal(AccionArranque.Esperar, paso.Accion);
            Assert.Equal(Ms(1000), paso.Espera);
        }

        [Fact]
        public void ListaDespuesDelMinimoMuestraEnSeguida()
        {
            Assert.Equal(AccionArranque.Mostrar, Arranque.Decidir(EstadoArranque.Lista, Ms(1200), false, false).Accion);
            Assert.Equal(AccionArranque.Mostrar, Arranque.Decidir(EstadoArranque.Lista, Ms(5000), false, false).Accion);
        }

        [Fact]
        public void ErrorTambienRespetaElMinimoYLuegoMuestraLaVentana()
        {
            Assert.Equal(AccionArranque.Esperar, Arranque.Decidir(EstadoArranque.Error, Ms(100), false, false).Accion);
            Assert.Equal(AccionArranque.Mostrar, Arranque.Decidir(EstadoArranque.Error, Ms(1300), false, false).Accion);
        }

        [Fact]
        public void SiLaCargaTardaDemasiadoMuestraLaVentanaConSuAviso()
        {
            Assert.Equal(AccionArranque.Mostrar, Arranque.Decidir(EstadoArranque.Cargando, Arranque.MaximoSplash, false, false).Accion);
        }

        [Fact]
        public void TiempoNegativoCuentaComoCero()
        {
            var paso = Arranque.Decidir(EstadoArranque.Lista, Ms(-50), false, false);
            Assert.Equal(AccionArranque.Esperar, paso.Accion);
            Assert.Equal(Arranque.MinimoSplash, paso.Espera);
        }

        [Fact]
        public void ConLaVentanaVisibleNoHaceNada()
        {
            foreach (EstadoArranque estado in Enum.GetValues(typeof(EstadoArranque)))
            {
                Assert.Equal(AccionArranque.Nada, Arranque.Decidir(estado, Ms(0), false, true).Accion);
                Assert.Equal(AccionArranque.Nada, Arranque.Decidir(estado, Ms(60000), false, true).Accion);
            }
        }

        [Fact]
        public void AlVerificarNuncaMuestraLaVentana()
        {
            foreach (EstadoArranque estado in Enum.GetValues(typeof(EstadoArranque)))
            {
                Assert.Equal(AccionArranque.Nada, Arranque.Decidir(estado, Ms(0), true, false).Accion);
                Assert.Equal(AccionArranque.Nada, Arranque.Decidir(estado, Ms(60000), true, false).Accion);
            }
        }

        [Fact]
        public void ElMinimoEsBreveYMenorQueElMaximo()
        {
            Assert.InRange(Arranque.MinimoSplash.TotalMilliseconds, 800, 1500);
            Assert.True(Arranque.MinimoSplash < Arranque.MaximoSplash);
        }

        [Fact]
        public void OtraInstanciaDuranteElSplashTraeElSplashYNoLaVentana()
        {
            Assert.Equal(Frente.Splash, Arranque.AlPedirFrente(false, true));
        }

        [Fact]
        public void OtraInstanciaConLaVentanaVisibleTraeLaVentana()
        {
            Assert.Equal(Frente.Ventana, Arranque.AlPedirFrente(true, true));
            Assert.Equal(Frente.Ventana, Arranque.AlPedirFrente(true, false));
        }

        [Fact]
        public void OtraInstanciaSinNadaVisibleNoMuestraNada()
        {
            Assert.Equal(Frente.Nada, Arranque.AlPedirFrente(false, false));
        }

        [Fact]
        public void CerrarElSplashAntesDeTiempoCierraElPrograma()
        {
            Assert.True(Arranque.CerrarAlCancelarSplash(false));
            Assert.False(Arranque.CerrarAlCancelarSplash(true));
        }
    }
}
