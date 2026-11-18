Set-StrictMode -Version Latest
if ($PSVersionTable.PSEdition -ne 'Core') {
    $env:PSModulePath = @((Join-Path ${env:ProgramFiles} 'WindowsPowerShell\Modules'), (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\Modules')) -join ';'
}
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
        Conexion    = Join-Path $Datos 'conexion.json'
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
    $codificacion = [Console]::OutputEncoding
    try {
        [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
    }
    catch {
        $codificacion = $null
    }
    try {
        return Ejecutar -Archivo $R.Python -Argumentos (@('-X', 'utf8', '-B', $R.Manage) + $Argumentos) -Descripcion $Descripcion -Silencioso:$Silencioso
    }
    finally {
        if ($null -ne $codificacion) { [Console]::OutputEncoding = $codificacion }
    }
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
    foreach ($regla in (Reglas-Sid -Ruta $R.Programa)) {
        if ($regla.IdentityReference.Value -eq $script:SidServicio -and $regla.AccessControlType -eq 'Allow' -and ($regla.FileSystemRights -band [System.Security.AccessControl.FileSystemRights]::Write)) {
            throw 'La cuenta del servicio tiene permiso de escritura en la carpeta del programa.'
        }
    }
}

function Reglas-Sid {
    param([Parameter(Mandatory = $true)][string]$Ruta)
    return @((Get-Acl -LiteralPath $Ruta).GetAccessRules($true, $true, [System.Security.Principal.SecurityIdentifier]))
}

function Comprobar-Privado {
    param([Parameter(Mandatory = $true)][string]$Ruta)
    $permitidos = @($script:SidAdministradores, $script:SidSistema, $script:SidServicio)
    foreach ($regla in (Reglas-Sid -Ruta $Ruta)) {
        if ($regla.AccessControlType -ne 'Allow') { continue }
        if ($permitidos -notcontains $regla.IdentityReference.Value) {
            throw ('La carpeta {0} da acceso a {1}; solo deben tenerlo Administradores, SYSTEM y la cuenta del servicio.' -f $Ruta, $regla.IdentityReference.Value)
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
    param([Parameter(Mandatory = $true)][int]$Puerto)
    Quitar-Firewall
    Escribir-Registro "Regla de firewall: HTTPS $Puerto solo desde la red local"
    New-NetFirewallRule -Name $script:ReglaFirewall -DisplayName 'Ariasmos (HTTPS en la red local)' -Direction Inbound -Protocol TCP -LocalPort $Puerto -RemoteAddress LocalSubnet -Action Allow -Profile Any | Out-Null
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

function Huella-Sha256 {
    param([Parameter(Mandatory = $true)][string]$Ruta)
    $certificado = Leer-Certificado -Ruta $Ruta
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        return -join ($sha.ComputeHash($certificado.RawData) | ForEach-Object { $_.ToString('X2') })
    }
    finally {
        $sha.Dispose()
    }
}

function Preparar-Certificado {
    param([Parameter(Mandatory = $true)]$R, [Parameter(Mandatory = $true)][string]$Nombre)
    $anteriores = @(@((Huella-De -Ruta $R.CertServidor), (Huella-De -Ruta $R.Certificado)) | Where-Object { $_ } | Select-Object -Unique)
    $salida = Manage -R $R -Argumentos @('generar_certificado', '--nombre', $Nombre, '--cert', $R.CertServidor, '--clave', $R.ClaveServidor, '--si-hace-falta') -Descripcion 'Certificado del servidor'
    Proteger-Clave -R $R
    $certificado = Leer-Certificado -Ruta $R.CertServidor
    $nuevo = @($salida | Where-Object { $_ -match '^CERTIFICADO: nuevo ' }).Count -gt 0
    foreach ($huella in @($anteriores + @($certificado.Thumbprint) | Select-Object -Unique)) {
        Quitar-De-Raices -Huella $huella
    }
    if ($nuevo -and @($anteriores | Where-Object { $_ -ne $certificado.Thumbprint }).Count -gt 0) {
        Escribir-Registro 'AVISO: se generó un certificado nuevo para este servidor. Hay que llevar un archivo de conexión nuevo a cada computadora adicional (Conectar otra computadora).'
    }
    Copy-Item -LiteralPath $R.CertServidor -Destination $R.Certificado -Force
    Escribir-Registro ('Certificado del servidor en {0} (SHA-256 {1}, vence {2:yyyy-MM-dd}); no se instala en el almacén de Windows' -f $R.Certificado, (Huella-Sha256 -Ruta $R.CertServidor), $certificado.NotAfter)
}

function Estado-Https {
    param(
        [Parameter(Mandatory = $true)][string]$Direccion,
        [Parameter(Mandatory = $true)][int]$Puerto,
        [Parameter(Mandatory = $true)][string]$Huella,
        [string]$Ruta = '/'
    )
    $resultado = [pscustomobject]@{ Codigo = 0; Huella = ''; Cabeceras = '' }
    $visto = @{ Der = $null }
    $cliente = New-Object System.Net.Sockets.TcpClient
    try {
        $intento = $cliente.BeginConnect($Direccion, $Puerto, $null, $null)
        if (-not $intento.AsyncWaitHandle.WaitOne(5000) -or -not $cliente.Connected) { return $resultado }
        $cliente.EndConnect($intento)
        $cliente.ReceiveTimeout = 15000
        $cliente.SendTimeout = 15000
        $validar = [System.Net.Security.RemoteCertificateValidationCallback] {
            param($origen, $certificadoRemoto, $cadena, $errores)
            if ($null -ne $certificadoRemoto) { $visto.Der = $certificadoRemoto.GetRawCertData() }
            return $true
        }
        $tls = New-Object System.Net.Security.SslStream($cliente.GetStream(), $false, $validar)
        try {
            $tls.AuthenticateAsClient($Direccion)
            if ($null -eq $visto.Der) { return $resultado }
            $sha = [System.Security.Cryptography.SHA256]::Create()
            try {
                $resultado.Huella = -join ($sha.ComputeHash($visto.Der) | ForEach-Object { $_.ToString('X2') })
            }
            finally {
                $sha.Dispose()
            }
            if ($resultado.Huella -ne $Huella) { return $resultado }
            $pedido = [System.Text.Encoding]::ASCII.GetBytes("GET $Ruta HTTP/1.1`r`nHost: $Direccion`r`nUser-Agent: Ariasmos-instalador`r`nConnection: close`r`n`r`n")
            $tls.Write($pedido, 0, $pedido.Length)
            $tls.Flush()
            $lector = New-Object System.IO.StreamReader($tls, [System.Text.Encoding]::ASCII)
            $lineas = @()
            while ($true) {
                $linea = $lector.ReadLine()
                if ($null -eq $linea -or $linea -eq '') { break }
                $lineas += $linea
                if ($lineas.Count -gt 100) { break }
            }
            $resultado.Cabeceras = $lineas -join "`n"
            if ($lineas.Count -gt 0 -and $lineas[0] -match '^HTTP/\d(\.\d)? (\d{3}) ') { $resultado.Codigo = [int]$Matches[2] }
        }
        finally {
            $tls.Dispose()
        }
    }
    catch {
        $resultado.Cabeceras = $_.Exception.Message
    }
    finally {
        $cliente.Close()
    }
    return $resultado
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
    param([Parameter(Mandatory = $true)][int]$Puerto, [Parameter(Mandatory = $true)][string]$Huella)
    $limite = (Get-Date).AddSeconds(120)
    $ultimo = ''
    while ((Get-Date) -lt $limite) {
        $estado = Estado-Https -Direccion 'localhost' -Puerto $Puerto -Huella $Huella
        $ultimo = "$($estado.Codigo)"
        if ($estado.Huella -and $estado.Huella -ne $Huella) {
            Escribir-Registro "AVISO: en el puerto $Puerto respondió un certificado distinto al del servidor ($($estado.Huella))."
            return $false
        }
        if ($ultimo -match '^(200|302)$') {
            Escribir-Registro "La aplicación responde en el puerto $Puerto con el certificado del servidor (HTTP $ultimo)"
            return $true
        }
        Start-Sleep -Seconds 3
    }
    Escribir-Registro "AVISO: la aplicación no respondió en el puerto $Puerto (último código: $ultimo). Revisa los registros en la carpeta registros."
    return $false
}
