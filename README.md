# Ariasmos

Sistema local y multiusuario de cobro y control de titulares: padrón con matrícula única como referencia de pago, cobro en efectivo y por banco con conciliación, inventario opcional, aprobaciones, cortes diario y mensual, bitácora sellada y respaldos cifrados. Se instala en Windows como programa con su propia ventana (`Ariasmos.exe`): una computadora principal guarda los datos y las adicionales se conectan a ella con un archivo de conexión. El repositorio no trae datos de ningún negocio.

## Guías

- [Guía de instalación](docs/GUIA-INSTALACION.md): instalar, conectar otras computadoras, clave de recuperación, actualizar y desinstalar.
- [Guía de uso](docs/GUIA-USO.md): el trabajo de cada rol.
- [Guía de inventario](docs/GUIA-INVENTARIO.md): artículos, ventas, devoluciones, entradas, mermas y conteo mensual (opcional).
- [Restaurar en un equipo nuevo](docs/RESTAURAR.md).
- [Publicar una versión](docs/GUIA-PUBLICAR-VERSION.md): llaves de firma, canal de versiones y claves de solo lectura (para el dueño del programa).
- [Referencia técnica](docs/REFERENCIA.md): cobro, caja, banco, inventario, actualizaciones, cortes, respaldos, comandos y demostración.
- [Arquitectura](docs/ARQUITECTURA.md).

## Desarrollo

Requiere Python 3.12.

```bash
python -m venv .venv
. .venv/bin/activate          # en Windows: .venv\Scripts\Activate.ps1
pip install -r requirements-pruebas.txt
cd sistema
python manage.py inicializar --sin-https
python manage.py migrate
python manage.py servir
```

`inicializar` crea la carpeta de instancia (fuera de git; otra ruta con la variable `COBRO_INSTANCIA`) con las claves de Django, matrícula, bitácora, respaldo y secretos, e imprime el **token del asistente**. En una instancia existente solo agrega lo que falte; `--host NOMBRE` (repetible) registra un nombre de equipo en `hosts` y `https://NOMBRE` en los orígenes de confianza. Nunca borres `configuracion.json` ni `ancla_auditoria.json` de una instalación con datos.

Pruebas, desde la raíz: `python -m pytest`. No necesitan instancia. Las pruebas de los scripts de PowerShell se ejecutan si `pwsh` está instalado (o la variable `PWSH` apunta a él).

### Instalador de Windows

- `escritorio/` es el programa `Ariasmos.exe` (C#, .NET Framework 4.8, WinForms y WebView2): `dotnet test escritorio/Pruebas/Ariasmos.Pruebas.csproj` y `dotnet build escritorio/Ariasmos/Ariasmos.csproj -c Release -o build/escritorio`.
- `instalacion/construir.ps1` arma `build\Ariasmos` con Python embebido, las dependencias (solo ruedas binarias, verificadas con `instalacion/requisitos-windows.txt`), WinSW y Caddy; cada descarga se verifica con el SHA-256 de `instalacion/dependencias.json`, y el instalador oficial de WebView2 con su firma Authenticode de Microsoft. Comprueba que `build\escritorio\Ariasmos.exe` sea de la misma versión.
- `instalacion/ariasmos.iss` (Inno Setup 6.3 o posterior) genera el instalador, con dos formas de instalar: computadora principal o adicional.
- `.github/workflows/instalador.yml` corre las pruebas en Linux y en Windows, compila y prueba `Ariasmos.exe`, construye el instalador y hace una prueba de humo de instalación principal, actualización, `Ariasmos.exe --verificar`, instalación adicional contra ese servidor y desinstalación.

La versión está en `VERSION` y se ve en el pie de página y con `python manage.py version`.

Con la Fase 4a cambiaron los permisos de las plantillas (Operación ya no trae «Ver cortes»); los roles de una instalación ya creada no se cambian solos.

## Licencia

Este programa es propietario: todos los derechos reservados. Consulta el archivo [`LICENSE`](LICENSE).
