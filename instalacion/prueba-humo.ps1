param(
    [Parameter(Mandatory = $true)][string]$Instalador,
    [Parameter(Mandatory = $true)][string]$Registros
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

. (Join-Path $PSScriptRoot 'herramientas\comun.ps1')
$ErrorActionPreference = 'Stop'

$Programa = Join-Path ${env:ProgramFiles} 'Ariasmos'
$Datos = Join-Path $env:ProgramData 'Ariasmos'
$Instancia = Join-Path $Datos 'instancia'
$Conexion = Join-Path $Datos 'conexion.json'
$Exe = Join-Path $Programa 'Ariasmos.exe'
$Servicios = @('AriasmosWeb', 'AriasmosTrabajador', 'AriasmosTLS')
$Puerto = 8443
$Equipo = Nombre-Equipo
$RegistroVentana = Join-Path $env:LOCALAPPDATA 'Ariasmos\registro.log'
$Escritorio = [Environment]::GetFolderPath('CommonDesktopDirectory')
$Procesos = @()
New-Item -ItemType Directory -Path $Registros -Force | Out-Null

function Paso { param([string]$Mensaje) Write-Host ('==> {0}' -f $Mensaje) }

function Fallar {
    param([string]$Mensaje)
    Write-Host "::error::$Mensaje"
    throw $Mensaje
}

function Instalar {
    param([string]$Nombre, [string[]]$Extra = @())
    $registro = Join-Path $Registros "$Nombre.log"
    Paso "Instalación silenciosa ($Nombre) $($Extra -join ' ')"
    $proceso = Start-Process -FilePath $Instalador -ArgumentList (@('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', "/LOG=`"$registro`"") + $Extra) -Wait -PassThru
    if ($proceso.ExitCode -ne 0) { Fallar "El instalador terminó con código $($proceso.ExitCode) ($Nombre)." }
    $texto = Get-Content -LiteralPath $registro -Raw
    if ($texto -match 'TOKEN-ASISTENTE|Token del asistente') { Fallar "El registro del instalador contiene el token del asistente ($Nombre)." }
    foreach ($fin in [regex]::Matches($texto, '(\S+\.ps1) termin\S* con c\S*digo (-?\d+)')) {
        if ($fin.Groups[2].Value -ne '0') {
            Fallar "$($fin.Groups[1].Value) terminó con código $($fin.Groups[2].Value) durante la $Nombre."
        }
    }
}

function Desinstalar {
    param([string]$Nombre)
    Paso "Desinstalación silenciosa ($Nombre)"
    $desinstalador = Join-Path $Programa 'unins000.exe'
    $proceso = Start-Process -FilePath $desinstalador -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', "/LOG=`"$(Join-Path $Registros "desinstalacion-$Nombre.log")`"") -Wait -PassThru
    if ($proceso.ExitCode -ne 0) { Fallar "El desinstalador terminó con código $($proceso.ExitCode) ($Nombre)." }
    $limite = (Get-Date).AddMinutes(1)
    while ((Test-Path -LiteralPath $desinstalador) -and (Get-Date) -lt $limite) { Start-Sleep -Seconds 2 }
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

function Leer-Conexion {
    param([string]$Ruta)
    if (-not (Test-Path -LiteralPath $Ruta)) { Fallar "No existe $Ruta." }
    $texto = Get-Content -LiteralPath $Ruta -Raw -Encoding UTF8
    $datos = $texto | ConvertFrom-Json
    $campos = @($datos.PSObject.Properties.Name)
    if (($campos -join ',') -ne 'producto,formato,direccion,puerto,huella') { Fallar "Campos inesperados en ${Ruta}: $($campos -join ',')." }
    if ($datos.producto -ne 'ariasmos' -or $datos.formato -ne 1 -or $datos.huella -notmatch '^[0-9A-F]{64}$') { Fallar "Contenido inesperado en ${Ruta}: $texto" }
    return $datos
}

function Comprobar-Permisos-Conexion {
    $permitidos = @{ 'S-1-5-32-544' = 'FullControl'; 'S-1-5-18' = 'FullControl'; 'S-1-5-32-545' = 'Read' }
    $acl = Get-Acl -LiteralPath $Conexion
    if (-not $acl.AreAccessRulesProtected) { Fallar 'conexion.json hereda permisos.' }
    foreach ($regla in $acl.GetAccessRules($true, $true, [System.Security.Principal.SecurityIdentifier])) {
        $sid = $regla.IdentityReference.Value
        if ($regla.AccessControlType -ne 'Allow') { continue }
        if (-not $permitidos.ContainsKey($sid)) { Fallar "conexion.json da acceso a $sid." }
        if ($sid -eq 'S-1-5-32-545' -and ($regla.FileSystemRights -band ([System.Security.AccessControl.FileSystemRights]::Write -bor [System.Security.AccessControl.FileSystemRights]::Delete -bor [System.Security.AccessControl.FileSystemRights]::ChangePermissions))) { Fallar 'Usuarios puede cambiar conexion.json.' }
    }
    Paso 'conexion.json: solo administradores lo cambian; Usuarios solo lo lee'
}

function Comprobar-Asistente {
    param([string]$Huella)
    $limite = (Get-Date).AddMinutes(2)
    while ($true) {
        $estado = Estado-Https -Direccion 'localhost' -Puerto $Puerto -Huella $Huella
        if ($estado.Huella -and $estado.Huella -ne $Huella) { Fallar "El servidor presentó otro certificado ($($estado.Huella))." }
        if ($estado.Codigo -eq 302 -and $estado.Cabeceras -match '(?im)^location:\s*/asistente/') {
            Paso "https://localhost:$Puerto/ presenta el certificado de la huella y redirige al asistente"
            return
        }
        if ((Get-Date) -gt $limite) { Fallar "https://localhost:$Puerto/ no redirigió al asistente. Respuesta: $($estado.Codigo) $($estado.Cabeceras)" }
        Start-Sleep -Seconds 3
    }
}

function Comprobar-Puerto8000 {
    $escuchas = @(Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue)
    if ($escuchas.Count -eq 0) { Fallar 'Nada escucha en el puerto 8000.' }
    foreach ($e in $escuchas) {
        if ($e.LocalAddress -ne '127.0.0.1') { Fallar "El puerto 8000 escucha en $($e.LocalAddress)." }
    }
    Paso 'El puerto 8000 solo escucha en 127.0.0.1'
}

function Reglas {
    param([string]$Ruta)
    return @((Get-Acl -LiteralPath $Ruta).GetAccessRules($true, $true, [System.Security.Principal.SecurityIdentifier]))
}

function Comprobar-Permisos {
    $permitidos = @('S-1-5-32-544', 'S-1-5-18', 'S-1-5-19')
    foreach ($ruta in @($Datos, $Instancia, (Join-Path $Instancia 'configuracion.json'))) {
        foreach ($regla in (Reglas $ruta)) {
            $sid = $regla.IdentityReference.Value
            if ($regla.AccessControlType -eq 'Allow' -and $permitidos -notcontains $sid) { Fallar "$ruta da acceso a $sid." }
        }
    }
    $escritura = Reglas $Programa | Where-Object {
        $_.IdentityReference.Value -eq 'S-1-5-19' -and $_.AccessControlType -eq 'Allow' -and ($_.FileSystemRights -band [System.Security.AccessControl.FileSystemRights]::Write)
    }
    if (@($escritura).Count -gt 0) { Fallar 'La cuenta del servicio puede escribir en la carpeta del programa.' }
    Paso 'Permisos de la instancia y del programa correctos'
}

function Comprobar-Firewall {
    $regla = Get-NetFirewallRule -Name 'Ariasmos-HTTPS' -ErrorAction SilentlyContinue
    if ($null -eq $regla) { Fallar 'No existe la regla de firewall Ariasmos-HTTPS.' }
    if ($regla.Direction -ne 'Inbound' -or $regla.Action -ne 'Allow' -or $regla.Enabled -ne 'True') { Fallar 'La regla de firewall no es de entrada, permitida y activa.' }
    $puertos = $regla | Get-NetFirewallPortFilter
    if ($puertos.Protocol -ne 'TCP' -or "$($puertos.LocalPort)" -ne "$Puerto") { Fallar "La regla de firewall no es TCP $Puerto ($($puertos.Protocol) $($puertos.LocalPort))." }
    $direcciones = $regla | Get-NetFirewallAddressFilter
    if ("$($direcciones.RemoteAddress)" -ne 'LocalSubnet') { Fallar "La regla de firewall no está limitada a la red local ($($direcciones.RemoteAddress))." }
    Paso "Regla de firewall TCP $Puerto limitada a la red local"
}

function Comprobar-SinSecretos {
    $configuracion = Get-Content -LiteralPath (Join-Path $Instancia 'configuracion.json') -Raw | ConvertFrom-Json
    $claves = @('clave_django', 'clave_matricula', 'clave_auditoria', 'clave_respaldo', 'clave_secretos') | ForEach-Object { [string]$configuracion.$_ } | Where-Object { $_ }
    $archivos = @(Get-ChildItem -LiteralPath (Join-Path $Programa 'servicios') -Filter '*.xml') + @(Get-Item -LiteralPath (Join-Path $Datos 'caddy\caddy.json')) + @(Get-Item -LiteralPath $Conexion) + @(Get-ChildItem -LiteralPath $Registros -File)
    foreach ($archivo in $archivos) {
        $texto = "$(Get-Content -LiteralPath $archivo.FullName -Raw)"
        foreach ($clave in $claves) { if ($texto.Contains($clave)) { Fallar "$($archivo.FullName) contiene una clave de la instancia." } }
    }
    Paso 'Ninguna clave en XML, configuración de Caddy, archivo de conexión ni registros'
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
}))
'@
    $script = Join-Path $env:TEMP 'ariasmos-analizar.py'
    Set-Content -LiteralPath $script -Value $codigo -Encoding Ascii
    $salida = & $python -I $script $Ruta
    if ($LASTEXITCODE -ne 0) { Fallar "No se pudo analizar el certificado $Ruta." }
    return ($salida -join '') | ConvertFrom-Json
}

function Comprobar-Certificado {
    param([string]$Huella)
    $servidor = Join-Path $Datos 'caddy\servidor.crt'
    if ((Huella-Sha256 -Ruta $servidor) -ne $Huella) { Fallar 'La huella de conexion.json no es la del certificado del servidor.' }
    $certificado = Leer-Certificado -Ruta $servidor
    foreach ($almacen in @('Cert:\LocalMachine\Root', 'Cert:\CurrentUser\Root', 'Cert:\LocalMachine\CA', 'Cert:\LocalMachine\TrustedPeople')) {
        if (@(Get-ChildItem -Path $almacen -ErrorAction SilentlyContinue | Where-Object { $_.Thumbprint -eq $certificado.Thumbprint -or $_.Subject -like 'CN=Ariasmos *' }).Count -gt 0) { Fallar "El certificado del servidor está instalado en $almacen." }
    }
    Paso 'El certificado del servidor no está en ningún almacén de Windows'
    $anterior = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $salida = (& curl.exe -sS -o NUL -w '%{http_code}' --max-time 15 "https://localhost:$Puerto/" 2>&1 | ForEach-Object { "$_" }) -join ' '
    $codigo = $LASTEXITCODE
    $ErrorActionPreference = $anterior
    if ($codigo -eq 0) { Fallar "Windows confía en el certificado del servidor (curl.exe respondió $salida)." }
    Paso "Windows no confía en el certificado (curl.exe con Schannel lo rechaza: código $codigo)"
    foreach ($nombre in @('localhost', $Equipo, '127.0.0.1') | Select-Object -Unique) {
        $estado = Estado-Https -Direccion $nombre -Puerto $Puerto -Huella $Huella
        if ($estado.Huella -ne $Huella) { Fallar "Por $nombre el servidor presentó otro certificado ($($estado.Huella))." }
        if ($estado.Codigo -notin @(200, 302)) { Fallar "Por $nombre el servidor respondió $($estado.Codigo): $($estado.Cabeceras)" }
        Paso "Por $nombre el servidor presenta el certificado de la huella (HTTP $($estado.Codigo))"
    }
    $a = Analizar-Certificado -Ruta $servidor
    if ($a.ca -or -not $a.bc_critica) { Fallar 'El certificado es de autoridad o su basicConstraints no es crítica.' }
    if ($a.firma_certificados -or -not $a.firma_digital -or -not $a.servidor) { Fallar 'El uso de clave del certificado no es solo de servidor.' }
    if ((@($a.dns) -join ',') -ne "$Equipo,localhost" -or (@($a.ips) -join ',') -ne '127.0.0.1') { Fallar "Nombres inesperados en el certificado: $(@($a.dns) -join ',') $(@($a.ips) -join ',')." }
    if ($a.sujeto -ne $a.emisor -or $a.sujeto -ne "CN=Ariasmos $Equipo") { Fallar "Sujeto o emisor inesperado: $($a.sujeto) / $($a.emisor)." }
    if ($a.curva -ne 'secp256r1') { Fallar "La clave no es P-256 ($($a.curva))." }
    if ($a.dias -lt 3649 -or $a.dias -gt 3651) { Fallar "La vigencia no es de unos 10 años ($($a.dias) días)." }
    $clave = Join-Path $Datos 'caddy\servidor.key'
    foreach ($regla in (Reglas $clave)) {
        $sid = $regla.IdentityReference.Value
        if ($regla.AccessControlType -eq 'Allow' -and @('S-1-5-32-544', 'S-1-5-18', 'S-1-5-19') -notcontains $sid) { Fallar "La clave privada da acceso a $sid." }
    }
    $pki = @(Get-ChildItem -LiteralPath (Join-Path $Datos 'caddy') -Recurse -Directory -Filter 'pki' -ErrorAction SilentlyContinue)
    if ($pki.Count -gt 0) { Fallar "Caddy creó una autoridad local: $($pki[0].FullName)." }
    Paso "Certificado del servidor: $($a.sujeto), DNS $(@($a.dns) -join ', '), CA:FALSE, serverAuth, $($a.curva), $($a.dias) días"
}

function Comprobar-Programa {
    param([string]$ModoEsperado)
    if (-not (Test-Path -LiteralPath $Exe)) { Fallar 'No se instaló Ariasmos.exe.' }
    $info = (Get-Item -LiteralPath $Exe).VersionInfo
    $version = (Get-Content -LiteralPath (Join-Path $PSScriptRoot '..\VERSION') -Raw).Trim()
    if ($info.ProductName -ne 'Ariasmos' -or -not "$($info.ProductVersion)".StartsWith($version)) { Fallar "Ariasmos.exe no es Ariasmos $version ($($info.ProductName) $($info.ProductVersion))." }
    $clave = Get-ItemProperty -Path 'HKLM:\SOFTWARE\Ariasmos' -ErrorAction SilentlyContinue
    if ($null -eq $clave -or $clave.Modo -ne $ModoEsperado) { Fallar "El registro no marca la computadora como $ModoEsperado." }
    $shell = New-Object -ComObject WScript.Shell
    foreach ($acceso in @((Join-Path $Escritorio 'Ariasmos.lnk'), (Join-Path ([Environment]::GetFolderPath('CommonPrograms')) 'Ariasmos\Ariasmos.lnk'))) {
        if (-not (Test-Path -LiteralPath $acceso)) { Fallar "Falta el acceso directo $acceso." }
        $destino = $shell.CreateShortcut($acceso).TargetPath
        if ($destino -ne $Exe) { Fallar "El acceso directo $acceso apunta a $destino." }
    }
    $web = @(Get-ChildItem -Path $Escritorio, (Join-Path ([Environment]::GetFolderPath('CommonPrograms')) 'Ariasmos') -Filter '*.url' -ErrorAction SilentlyContinue)
    if ($web.Count -gt 0) { Fallar "Hay accesos directos a direcciones web: $($web.FullName -join ', ')." }
    Paso "Ariasmos.exe $($info.ProductVersion) instalado como $ModoEsperado, con accesos directos solo a Ariasmos.exe"
}

function Ventana {
    param([string]$Nombre, [int]$Esperado = 0)
    if (Test-Path -LiteralPath $RegistroVentana) { Remove-Item -LiteralPath $RegistroVentana -Force }
    $proceso = Start-Process -FilePath $Exe -ArgumentList '--verificar' -PassThru
    if (-not $proceso.WaitForExit(240000)) {
        $proceso.Kill()
        Fallar "Ariasmos.exe --verificar no terminó en 4 minutos ($Nombre)."
    }
    $registro = if (Test-Path -LiteralPath $RegistroVentana) { Get-Content -LiteralPath $RegistroVentana -Raw } else { '(sin registro)' }
    Write-Host "---- registro de Ariasmos.exe ($Nombre) ----"
    Write-Host $registro
    Copy-Item -LiteralPath $RegistroVentana -Destination (Join-Path $Registros "ventana-$Nombre.log") -Force -ErrorAction SilentlyContinue
    if ($proceso.ExitCode -ne $Esperado) { Fallar "Ariasmos.exe --verificar terminó con código $($proceso.ExitCode) y se esperaba $Esperado ($Nombre)." }
    Paso "Ariasmos.exe --verificar: código $($proceso.ExitCode) ($Nombre)"
}

function Ventana-Con {
    param([string]$Nombre, [string]$Contenido, [int]$Esperado)
    $original = [System.IO.File]::ReadAllBytes($Conexion)
    try {
        [System.IO.File]::WriteAllText($Conexion, $Contenido, (New-Object System.Text.UTF8Encoding($false)))
        Ventana -Nombre $Nombre -Esperado $Esperado
    }
    finally {
        [System.IO.File]::WriteAllBytes($Conexion, $original)
    }
}

function Comprobar-Ventana-Rechaza {
    param($Datos)
    $otra = -join ((1..64) | ForEach-Object { '0123456789ABCDEF'[(Get-Random -Maximum 16)] })
    Ventana-Con -Nombre 'huella-distinta' -Contenido ('{{"producto": "ariasmos", "formato": 1, "direccion": "{0}", "puerto": {1}, "huella": "{2}"}}' -f $Datos.direccion, $Datos.puerto, $otra) -Esperado 5
    Ventana-Con -Nombre 'campo-de-mas' -Contenido ('{{"producto": "ariasmos", "formato": 1, "direccion": "{0}", "puerto": {1}, "huella": "{2}", "extra": "x"}}' -f $Datos.direccion, $Datos.puerto, $Datos.huella) -Esperado 2
    Ventana-Con -Nombre 'sin-servidor' -Contenido ('{{"producto": "ariasmos", "formato": 1, "direccion": "{0}", "puerto": 1, "huella": "{1}"}}' -f $Datos.direccion, $Datos.huella) -Esperado 4
    Paso 'Ariasmos.exe se niega a conectar con otra huella, con un archivo alterado y sin servidor'
}

function Iniciar-Servidor-Manual {
    param([string]$Copia, [string]$DatosPrueba)
    Paso "Servidor de prueba con una copia del programa y los datos en $DatosPrueba (para la computadora adicional)"
    $instanciaPrueba = Join-Path $DatosPrueba 'instancia'
    $archivo = Join-Path $instanciaPrueba 'configuracion.json'
    $configuracion = Get-Content -LiteralPath $archivo -Raw -Encoding UTF8 | ConvertFrom-Json
    $configuracion.base_datos = Join-Path $instanciaPrueba (Split-Path -Leaf $configuracion.base_datos)
    $configuracion.certificado_servidor = Join-Path $DatosPrueba 'certificado\ariasmos-servidor.crt'
    [System.IO.File]::WriteAllText($archivo, ($configuracion | ConvertTo-Json -Depth 5), (New-Object System.Text.UTF8Encoding($false)))
    $caddy = Join-Path $DatosPrueba 'caddy\caddy.json'
    $texto = [System.IO.File]::ReadAllText($caddy)
    $texto = $texto.Replace(($Datos -replace '\\', '/'), ($DatosPrueba -replace '\\', '/'))
    [System.IO.File]::WriteAllText($caddy, $texto, (New-Object System.Text.UTF8Encoding($false)))
    $env:COBRO_INSTANCIA = $instanciaPrueba
    $env:PYTHONUTF8 = '1'
    $env:XDG_DATA_HOME = Join-Path $DatosPrueba 'caddy\datos'
    $env:XDG_CONFIG_HOME = Join-Path $DatosPrueba 'caddy\config'
    $web = Start-Process -FilePath (Join-Path $Copia 'python\python.exe') -ArgumentList @('-X', 'utf8', '-B', "`"$(Join-Path $Copia 'app\sistema\manage.py')`"", 'servir', '--host', '127.0.0.1', '--puerto', '8000') -WorkingDirectory (Join-Path $Copia 'app\sistema') -PassThru -WindowStyle Hidden -RedirectStandardOutput (Join-Path $Registros 'web-manual.log') -RedirectStandardError (Join-Path $Registros 'web-manual.err')
    $tls = Start-Process -FilePath (Join-Path $Copia 'caddy\caddy.exe') -ArgumentList @('run', '--config', "`"$caddy`"") -WorkingDirectory (Join-Path $DatosPrueba 'caddy') -PassThru -WindowStyle Hidden -RedirectStandardOutput (Join-Path $Registros 'tls-manual.log') -RedirectStandardError (Join-Path $Registros 'tls-manual.err')
    $script:Procesos = @($web, $tls)
}

function Detener-Servidor-Manual {
    foreach ($proceso in $script:Procesos) {
        if ($null -ne $proceso -and -not $proceso.HasExited) { & taskkill.exe /F /T /PID $proceso.Id | Out-Null }
    }
    $script:Procesos = @()
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
    Instalar -Nombre 'principal' -Extra @('/MODO=principal', "/PUERTO=$Puerto")
    Paso "Nombre del equipo esperado en el certificado: $Equipo"
    Esperar-Servicios
    $principal = Leer-Conexion -Ruta $Conexion
    if ($principal.direccion -ne 'localhost' -or $principal.puerto -ne $Puerto) { Fallar "conexion.json de la principal no es localhost:$Puerto ($($principal.direccion):$($principal.puerto))." }
    Comprobar-Permisos-Conexion
    Comprobar-Asistente -Huella $principal.huella
    Comprobar-Puerto8000
    Comprobar-Permisos
    Comprobar-Firewall
    Comprobar-Certificado -Huella $principal.huella
    Comprobar-Programa -ModoEsperado 'principal'
    if ((Get-ItemProperty -Path 'HKLM:\SOFTWARE\Ariasmos').Puerto -ne $Puerto) { Fallar 'El registro no guarda el puerto.' }
    Ventana -Nombre 'principal'
    Comprobar-Ventana-Rechaza -Datos $principal
    Copiar-Registros
    Comprobar-SinSecretos

    $antes = Get-Content -LiteralPath (Join-Path $Instancia 'configuracion.json') -Raw | ConvertFrom-Json
    Instalar -Nombre 'actualizacion'
    Esperar-Servicios
    $actualizada = Leer-Conexion -Ruta $Conexion
    if ($actualizada.huella -ne $principal.huella -or $actualizada.puerto -ne $Puerto) { Fallar 'La actualización cambió el certificado o el puerto sin que hiciera falta.' }
    Comprobar-Asistente -Huella $principal.huella
    Comprobar-Firewall
    $despues = Get-Content -LiteralPath (Join-Path $Instancia 'configuracion.json') -Raw | ConvertFrom-Json
    foreach ($propiedad in $antes.PSObject.Properties) {
        $nuevo = $despues.PSObject.Properties[$propiedad.Name]
        if ($null -eq $nuevo) { Fallar "La actualización quitó la clave $($propiedad.Name) de configuracion.json." }
        if (($propiedad.Value | ConvertTo-Json -Compress -Depth 5) -ne ($nuevo.Value | ConvertTo-Json -Compress -Depth 5)) { Fallar "La actualización cambió $($propiedad.Name) en configuracion.json." }
    }
    $copias = @(Get-ChildItem -LiteralPath (Join-Path $Datos 'antes-de-actualizar') -Directory)
    if ($copias.Count -lt 1) { Fallar 'La actualización no guardó la copia de la instancia.' }
    Ventana -Nombre 'actualizacion'
    Paso 'La actualización conservó certificado, puerto y configuración'

    $copia = Join-Path $env:TEMP ('ariasmos-servidor-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $copia -Force | Out-Null
    foreach ($parte in @('python', 'app', 'caddy', 'site-packages')) {
        Copy-Item -LiteralPath (Join-Path $Programa $parte) -Destination (Join-Path $copia $parte) -Recurse -Force
    }
    $paraAdicional = Join-Path $env:TEMP ('ariasmos-conexion-' + [guid]::NewGuid().ToString('N'))
    $salida = & (Get-Process -Id $PID).Path -NoProfile -NonInteractive -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'herramientas\conexion.ps1') -Accion Generar -Direccion $Equipo -Puerto $Puerto -Certificado (Join-Path $Datos 'caddy\servidor.crt') -Datos $paraAdicional
    if ($LASTEXITCODE -ne 0) { Fallar "No se pudo generar el archivo de conexión para la adicional: $salida" }

    Desinstalar -Nombre 'principal'
    foreach ($nombre in $Servicios) {
        if ($null -ne (Get-Service -Name $nombre -ErrorAction SilentlyContinue)) { Fallar "El servicio $nombre sigue instalado." }
    }
    if ($null -ne (Get-NetFirewallRule -Name 'Ariasmos-HTTPS' -ErrorAction SilentlyContinue)) { Fallar 'La regla de firewall sigue existiendo.' }
    if (-not (Test-Path -LiteralPath (Join-Path $Instancia 'configuracion.json'))) { Fallar 'La desinstalación borró los datos.' }
    if (Test-Path -LiteralPath $Exe) { Fallar 'La desinstalación dejó Ariasmos.exe.' }
    Paso 'Desinstalación de la principal correcta: sin servicios ni regla, datos conservados'

    $datosPrueba = Join-Path $env:TEMP ('ariasmos-datos-' + [guid]::NewGuid().ToString('N'))
    Move-Item -LiteralPath $Datos -Destination $datosPrueba
    Iniciar-Servidor-Manual -Copia $copia -DatosPrueba $datosPrueba
    $limite = (Get-Date).AddMinutes(2)
    while ((Estado-Https -Direccion 'localhost' -Puerto $Puerto -Huella $principal.huella).Codigo -notin @(200, 302)) {
        if ((Get-Date) -gt $limite) { Fallar 'El servidor de prueba no respondió.' }
        Start-Sleep -Seconds 2
    }
    Instalar -Nombre 'adicional' -Extra @('/MODO=adicional', "/CONEXION=$(Join-Path $paraAdicional 'conexion.json')")
    foreach ($ausente in @('python', 'app', 'servicios', 'caddy', 'herramientas', 'site-packages')) {
        if (Test-Path -LiteralPath (Join-Path $Programa $ausente)) { Fallar "La computadora adicional recibió $ausente." }
    }
    foreach ($nombre in $Servicios) {
        if ($null -ne (Get-Service -Name $nombre -ErrorAction SilentlyContinue)) { Fallar "La computadora adicional instaló el servicio $nombre." }
    }
    if ($null -ne (Get-NetFirewallRule -Name 'Ariasmos-HTTPS' -ErrorAction SilentlyContinue)) { Fallar 'La computadora adicional creó una regla de firewall.' }
    $adicional = Leer-Conexion -Ruta $Conexion
    if ($adicional.direccion -ne $Equipo -or $adicional.puerto -ne $Puerto -or $adicional.huella -ne $principal.huella) { Fallar "conexion.json de la adicional no es el elegido ($($adicional.direccion):$($adicional.puerto))." }
    Comprobar-Permisos-Conexion
    Comprobar-Programa -ModoEsperado 'adicional'
    if ($null -ne (Get-ItemProperty -Path 'HKLM:\SOFTWARE\Ariasmos' -Name 'Puerto' -ErrorAction SilentlyContinue)) { Fallar 'La adicional guardó un puerto de servidor.' }
    Ventana -Nombre 'adicional'
    $ip = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } | Select-Object -First 1
    if ($null -ne $ip) {
        Ventana-Con -Nombre 'adicional-por-ip' -Contenido ('{{"producto": "ariasmos", "formato": 1, "direccion": "{0}", "puerto": {1}, "huella": "{2}"}}' -f $ip.IPAddress, $Puerto, $principal.huella) -Esperado 0
    }
    Comprobar-Ventana-Rechaza -Datos $adicional
    $acl = Get-Acl -LiteralPath $Datos
    foreach ($regla in $acl.GetAccessRules($true, $true, [System.Security.Principal.SecurityIdentifier])) {
        if ($regla.AccessControlType -eq 'Allow' -and @('S-1-5-32-544', 'S-1-5-18', 'S-1-5-32-545') -notcontains $regla.IdentityReference.Value) { Fallar "La carpeta de datos de la adicional da acceso a $($regla.IdentityReference.Value)." }
    }
    Paso 'La computadora adicional solo tiene Ariasmos.exe y se conecta a la principal comprobando la huella'

    Desinstalar -Nombre 'adicional'
    if (Test-Path -LiteralPath $Conexion) { Fallar 'La desinstalación de la adicional dejó conexion.json.' }
    if (Test-Path -LiteralPath 'HKLM:\SOFTWARE\Ariasmos') { Fallar 'La desinstalación dejó la clave del registro.' }
    if (Test-Path -LiteralPath (Join-Path $Escritorio 'Ariasmos.lnk')) { Fallar 'La desinstalación dejó el acceso directo.' }
    Paso 'Desinstalación de la adicional correcta'
}
catch {
    $resultado = 1
    Write-Host "PRUEBA DE HUMO FALLIDA: $($_.Exception.Message)"
    Copiar-Registros
    Mostrar-Registros
}
finally {
    Detener-Servidor-Manual
    Copiar-Registros
}
exit $resultado
