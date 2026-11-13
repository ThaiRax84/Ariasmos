Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$script:SidAdministradores = 'S-1-5-32-544'
$script:SidSistema = 'S-1-5-18'
$script:SidServicio = 'S-1-5-19'
$script:SidUsuarios = 'S-1-5-32-545'
$script:Servicios = @('AriasmosWeb', 'AriasmosTrabajador', 'AriasmosTLS')
$script:ReglaFirewall = 'Ariasmos-HTTPS'
$script:Registro = $null

function Iniciar-Registro {
    param([Parameter(Mandatory = $true)][string]$Ruta)
    $carpeta = Split-Path -Parent $Ruta
    if (-not (Test-Path -LiteralPath $carpeta)) {
        New-Item -ItemType Directory -Path $carpeta -Force | Out-Null
    }
    $script:Registro = $Ruta
    Escribir-Registro ('---- {0} ----' -f (Split-Path -Leaf $MyInvocation.PSCommandPath))
}

function Escribir-Registro {
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Mensaje)
    $linea = '{0:yyyy-MM-dd HH:mm:ss} {1}' -f (Get-Date), $Mensaje
    if ($script:Registro) {
        Add-Content -LiteralPath $script:Registro -Value $linea -Encoding UTF8
    }
    Write-Host $linea
}

function Ejecutar {
    param(
        [Parameter(Mandatory = $true)][string]$Archivo,
        [string[]]$Argumentos = @(),
        [string]$Descripcion = '',
        [switch]$Silencioso,
        [int[]]$CodigosValidos = @(0)
    )
    if ($Descripcion) { Escribir-Registro $Descripcion }
    $anterior = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $salida = & $Archivo @Argumentos 2>&1 | ForEach-Object { "$_" }
        $codigo = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $anterior
    }
    if ($null -eq $salida) { $salida = @() }
    if (-not $Silencioso) {
        foreach ($renglon in $salida) { Escribir-Registro "    $renglon" }
    }
    if ($CodigosValidos -notcontains $codigo) {
        throw ('Falló: {0} {1} (código {2})' -f (Split-Path -Leaf $Archivo), ($Argumentos -join ' '), $codigo)
    }
    return , @($salida)
}

function Nombre-Equipo {
    $nombre = ($env:COMPUTERNAME -replace '[^A-Za-z0-9-]', '').Trim('-').ToLowerInvariant()
    $nombre = $nombre -replace '-{2,}', '-'
    if ($nombre.Length -gt 63) { $nombre = $nombre.Substring(0, 63).Trim('-') }
    if (-not $nombre) { $nombre = 'localhost' }
    return $nombre
}

function Rutas {
    param([Parameter(Mandatory = $true)][string]$Programa, [Parameter(Mandatory = $true)][string]$Datos)
    return [pscustomobject]@{
        Programa    = $Programa
        Datos       = $Datos
        Python      = Join-Path $Programa 'python\python.exe'
        Manage      = Join-Path $Programa 'app\sistema\manage.py'
        Servicios   = Join-Path $Programa 'servicios'
        Instancia   = Join-Path $Datos 'instancia'
        Registros   = Join-Path $Datos 'registros'
        Caddy       = Join-Path $Datos 'caddy'
        CaddyConfig = Join-Path $Datos 'caddy\caddy.json'
        CaddyDatos  = Join-Path $Datos 'caddy\datos'
        CertServidor = Join-Path $Datos 'caddy\servidor.crt'
        ClaveServidor = Join-Path $Datos 'caddy\servidor.key'
        Certificado = Join-Path $Datos 'certificado\ariasmos-servidor.crt'
        Copias      = Join-Path $Datos 'antes-de-actualizar'
    }
}

function Manage {
    param(
        [Parameter(Mandatory = $true)]$R,
        [Parameter(Mandatory = $true)][string[]]$Argumentos,
        [string]$Descripcion = '',
        [switch]$Silencioso
    )
    $env:COBRO_INSTANCIA = $R.Instancia
    $env:PYTHONUTF8 = '1'
    return Ejecutar -Archivo $R.Python -Argumentos (@('-X', 'utf8', '-B', $R.Manage) + $Argumentos) -Descripcion $Descripcion -Silencioso:$Silencioso
}

function Proteger-Datos {
    param([Parameter(Mandatory = $true)]$R)
    foreach ($carpeta in @($R.Datos, $R.Instancia, $R.Registros, $R.Caddy, $R.CaddyDatos, (Split-Path -Parent $R.Certificado), $R.Copias)) {
        if (-not (Test-Path -LiteralPath $carpeta)) {
            New-Item -ItemType Directory -Path $carpeta -Force | Out-Null
        }
    }
    Ejecutar -Archivo 'icacls.exe' -Argumentos @($R.Datos, '/inheritance:r', '/grant:r', "*$($script:SidAdministradores):(OI)(CI)F", "*$($script:SidSistema):(OI)(CI)F", "*$($script:SidServicio):(OI)(CI)M", '/Q') -Descripcion 'Permisos de la carpeta de datos' | Out-Null
    Ejecutar -Archivo 'icacls.exe' -Argumentos @((Join-Path $R.Datos '*'), '/reset', '/T', '/C', '/Q') -Descripcion 'El contenido de la carpeta de datos hereda esos permisos' | Out-Null
    Comprobar-Privado -Ruta $R.Instancia
}

function Proteger-Programa {
    param([Parameter(Mandatory = $true)]$R)
    Ejecutar -Archivo 'icacls.exe' -Argumentos @($R.Programa, '/grant', "*$($script:SidServicio):(OI)(CI)RX", '/Q') -Descripcion 'La cuenta del servicio solo lee la carpeta del programa' | Out-Null
    foreach ($regla in (Get-Acl -LiteralPath $R.Programa).Access) {
        $sid = Sid-De $regla.IdentityReference
        if ($sid -eq $script:SidServicio -and ($regla.FileSystemRights -band [System.Security.AccessControl.FileSystemRights]::Write)) {
            throw 'La cuenta del servicio tiene permiso de escritura en la carpeta del programa.'
        }
    }
}

function Sid-De {
    param($Identidad)
    try {
        return $Identidad.Translate([System.Security.Principal.SecurityIdentifier]).Value
    }
    catch {
        return "$Identidad"
    }
}

function Comprobar-Privado {
    param([Parameter(Mandatory = $true)][string]$Ruta)
    $permitidos = @($script:SidAdministradores, $script:SidSistema, $script:SidServicio)
    foreach ($regla in (Get-Acl -LiteralPath $Ruta).Access) {
        if ($regla.AccessControlType -ne 'Allow') { continue }
        $sid = Sid-De $regla.IdentityReference
        if ($permitidos -notcontains $sid) {
            throw ('La carpeta {0} da acceso a {1}; solo deben tenerlo Administradores, SYSTEM y la cuenta del servicio.' -f $Ruta, $regla.IdentityReference)
        }
    }
}

function Servicio-Existe {
    param([Parameter(Mandatory = $true)][string]$Nombre)
    return $null -ne (Get-Service -Name $Nombre -ErrorAction SilentlyContinue)
}

function Detener-Servicios {
    param([Parameter(Mandatory = $true)]$R)
    foreach ($nombre in ($script:Servicios[($script:Servicios.Count - 1)..0])) {
        $servicio = Get-Service -Name $nombre -ErrorAction SilentlyContinue
        if ($null -ne $servicio -and $servicio.Status -ne 'Stopped') {
            Escribir-Registro "Deteniendo $nombre"
            Stop-Service -Name $nombre -Force -ErrorAction Stop
            $servicio.WaitForStatus('Stopped', [TimeSpan]::FromSeconds(60))
        }
    }
}

function Quitar-Servicios {
    param([Parameter(Mandatory = $true)]$R)
    Detener-Servicios -R $R
    foreach ($nombre in $script:Servicios) {
        if (Servicio-Existe $nombre) {
            $envoltura = Join-Path $R.Servicios "$nombre.exe"
            if (Test-Path -LiteralPath $envoltura) {
                Ejecutar -Archivo $envoltura -Argumentos @('uninstall') -Descripcion "Quitando el servicio $nombre" | Out-Null
            }
            else {
                Ejecutar -Archivo 'sc.exe' -Argumentos @('delete', $nombre) -Descripcion "Quitando el servicio $nombre" | Out-Null
            }
            $limite = (Get-Date).AddSeconds(60)
            while ((Servicio-Existe $nombre) -and (Get-Date) -lt $limite) { Start-Sleep -Seconds 1 }
            if (Servicio-Existe $nombre) { throw "El servicio $nombre no se pudo quitar." }
        }
    }
}

function Instalar-Servicios {
    param([Parameter(Mandatory = $true)]$R)
    Quitar-Servicios -R $R
    foreach ($nombre in $script:Servicios) {
        $envoltura = Join-Path $R.Servicios "$nombre.exe"
        if (-not (Test-Path -LiteralPath $envoltura)) { throw "Falta $envoltura." }
        Ejecutar -Archivo $envoltura -Argumentos @('install') -Descripcion "Instalando el servicio $nombre" | Out-Null
        $cuenta = (Get-CimInstance -ClassName Win32_Service -Filter "Name='$nombre'").StartName
        if ($cuenta -ne 'NT AUTHORITY\LocalService') { throw "El servicio $nombre quedó con la cuenta '$cuenta' en lugar de NT AUTHORITY\LocalService." }
    }
}

function Iniciar-Servicios {
    param([Parameter(Mandatory = $true)]$R)
    foreach ($nombre in $script:Servicios) {
        Escribir-Registro "Iniciando $nombre"
        Start-Service -Name $nombre -ErrorAction Stop
        (Get-Service -Name $nombre).WaitForStatus('Running', [TimeSpan]::FromSeconds(90))
    }
}

function Puerto-Ocupado {
    param([Parameter(Mandatory = $true)][int]$Puerto)
    $escuchas = Get-NetTCPConnection -LocalPort $Puerto -State Listen -ErrorAction SilentlyContinue
    return $null -ne $escuchas
}

function Instalar-Firewall {
    Quitar-Firewall
    Escribir-Registro 'Regla de firewall: HTTPS 443 solo desde la red local'
    New-NetFirewallRule -Name $script:ReglaFirewall -DisplayName 'Ariasmos (HTTPS en la red local)' -Direction Inbound -Protocol TCP -LocalPort 443 -RemoteAddress LocalSubnet -Action Allow -Profile Any | Out-Null
}

function Quitar-Firewall {
    $regla = Get-NetFirewallRule -Name $script:ReglaFirewall -ErrorAction SilentlyContinue
    if ($null -ne $regla) {
        Escribir-Registro 'Quitando la regla de firewall'
        Remove-NetFirewallRule -Name $script:ReglaFirewall
    }
}

function Leer-Certificado {
    param([Parameter(Mandatory = $true)][string]$Ruta)
    $texto = Get-Content -LiteralPath $Ruta -Raw -Encoding Ascii
    if ($texto -match 'PRIVATE KEY' -or ([regex]::Matches($texto, '-----BEGIN CERTIFICATE-----')).Count -ne 1) {
        throw "El archivo $Ruta no es un único certificado público."
    }
    $certificado = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2(, [System.IO.File]::ReadAllBytes($Ruta))
    if (Es-Autoridad $certificado) { throw "El archivo $Ruta es un certificado de autoridad y no el del servidor." }
    return $certificado
}

function Es-Autoridad {
    param([Parameter(Mandatory = $true)]$Certificado)
    foreach ($extension in $Certificado.Extensions) {
        if ($extension -is [System.Security.Cryptography.X509Certificates.X509BasicConstraintsExtension]) {
            return $extension.CertificateAuthority
        }
    }
    return $true
}

function Huella-De {
    param([Parameter(Mandatory = $true)][string]$Ruta)
    if (-not (Test-Path -LiteralPath $Ruta)) { return '' }
    try {
        return (Leer-Certificado -Ruta $Ruta).Thumbprint
    }
    catch {
        Escribir-Registro "AVISO: no se pudo leer $Ruta ($($_.Exception.Message))"
        return ''
    }
}

function Almacen-Raiz {
    param([Parameter(Mandatory = $true)][scriptblock]$Accion)
    $almacen = New-Object System.Security.Cryptography.X509Certificates.X509Store('Root', 'LocalMachine')
    $almacen.Open('ReadWrite')
    try {
        & $Accion $almacen
    }
    finally {
        $almacen.Close()
    }
}

function Quitar-De-Raices {
    param([Parameter(Mandatory = $true)][string]$Huella)
    if (-not $Huella) { return }
    Almacen-Raiz {
        param($almacen)
        foreach ($existente in @($almacen.Certificates.Find('FindByThumbprint', $Huella, $false))) {
            $almacen.Remove($existente)
            Escribir-Registro ('Certificado {0} quitado de las raíces de confianza de este equipo' -f $existente.Thumbprint)
        }
    }
}

function Proteger-Clave {
    param([Parameter(Mandatory = $true)]$R)
    if (-not (Test-Path -LiteralPath $R.ClaveServidor)) { throw "Falta la clave privada del servidor en $($R.ClaveServidor)." }
    Ejecutar -Archivo 'icacls.exe' -Argumentos @($R.ClaveServidor, '/inheritance:r', '/grant:r', "*$($script:SidAdministradores):F", "*$($script:SidSistema):F", "*$($script:SidServicio):R", '/Q') -Descripcion 'Permisos de la clave privada del servidor: solo lectura para el servicio' | Out-Null
}

function Preparar-Certificado {
    param([Parameter(Mandatory = $true)]$R, [Parameter(Mandatory = $true)][string]$Nombre)
    $anteriores = @(@((Huella-De -Ruta $R.CertServidor), (Huella-De -Ruta $R.Certificado)) | Where-Object { $_ } | Select-Object -Unique)
    $salida = Manage -R $R -Argumentos @('generar_certificado', '--nombre', $Nombre, '--cert', $R.CertServidor, '--clave', $R.ClaveServidor, '--si-hace-falta') -Descripcion 'Certificado del servidor'
    Proteger-Clave -R $R
    $certificado = Leer-Certificado -Ruta $R.CertServidor
    $nuevo = @($salida | Where-Object { $_ -match '^CERTIFICADO: nuevo ' }).Count -gt 0
    foreach ($huella in $anteriores) {
        if ($huella -ne $certificado.Thumbprint) {
            Quitar-De-Raices -Huella $huella
        }
    }
    if ($nuevo -and @($anteriores | Where-Object { $_ -ne $certificado.Thumbprint }).Count -gt 0) {
        Escribir-Registro 'AVISO: se generó un certificado nuevo para este servidor. Hay que volver a instalarlo en las demás computadoras (Conectar otra computadora).'
    }
    Copy-Item -LiteralPath $R.CertServidor -Destination $R.Certificado -Force
    Almacen-Raiz {
        param($almacen)
        $almacen.Add($certificado)
    }
    Escribir-Registro ('Certificado del servidor publicado en {0} e instalado en las raíces de confianza (huella {1}, vence {2:yyyy-MM-dd})' -f $R.Certificado, $certificado.Thumbprint, $certificado.NotAfter)
}

function Limpiar-Autoridad-Anterior {
    param([Parameter(Mandatory = $true)]$R)
    $pki = Join-Path $R.CaddyDatos 'caddy\pki'
    if (-not (Test-Path -LiteralPath $pki)) { return }
    foreach ($archivo in @(Get-ChildItem -LiteralPath $pki -Recurse -Filter '*.crt' -File)) {
        try {
            $certificado = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2(, [System.IO.File]::ReadAllBytes($archivo.FullName))
            Quitar-De-Raices -Huella $certificado.Thumbprint
        }
        catch {
            Escribir-Registro "AVISO: no se pudo leer $($archivo.FullName)"
        }
    }
    Remove-Item -LiteralPath $pki -Recurse -Force
    Escribir-Registro 'Se quitó la autoridad de certificados local de una versión anterior'
}

function Quitar-Certificado {
    param([Parameter(Mandatory = $true)]$R)
    foreach ($huella in @(@((Huella-De -Ruta $R.Certificado), (Huella-De -Ruta $R.CertServidor)) | Where-Object { $_ } | Select-Object -Unique)) {
        Quitar-De-Raices -Huella $huella
    }
}

function Esperar-Aplicacion {
    $limite = (Get-Date).AddSeconds(120)
    $ultimo = ''
    while ((Get-Date) -lt $limite) {
        $anterior = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        $codigo = & curl.exe -s --ssl-revoke-best-effort -o NUL -w '%{http_code}' 'https://localhost/' 2>$null
        $ErrorActionPreference = $anterior
        $ultimo = "$codigo"
        if ($ultimo -match '^(200|302)$') {
            Escribir-Registro "La aplicación responde por https://localhost/ (HTTP $ultimo)"
            return $true
        }
        Start-Sleep -Seconds 3
    }
    Escribir-Registro "AVISO: la aplicación no respondió por https://localhost/ (último código: $ultimo). Revisa los registros en la carpeta registros."
    return $false
}
