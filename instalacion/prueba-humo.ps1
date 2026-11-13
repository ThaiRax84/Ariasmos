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
$Publico = Join-Path $Datos 'certificado\ariasmos-servidor.crt'
$Equipo = ''
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
        if ($texto -match 'revocation|CRYPT_E_NO_REVOCATION_CHECK|CRYPT_E_REVOCATION_OFFLINE') {
            $cabeceras = & curl.exe -sS --ssl-revoke-best-effort -o NUL -D - --max-time 10 'https://localhost/' 2>&1
            $texto = ($cabeceras | ForEach-Object { "$_" }) -join "`n"
        }
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
    $archivos = @(Get-ChildItem -LiteralPath (Join-Path $Programa 'servicios') -Filter '*.xml') + @(Get-Item -LiteralPath (Join-Path $Datos 'caddy\caddy.json')) + @(Get-ChildItem -LiteralPath $Registros -File)
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
    Paso 'Ninguna clave en XML, configuración de Caddy, registros ni variables de entorno'
}

function Analizar-Certificado {
    param([string]$Ruta)
    $python = Join-Path $Programa 'python\python.exe'
    $codigo = @'
import json, sys
from cryptography import x509
from cryptography.x509.oid import ExtendedKeyUsageOID
datos = open(sys.argv[1], "rb").read()
c = x509.load_pem_x509_certificate(datos) if datos.startswith(b"-----") else x509.load_der_x509_certificate(datos)
e = c.extensions
san = e.get_extension_for_class(x509.SubjectAlternativeName)
bc = e.get_extension_for_class(x509.BasicConstraints)
ku = e.get_extension_for_class(x509.KeyUsage).value
eku = e.get_extension_for_class(x509.ExtendedKeyUsage).value
print(json.dumps({
    "sujeto": c.subject.rfc4514_string(),
    "emisor": c.issuer.rfc4514_string(),
    "dns": san.value.get_values_for_type(x509.DNSName),
    "ips": [str(i) for i in san.value.get_values_for_type(x509.IPAddress)],
    "ca": bc.value.ca,
    "bc_critica": bc.critical,
    "firma_digital": ku.digital_signature,
    "firma_certificados": ku.key_cert_sign,
    "servidor": ExtendedKeyUsageOID.SERVER_AUTH in eku,
    "curva": getattr(getattr(c.public_key(), "curve", None), "name", ""),
    "dias": (c.not_valid_after_utc - c.not_valid_before_utc).days,
    "vence": c.not_valid_after_utc.strftime("%Y-%m-%d"),
}))
'@
    $script = Join-Path $env:TEMP 'ariasmos-analizar.py'
    Set-Content -LiteralPath $script -Value $codigo -Encoding Ascii
    $salida = & $python -I $script $Ruta
    if ($LASTEXITCODE -ne 0) { Fallar "No se pudo analizar el certificado $Ruta." }
    return ($salida -join '') | ConvertFrom-Json
}

function Certificado-Servido {
    param([string]$Nombre)
    $cliente = New-Object System.Net.Sockets.TcpClient('127.0.0.1', 443)
    try {
        $tls = New-Object System.Net.Security.SslStream($cliente.GetStream(), $false)
        try {
            $tls.AuthenticateAsClient($Nombre, $null, [System.Security.Authentication.SslProtocols]::Tls12, $false)
        }
        catch {
            Fallar "La conexión TLS a $Nombre no se validó contra el almacén del equipo: $($_.Exception.InnerException.Message) $($_.Exception.Message)"
        }
        $certificado = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($tls.RemoteCertificate)
        $tls.Dispose()
        return $certificado
    }
    finally {
        $cliente.Close()
    }
}

function Comprobar-Curl {
    param([string]$Nombre)
    $argumentos = @('-sS', '-o', 'NUL', '-w', '%{http_code}', '--max-time', '15', '--resolve', "$($Nombre):443:127.0.0.1", "https://$Nombre/")
    $anterior = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $salida = (& curl.exe @argumentos 2>&1 | ForEach-Object { "$_" }) -join ' '
    $codigo = $LASTEXITCODE
    $modo = 'estricto'
    if ($codigo -ne 0 -and $salida -match 'revocation|CRYPT_E_NO_REVOCATION_CHECK|CRYPT_E_REVOCATION_OFFLINE') {
        $salida = (& curl.exe --ssl-revoke-best-effort @argumentos 2>&1 | ForEach-Object { "$_" }) -join ' '
        $codigo = $LASTEXITCODE
        $modo = 'revocación en modo best-effort (el certificado no tiene lista de revocación; la cadena se valida igual)'
    }
    $ErrorActionPreference = $anterior
    if ($codigo -ne 0 -or $salida -notmatch '(200|302)$') { Fallar "curl.exe (Schannel) no validó https://$Nombre/ (código $codigo): $salida" }
    Paso "curl.exe con Schannel valida https://$Nombre/ sin desactivar la verificación ($modo): HTTP $salida"
}

function Equipo-Esperado {
    . (Join-Path $Programa 'herramientas\comun.ps1')
    return Nombre-Equipo
}

function Comprobar-Certificado {
    if (-not (Test-Path -LiteralPath $Publico)) { Fallar 'No se publicó el certificado del servidor.' }
    $texto = Get-Content -LiteralPath $Publico -Raw
    if ($texto -match 'PRIVATE KEY') { Fallar 'El certificado publicado contiene una clave privada.' }
    if (([regex]::Matches($texto, '-----BEGIN CERTIFICATE-----')).Count -ne 1) { Fallar 'El archivo publicado no es un único certificado.' }
    $certificado = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2(, [System.IO.File]::ReadAllBytes($Publico))
    $instalado = Get-ChildItem -Path Cert:\LocalMachine\Root | Where-Object { $_.Thumbprint -eq $certificado.Thumbprint }
    if (-not $instalado) { Fallar 'El certificado del servidor no está en las raíces de confianza del equipo.' }
    foreach ($nombre in @('localhost', $Equipo) | Select-Object -Unique) {
        $servido = Certificado-Servido -Nombre $nombre
        if ($servido.Thumbprint -ne $certificado.Thumbprint) { Fallar "El certificado servido para $nombre ($($servido.Thumbprint)) no es el instalado ($($certificado.Thumbprint))." }
        Paso ".NET SslStream valida $nombre contra el almacén del equipo y recibe el certificado instalado"
        Comprobar-Curl -Nombre $nombre
    }
    $temporal = Join-Path $env:TEMP 'ariasmos-servido.der'
    [System.IO.File]::WriteAllBytes($temporal, $servido.RawData)
    $a = Analizar-Certificado -Ruta $temporal
    if ($a.ca -or -not $a.bc_critica) { Fallar 'El certificado servido es de autoridad o su basicConstraints no es crítica.' }
    if ($a.firma_certificados -or -not $a.firma_digital -or -not $a.servidor) { Fallar 'El uso de clave del certificado no es solo de servidor.' }
    if ((@($a.dns) -join ',') -ne "$Equipo,localhost" -or (@($a.ips) -join ',') -ne '127.0.0.1') { Fallar "Nombres inesperados en el certificado: $(@($a.dns) -join ',') $(@($a.ips) -join ',')." }
    if ($a.sujeto -ne $a.emisor -or $a.sujeto -ne "CN=Ariasmos $Equipo") { Fallar "Sujeto o emisor inesperado: $($a.sujeto) / $($a.emisor)." }
    if ($a.curva -ne 'secp256r1') { Fallar "La clave no es P-256 ($($a.curva))." }
    if ($a.dias -lt 3649 -or $a.dias -gt 3651) { Fallar "La vigencia no es de unos 10 años ($($a.dias) días)." }
    $sha256 = (Get-FileHash -LiteralPath $temporal -Algorithm SHA256).Hash
    Paso "Certificado del servidor: SHA-256 $sha256, SHA-1 $($certificado.Thumbprint), $($a.sujeto), DNS $(@($a.dns) -join ', '), IP $(@($a.ips) -join ', '), CA:FALSE crítica, serverAuth, $($a.curva), $($a.dias) días, vence $($a.vence)"
    $clave = Join-Path $Datos 'caddy\servidor.key'
    $permitidos = @('S-1-5-32-544', 'S-1-5-18', 'S-1-5-19')
    foreach ($regla in (Get-Acl -LiteralPath $clave).Access) {
        $sid = $regla.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value
        if ($regla.AccessControlType -eq 'Allow' -and $permitidos -notcontains $sid) { Fallar "La clave privada da acceso a $($regla.IdentityReference)." }
        if ($sid -eq 'S-1-5-19' -and ($regla.FileSystemRights -band [System.Security.AccessControl.FileSystemRights]::Write)) { Fallar 'La cuenta del servicio puede escribir la clave privada.' }
    }
    foreach ($archivo in @(Get-ChildItem -LiteralPath $Datos -Recurse -File -ErrorAction SilentlyContinue | Where-Object { $_.FullName -ne $clave -and $_.Length -lt 10MB })) {
        if ((Get-Content -LiteralPath $archivo.FullName -Raw -ErrorAction SilentlyContinue) -match 'PRIVATE KEY') { Fallar "Hay una clave privada fuera de su lugar: $($archivo.FullName)." }
    }
    Paso 'La clave privada solo está en caddy\servidor.key, con lectura para el servicio y sin acceso para Usuarios'
    Comprobar-SinAutoridad
    return $certificado.Thumbprint
}

function Comprobar-SinAutoridad {
    $pki = @(Get-ChildItem -LiteralPath (Join-Path $Datos 'caddy') -Recurse -Directory -Filter 'pki' -ErrorAction SilentlyContinue)
    if ($pki.Count -gt 0) { Fallar "Caddy creó una autoridad local: $($pki[0].FullName)." }
    foreach ($almacen in @('Cert:\LocalMachine\Root', 'Cert:\CurrentUser\Root', 'Cert:\LocalMachine\CA')) {
        $autoridad = @(Get-ChildItem -Path $almacen -ErrorAction SilentlyContinue | Where-Object { $_.Subject -match 'Caddy Local Authority' })
        if ($autoridad.Count -gt 0) { Fallar "Hay una autoridad de Caddy en $($almacen): $($autoridad[0].Subject)." }
    }
    Paso 'Sin carpeta pki ni autoridad de Caddy en los almacenes'
}

function Comprobar-Navegador {
    param([string]$Nombre, [string]$Ejecutable)
    if (-not (Test-Path -LiteralPath $Ejecutable)) {
        Paso "$Nombre no está instalado en este equipo: se omite"
        return $false
    }
    $perfil = Join-Path $env:TEMP ("ariasmos-$Nombre-" + [guid]::NewGuid().ToString('N'))
    $salida = Join-Path $Registros "navegador-$Nombre.html"
    $errores = Join-Path $Registros "navegador-$Nombre.err"
    $argumentos = @('--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check', '--disable-extensions', "--user-data-dir=`"$perfil`"", '--virtual-time-budget=5000', '--dump-dom', 'https://localhost/')
    $proceso = Start-Process -FilePath $Ejecutable -ArgumentList $argumentos -RedirectStandardOutput $salida -RedirectStandardError $errores -PassThru -WindowStyle Hidden
    if (-not $proceso.WaitForExit(120000)) {
        $proceso.Kill()
        Fallar "$Nombre sin interfaz no terminó en 2 minutos."
    }
    $dom = if (Test-Path -LiteralPath $salida) { Get-Content -LiteralPath $salida -Raw } else { '' }
    if ($null -eq $dom) { $dom = '' }
    $titulo = if ($dom -match '<title>([^<]*)</title>') { $Matches[1].Trim() } else { '(sin título)' }
    Write-Host "---- $Nombre --dump-dom https://localhost/ (código $($proceso.ExitCode), $($dom.Length) caracteres, título: $titulo) ----"
    Write-Host ($dom.Substring(0, [Math]::Min(1500, $dom.Length)))
    Write-Host "---- fin de la salida de $Nombre ----"
    if ($dom -match 'ERR_CERT|NET::ERR|SSL_ERROR|privacy-error|interstitial') { Fallar "$Nombre rechazó el certificado del servidor: $titulo." }
    if ($dom -notmatch 'name="token"') { Fallar "$Nombre no mostró la página del asistente (título: $titulo)." }
    Paso "$Nombre sin interfaz abre https://localhost/ con el certificado instalado y muestra el asistente (título: $titulo)"
    return $true
}

function Comprobar-Navegadores {
    $edge = Comprobar-Navegador -Nombre 'edge' -Ejecutable (Join-Path ${env:ProgramFiles(x86)} 'Microsoft\Edge\Application\msedge.exe')
    if (-not $edge) { $edge = Comprobar-Navegador -Nombre 'edge' -Ejecutable (Join-Path ${env:ProgramFiles} 'Microsoft\Edge\Application\msedge.exe') }
    if (-not $edge) { Fallar 'Microsoft Edge no está disponible para la comprobación con navegador.' }
    Comprobar-Navegador -Nombre 'chrome' -Ejecutable (Join-Path ${env:ProgramFiles} 'Google\Chrome\Application\chrome.exe') | Out-Null
}

function Mostrar-Registros {
    foreach ($carpeta in @($Registros, (Join-Path $Datos 'registros'))) {
        if (-not (Test-Path -LiteralPath $carpeta)) { continue }
        foreach ($archivo in @(Get-ChildItem -LiteralPath $carpeta -File -ErrorAction SilentlyContinue)) {
            Write-Host "::group::$($archivo.FullName)"
            Get-Content -LiteralPath $archivo.FullName -Tail 400 -ErrorAction SilentlyContinue | ForEach-Object { Write-Host $_ }
            Write-Host '::endgroup::'
        }
    }
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
    $Equipo = Equipo-Esperado
    Paso "Nombre del equipo esperado en el certificado: $Equipo"
    Esperar-Servicios
    Comprobar-Asistente
    Comprobar-Puerto8000
    Comprobar-Permisos
    Comprobar-Firewall
    $huella = Comprobar-Certificado
    Comprobar-Navegadores
    Copiar-Registros
    Comprobar-SinSecretos

    $antes = Get-Content -LiteralPath (Join-Path $Instancia 'configuracion.json') -Raw | ConvertFrom-Json
    Instalar -Nombre 'actualizacion'
    Esperar-Servicios
    Comprobar-Asistente
    if ((Comprobar-Certificado) -ne $huella) { Fallar 'La actualización cambió el certificado del servidor sin que hiciera falta.' }
    Paso 'La actualización conservó el certificado del servidor'
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
    if (Get-ChildItem -Path Cert:\LocalMachine\Root | Where-Object { $_.Thumbprint -eq $huella -or $_.Subject -like 'CN=Ariasmos *' }) { Fallar 'Un certificado de Ariasmos sigue en las raíces de confianza.' }
    Comprobar-SinAutoridad
    if (-not (Test-Path -LiteralPath (Join-Path $Instancia 'configuracion.json'))) { Fallar 'La desinstalación borró los datos.' }
    Paso 'Desinstalación correcta: sin servicios, sin regla ni certificado, datos conservados'
}
catch {
    $resultado = 1
    Write-Host "PRUEBA DE HUMO FALLIDA: $($_.Exception.Message)"
    Copiar-Registros
    Mostrar-Registros
}
finally {
    Copiar-Registros
}
exit $resultado
