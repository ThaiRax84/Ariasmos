param(
    [Parameter(Mandatory = $true)][string]$Instalador,
    [Parameter(Mandatory = $true)][string]$Registros
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$Programa = Join-Path ${env:ProgramFiles} 'Ariasmos'
$Datos = Join-Path $env:ProgramData 'Ariasmos'
$Instancia = Join-Path $Datos 'instancia'
$Servicios = @('AriasmosWeb', 'AriasmosTrabajador', 'AriasmosTLS')
New-Item -ItemType Directory -Path $Registros -Force | Out-Null

function Paso { param([string]$Mensaje) Write-Host ('==> {0}' -f $Mensaje) }

function Fallar {
    param([string]$Mensaje)
    Write-Host "::error::$Mensaje"
    throw $Mensaje
}

function Instalar {
    param([string]$Nombre)
    $registro = Join-Path $Registros "$Nombre.log"
    Paso "Instalación silenciosa ($Nombre)"
    $proceso = Start-Process -FilePath $Instalador -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', "/LOG=`"$registro`"") -Wait -PassThru
    if ($proceso.ExitCode -ne 0) { Fallar "El instalador terminó con código $($proceso.ExitCode) ($Nombre)." }
    $texto = Get-Content -LiteralPath $registro -Raw
    if ($texto -match 'TOKEN-ASISTENTE|Token del asistente') { Fallar "El registro del instalador contiene el token del asistente ($Nombre)." }
}

function Esperar-Servicios {
    $limite = (Get-Date).AddMinutes(3)
    foreach ($nombre in $Servicios) {
        while ($true) {
            $servicio = Get-Service -Name $nombre -ErrorAction SilentlyContinue
            if ($null -ne $servicio -and $servicio.Status -eq 'Running') { break }
            if ((Get-Date) -gt $limite) { Fallar "El servicio $nombre no está en ejecución (estado: $(if ($servicio) { $servicio.Status } else { 'no existe' }))." }
            Start-Sleep -Seconds 2
        }
        $info = Get-CimInstance -ClassName Win32_Service -Filter "Name='$nombre'"
        if ($info.StartName -ne 'NT AUTHORITY\LocalService') { Fallar "El servicio $nombre corre como '$($info.StartName)' y no como NT AUTHORITY\LocalService." }
        if ($info.StartMode -ne 'Auto') { Fallar "El servicio $nombre no tiene inicio automático ($($info.StartMode))." }
        Paso "$nombre en ejecución como $($info.StartName)"
    }
}

function Comprobar-Asistente {
    $limite = (Get-Date).AddMinutes(2)
    while ($true) {
        $cabeceras = & curl.exe -sS -o NUL -D - --max-time 10 'https://localhost/' 2>&1
        $texto = ($cabeceras | ForEach-Object { "$_" }) -join "`n"
        if ($texto -match 'HTTP/[\d.]+ 302' -and $texto -match '(?im)^location:\s*/asistente/') {
            Paso 'https://localhost/ responde con un certificado de confianza y redirige al asistente'
            return
        }
        if ((Get-Date) -gt $limite) { Fallar "https://localhost/ no redirigió al asistente. Respuesta: $texto" }
        Start-Sleep -Seconds 3
    }
}

function Comprobar-Puerto8000 {
    $escuchas = @(Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue)
    if ($escuchas.Count -eq 0) { Fallar 'Nada escucha en el puerto 8000.' }
    foreach ($e in $escuchas) {
        if ($e.LocalAddress -ne '127.0.0.1') { Fallar "El puerto 8000 escucha en $($e.LocalAddress)." }
    }
    $direccion = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } | Select-Object -First 1
    if ($null -ne $direccion) {
        $cliente = New-Object System.Net.Sockets.TcpClient
        try {
            $intento = $cliente.BeginConnect($direccion.IPAddress, 8000, $null, $null)
            $conectado = $intento.AsyncWaitHandle.WaitOne(3000) -and $cliente.Connected
        }
        finally {
            $cliente.Close()
        }
        if ($conectado) { Fallar "El puerto 8000 responde desde $($direccion.IPAddress)." }
        Paso "El puerto 8000 no responde desde $($direccion.IPAddress)"
    }
}

function Comprobar-Permisos {
    $permitidos = @('S-1-5-32-544', 'S-1-5-18', 'S-1-5-19')
    foreach ($ruta in @($Datos, $Instancia, (Join-Path $Instancia 'configuracion.json'))) {
        foreach ($regla in (Get-Acl -LiteralPath $ruta).Access) {
            $sid = $regla.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value
            if ($regla.AccessControlType -eq 'Allow' -and $permitidos -notcontains $sid) { Fallar "$ruta da acceso a $($regla.IdentityReference) ($sid)." }
        }
    }
    $leible = $true
    try {
        $usuarios = New-Object System.Security.Principal.SecurityIdentifier('S-1-5-32-545')
        $reglas = (Get-Acl -LiteralPath $Instancia).Access | Where-Object { $_.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]) -eq $usuarios }
        $leible = @($reglas).Count -gt 0
    }
    catch { $leible = $true }
    if ($leible) { Fallar 'El grupo Usuarios tiene acceso a la instancia.' }
    $escritura = (Get-Acl -LiteralPath $Programa).Access | Where-Object {
        $_.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value -eq 'S-1-5-19' -and ($_.FileSystemRights -band [System.Security.AccessControl.FileSystemRights]::Write)
    }
    if (@($escritura).Count -gt 0) { Fallar 'La cuenta del servicio puede escribir en la carpeta del programa.' }
    Paso 'Permisos de la instancia y del programa correctos'
}

function Comprobar-Firewall {
    $regla = Get-NetFirewallRule -Name 'Ariasmos-HTTPS' -ErrorAction SilentlyContinue
    if ($null -eq $regla) { Fallar 'No existe la regla de firewall Ariasmos-HTTPS.' }
    if ($regla.Direction -ne 'Inbound' -or $regla.Action -ne 'Allow' -or $regla.Enabled -ne 'True') { Fallar 'La regla de firewall no es de entrada, permitida y activa.' }
    $puertos = $regla | Get-NetFirewallPortFilter
    if ($puertos.Protocol -ne 'TCP' -or "$($puertos.LocalPort)" -ne '443') { Fallar "La regla de firewall no es TCP 443 ($($puertos.Protocol) $($puertos.LocalPort))." }
    $direcciones = $regla | Get-NetFirewallAddressFilter
    if ("$($direcciones.RemoteAddress)" -ne 'LocalSubnet') { Fallar "La regla de firewall no está limitada a la red local ($($direcciones.RemoteAddress))." }
    Paso 'Regla de firewall TCP 443 limitada a la red local'
}

function Comprobar-SinSecretos {
    $configuracion = Get-Content -LiteralPath (Join-Path $Instancia 'configuracion.json') -Raw | ConvertFrom-Json
    $claves = @('clave_django', 'clave_matricula', 'clave_auditoria', 'clave_respaldo', 'clave_secretos') | ForEach-Object { [string]$configuracion.$_ } | Where-Object { $_ }
    $archivos = @(Get-ChildItem -LiteralPath (Join-Path $Programa 'servicios') -Filter '*.xml') + @(Get-Item -LiteralPath (Join-Path $Datos 'caddy\Caddyfile')) + @(Get-ChildItem -LiteralPath $Registros -File)
    foreach ($archivo in $archivos) {
        $texto = Get-Content -LiteralPath $archivo.FullName -Raw
        foreach ($clave in $claves) { if ($texto.Contains($clave)) { Fallar "$($archivo.FullName) contiene una clave de la instancia." } }
    }
    foreach ($ambito in @('Machine', 'User')) {
        $variables = [Environment]::GetEnvironmentVariables($ambito)
        foreach ($nombre in $variables.Keys) {
            foreach ($clave in $claves) { if ("$($variables[$nombre])".Contains($clave)) { Fallar "La variable de entorno $nombre ($ambito) contiene una clave." } }
        }
    }
    Paso 'Ninguna clave en XML, Caddyfile, registros ni variables de entorno'
}

function Comprobar-Certificado {
    $publico = Join-Path $Datos 'certificado\ariasmos-raiz.crt'
    if (-not (Test-Path -LiteralPath $publico)) { Fallar 'No se publicó el certificado raíz.' }
    $texto = Get-Content -LiteralPath $publico -Raw
    if ($texto -match 'PRIVATE KEY') { Fallar 'El certificado publicado contiene una clave privada.' }
    $certificado = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2(, [System.IO.File]::ReadAllBytes($publico))
    $instalado = Get-ChildItem -Path Cert:\LocalMachine\Root | Where-Object { $_.Thumbprint -eq $certificado.Thumbprint }
    if (-not $instalado) { Fallar 'El certificado raíz no está en las raíces de confianza del equipo.' }
    Paso "Certificado raíz instalado ($($certificado.Thumbprint))"
    return $certificado.Thumbprint
}

function Copiar-Registros {
    $origen = Join-Path $Datos 'registros'
    if (Test-Path -LiteralPath $origen) {
        Copy-Item -Path (Join-Path $origen '*') -Destination $Registros -Force -ErrorAction SilentlyContinue
    }
}

$resultado = 0
try {
    Instalar -Nombre 'instalacion'
    Esperar-Servicios
    Comprobar-Asistente
    Comprobar-Puerto8000
    Comprobar-Permisos
    Comprobar-Firewall
    $huella = Comprobar-Certificado
    Copiar-Registros
    Comprobar-SinSecretos

    $antes = Get-Content -LiteralPath (Join-Path $Instancia 'configuracion.json') -Raw | ConvertFrom-Json
    Instalar -Nombre 'actualizacion'
    Esperar-Servicios
    Comprobar-Asistente
    $despues = Get-Content -LiteralPath (Join-Path $Instancia 'configuracion.json') -Raw | ConvertFrom-Json
    foreach ($propiedad in $antes.PSObject.Properties) {
        $nuevo = $despues.PSObject.Properties[$propiedad.Name]
        if ($null -eq $nuevo) { Fallar "La actualización quitó la clave $($propiedad.Name) de configuracion.json." }
        if (($propiedad.Value | ConvertTo-Json -Compress -Depth 5) -ne ($nuevo.Value | ConvertTo-Json -Compress -Depth 5)) { Fallar "La actualización cambió $($propiedad.Name) en configuracion.json." }
    }
    $copias = @(Get-ChildItem -LiteralPath (Join-Path $Datos 'antes-de-actualizar') -Directory)
    if ($copias.Count -lt 1 -or -not (Test-Path -LiteralPath (Join-Path $copias[0].FullName 'instancia\configuracion.json'))) { Fallar 'La actualización no guardó la copia de la instancia.' }
    Paso 'La actualización conservó configuracion.json y guardó una copia de la instancia'

    Paso 'Desinstalación silenciosa'
    $desinstalador = Join-Path $Programa 'unins000.exe'
    $proceso = Start-Process -FilePath $desinstalador -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', "/LOG=`"$(Join-Path $Registros 'desinstalacion.log')`"") -Wait -PassThru
    if ($proceso.ExitCode -ne 0) { Fallar "El desinstalador terminó con código $($proceso.ExitCode)." }
    $limite = (Get-Date).AddMinutes(1)
    while ((Test-Path -LiteralPath $desinstalador) -and (Get-Date) -lt $limite) { Start-Sleep -Seconds 2 }
    foreach ($nombre in $Servicios) {
        if ($null -ne (Get-Service -Name $nombre -ErrorAction SilentlyContinue)) { Fallar "El servicio $nombre sigue instalado." }
    }
    if ($null -ne (Get-NetFirewallRule -Name 'Ariasmos-HTTPS' -ErrorAction SilentlyContinue)) { Fallar 'La regla de firewall sigue existiendo.' }
    if (Get-ChildItem -Path Cert:\LocalMachine\Root | Where-Object { $_.Thumbprint -eq $huella }) { Fallar 'El certificado raíz sigue en las raíces de confianza.' }
    if (-not (Test-Path -LiteralPath (Join-Path $Instancia 'configuracion.json'))) { Fallar 'La desinstalación borró los datos.' }
    Paso 'Desinstalación correcta: sin servicios, sin regla ni certificado, datos conservados'
}
catch {
    $resultado = 1
    Write-Host "PRUEBA DE HUMO FALLIDA: $($_.Exception.Message)"
}
finally {
    Copiar-Registros
}
exit $resultado
