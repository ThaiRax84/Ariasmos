param(
    [Parameter(Mandatory = $true)][string]$Programa,
    [Parameter(Mandatory = $true)][string]$Datos,
    [Parameter(Mandatory = $true)][ValidateSet('nueva', 'actualizar', 'restaurada')][string]$Modo
)

. (Join-Path $PSScriptRoot 'comun.ps1')

$R = Rutas -Programa $Programa -Datos $Datos
try {
    Iniciar-Registro -Ruta (Join-Path $R.Registros 'instalacion.log')
    Proteger-Datos -R $R
    Escribir-Registro "Modo: $Modo · versión $((Get-Content -LiteralPath (Join-Path $Programa 'app\VERSION') -Raw).Trim())"
    Proteger-Programa -R $R
    if (-not (Test-Path -LiteralPath $R.Python)) { throw "Falta $($R.Python): la copia del programa está incompleta." }
    $nombre = Nombre-Equipo
    Escribir-Registro "Nombre del equipo para HTTPS: $nombre"
    $salida = Manage -R $R -Argumentos @('inicializar', '--host', $nombre, '--certificado-servidor', $R.Certificado) -Descripcion 'Preparando la instancia' -Silencioso
    $token = ''
    foreach ($renglon in $salida) {
        if ($renglon -match '^Token del asistente: (\S+)$') {
            $token = $Matches[1]
        }
        else {
            Escribir-Registro "    $renglon"
        }
    }
    Comprobar-Privado -Ruta $R.Instancia
    Manage -R $R -Argumentos @('migrate', '--noinput') -Descripcion 'Actualizando la base de datos' | Out-Null
    Manage -R $R -Argumentos @('check') -Descripcion 'Comprobando la instalación' | Out-Null
    Limpiar-Autoridad-Anterior -R $R
    Preparar-Certificado -R $R -Nombre $nombre
    $argumentosCaddy = @('generar_config_caddy', '--nombre', $nombre, '--cert', $R.CertServidor, '--clave', $R.ClaveServidor, '--salida', $R.CaddyConfig)
    if (Puerto-Ocupado -Puerto 80) {
        Escribir-Registro 'El puerto 80 está ocupado por otro programa: no habrá redirección de HTTP a HTTPS.'
        $argumentosCaddy += '--sin-redireccion'
    }
    Manage -R $R -Argumentos $argumentosCaddy -Descripcion 'Escribiendo la configuración del servicio TLS' | Out-Null
    if (Puerto-Ocupado -Puerto 443) {
        $servicioTls = Get-Service -Name 'AriasmosTLS' -ErrorAction SilentlyContinue
        if ($null -eq $servicioTls -or $servicioTls.Status -ne 'Running') {
            throw 'El puerto 443 está ocupado por otro programa. Ciérralo o desinstálalo y vuelve a ejecutar el instalador.'
        }
    }
    Instalar-Servicios -R $R
    Instalar-Firewall
    Iniciar-Servicios -R $R
    Esperar-Aplicacion | Out-Null
    Escribir-Registro 'Instalación terminada'
    if ($token -and $Modo -eq 'nueva') {
        [Console]::Out.WriteLine("TOKEN-ASISTENTE: $token")
    }
    exit 0
}
catch {
    Escribir-Registro "ERROR: $($_.Exception.Message)"
    [Console]::Out.WriteLine("ERROR-INSTALACION: $($_.Exception.Message)")
    exit 1
}
