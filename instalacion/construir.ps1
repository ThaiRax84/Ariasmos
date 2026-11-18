param(
    [string]$Python = 'python',
    [string]$Salida = (Join-Path (Split-Path -Parent $PSScriptRoot) 'build')
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Raiz = Split-Path -Parent $PSScriptRoot
$Paquete = Join-Path $Salida 'Ariasmos'
$Descargas = Join-Path $Salida 'descargas'
$Registro = Join-Path $Salida 'construir.log'

function Paso {
    param([Parameter(Mandatory = $true)][string]$Mensaje)
    $linea = '{0:yyyy-MM-dd HH:mm:ss} {1}' -f (Get-Date), $Mensaje
    Add-Content -LiteralPath $Registro -Value $linea -Encoding UTF8
    Write-Host $linea
}

function Ejecutar {
    param([Parameter(Mandatory = $true)][string]$Archivo, [string[]]$Argumentos = @())
    Paso ("  > {0} {1}" -f (Split-Path -Leaf $Archivo), ($Argumentos -join ' '))
    $anterior = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $salida = & $Archivo @Argumentos 2>&1 | ForEach-Object { "$_" }
        $codigo = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $anterior
    }
    foreach ($renglon in @($salida)) { if ($renglon) { Add-Content -LiteralPath $Registro -Value "    $renglon" -Encoding UTF8 } }
    if ($codigo -ne 0) {
        @($salida) | Select-Object -Last 40 | ForEach-Object { Write-Host "    $_" }
        throw ('Falló {0} (código {1}).' -f (Split-Path -Leaf $Archivo), $codigo)
    }
    return , @($salida)
}

function Hash-De {
    param([Parameter(Mandatory = $true)][string]$Ruta, [string]$Algoritmo = 'SHA256')
    return (Get-FileHash -LiteralPath $Ruta -Algorithm $Algoritmo).Hash.ToLowerInvariant()
}

function Descargar {
    param([Parameter(Mandatory = $true)][string]$Nombre, [Parameter(Mandatory = $true)]$Dependencia)
    $url = [string]$Dependencia.url
    if (-not $url.StartsWith('https://')) { throw "La URL de $Nombre no es https: $url" }
    $archivo = Join-Path $Descargas ([System.IO.Path]::GetFileName(([Uri]$url).AbsolutePath))
    if (-not (Test-Path -LiteralPath $archivo)) {
        Paso "Descargando $Nombre $($Dependencia.version) de $url"
        $temporal = "$archivo.parcial"
        Invoke-WebRequest -Uri $url -OutFile $temporal -UseBasicParsing
        Move-Item -LiteralPath $temporal -Destination $archivo -Force
    }
    $calculado = Hash-De -Ruta $archivo
    $esperado = ([string]$Dependencia.sha256).ToLowerInvariant()
    if (-not $esperado) {
        $detalle = "SHA-256 calculado: $calculado"
        if ($Dependencia.PSObject.Properties.Name -contains 'md5_oficial') {
            $md5 = Hash-De -Ruta $archivo -Algoritmo 'MD5'
            $coincide = if ($md5 -eq ([string]$Dependencia.md5_oficial).ToLowerInvariant()) { 'coincide' } else { 'NO coincide' }
            $detalle += " · MD5 calculado: $md5 ($coincide con el MD5 oficial $($Dependencia.md5_oficial))"
        }
        throw "dependencias.json no trae el SHA-256 de $Nombre. $detalle. Comprueba el archivo y fija el SHA-256 en instalacion/dependencias.json."
    }
    if ($calculado -ne $esperado) {
        Remove-Item -LiteralPath $archivo -Force
        throw "El SHA-256 de $Nombre no coincide: esperado $esperado, calculado $calculado. Se borró la descarga."
    }
    Paso "SHA-256 verificado de $Nombre ($calculado)"
    return $archivo
}

function Descargar-Firmado {
    param([Parameter(Mandatory = $true)][string]$Nombre, [Parameter(Mandatory = $true)]$Dependencia)
    $url = [string]$Dependencia.url
    if (-not $url.StartsWith('https://go.microsoft.com/')) { throw "La URL de $Nombre no es de go.microsoft.com: $url" }
    $archivo = Join-Path $Descargas ([string]$Dependencia.archivo)
    if (-not (Test-Path -LiteralPath $archivo)) {
        Paso "Descargando $Nombre de $url"
        $temporal = "$archivo.parcial"
        Invoke-WebRequest -Uri $url -OutFile $temporal -UseBasicParsing
        Move-Item -LiteralPath $temporal -Destination $archivo -Force
    }
    $firma = Get-AuthenticodeSignature -LiteralPath $archivo
    $sujeto = if ($null -ne $firma.SignerCertificate) { $firma.SignerCertificate.Subject } else { '' }
    if ($firma.Status -ne 'Valid' -or $sujeto -notmatch ('(^|, )O=' + [regex]::Escape([string]$Dependencia.firmante) + '(,|$)') -or $sujeto -notmatch '(^|, )CN=Microsoft Corporation(,|$)') {
        Remove-Item -LiteralPath $archivo -Force
        throw "La firma de $Nombre no es válida o no es de $($Dependencia.firmante) (estado $($firma.Status), firmante '$sujeto'). Se borró la descarga."
    }
    Paso "Firma Authenticode verificada de ${Nombre}: $sujeto ($(Hash-De -Ruta $archivo))"
    return $archivo
}

function Copiar-Codigo {
    param([Parameter(Mandatory = $true)][string]$Origen, [Parameter(Mandatory = $true)][string]$Destino)
    New-Item -ItemType Directory -Path $Destino -Force | Out-Null
    $base = (Resolve-Path -LiteralPath $Origen).ProviderPath
    foreach ($elemento in Get-ChildItem -LiteralPath $base -Recurse -File) {
        $relativa = $elemento.FullName.Substring($base.Length).TrimStart('\', '/')
        if ($relativa -match '(^|[\\/])(__pycache__|\.pytest_cache)([\\/]|$)' -or $elemento.Extension -in @('.pyc', '.sqlite3', '.log')) { continue }
        $final = Join-Path $Destino $relativa
        New-Item -ItemType Directory -Path (Split-Path -Parent $final) -Force | Out-Null
        Copy-Item -LiteralPath $elemento.FullName -Destination $final -Force
    }
}

try {
    New-Item -ItemType Directory -Path $Salida -Force | Out-Null
    New-Item -ItemType Directory -Path $Descargas -Force | Out-Null
    Set-Content -LiteralPath $Registro -Value '' -Encoding UTF8
    $version = (Get-Content -LiteralPath (Join-Path $Raiz 'VERSION') -Raw).Trim()
    if ($version -notmatch '^\d+\.\d+\.\d+$') { throw "VERSION no es válida: '$version'" }
    Paso "Construyendo Ariasmos $version"

    $dependencias = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'dependencias.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($nombre in @('python', 'winsw', 'caddy', 'webview2')) {
        if (-not ($dependencias.PSObject.Properties.Name -contains $nombre)) { throw "dependencias.json no trae $nombre." }
    }

    $versionPython = Ejecutar -Archivo $Python -Argumentos @('-c', "import sys, struct; print('%d.%d %d' % (sys.version_info[0], sys.version_info[1], struct.calcsize('P') * 8))")
    if (($versionPython -join '').Trim() -ne '3.12 64') { throw "Se necesita Python 3.12 de 64 bits para instalar las dependencias; se encontró: $($versionPython -join ' ')" }

    $zipPython = Descargar -Nombre 'python' -Dependencia $dependencias.python
    $exeWinsw = Descargar -Nombre 'winsw' -Dependencia $dependencias.winsw
    $zipCaddy = Descargar -Nombre 'caddy' -Dependencia $dependencias.caddy
    Descargar-Firmado -Nombre 'webview2' -Dependencia $dependencias.webview2 | Out-Null

    Paso 'Programa de escritorio'
    $escritorio = Join-Path $Salida 'escritorio'
    $exe = Join-Path $escritorio 'Ariasmos.exe'
    if (-not (Test-Path -LiteralPath $exe)) { throw "Falta ${exe}: compila escritorio/Ariasmos antes de construir el paquete." }
    $info = (Get-Item -LiteralPath $exe).VersionInfo
    if ($info.ProductName -ne 'Ariasmos' -or -not "$($info.ProductVersion)".StartsWith($version)) { throw "Ariasmos.exe no es Ariasmos $version ($($info.ProductName) $($info.ProductVersion))." }
    foreach ($necesario in @('Ariasmos.Nucleo.dll', 'Microsoft.Web.WebView2.Core.dll', 'Microsoft.Web.WebView2.WinForms.dll')) {
        if (-not (Test-Path -LiteralPath (Join-Path $escritorio $necesario))) { throw "Falta $necesario junto a Ariasmos.exe." }
    }
    Paso "Ariasmos.exe $($info.ProductVersion) listo"

    if (Test-Path -LiteralPath $Paquete) {
        Paso 'Borrando la construcción anterior'
        Remove-Item -LiteralPath $Paquete -Recurse -Force
    }
    New-Item -ItemType Directory -Path $Paquete -Force | Out-Null

    Paso 'Python embebido'
    $carpetaPython = Join-Path $Paquete 'python'
    Expand-Archive -LiteralPath $zipPython -DestinationPath $carpetaPython -Force
    $pth = Get-ChildItem -LiteralPath $carpetaPython -Filter 'python*._pth'
    if (@($pth).Count -ne 1) { throw 'El Python embebido no trae exactamente un archivo ._pth.' }
    if ($pth[0].Name -ne 'python312._pth') { throw "Se esperaba python312._pth y llegó $($pth[0].Name)." }
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'python312._pth') -Destination $pth[0].FullName -Force
    $pythonEmbebido = Join-Path $carpetaPython 'python.exe'

    Paso 'Dependencias (solo ruedas binarias, verificadas por SHA-256)'
    $sitio = Join-Path $Paquete 'site-packages'
    Ejecutar -Archivo $Python -Argumentos @('-m', 'pip', 'install', '--disable-pip-version-check', '--no-cache-dir', '--only-binary=:all:', '--require-hashes', '--no-deps', '--target', $sitio, '-r', (Join-Path $PSScriptRoot 'requisitos-windows.txt')) | Out-Null
    Get-ChildItem -LiteralPath $sitio -Directory -Filter 'bin' -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force

    Paso 'Código de la aplicación'
    $app = Join-Path $Paquete 'app'
    foreach ($carpeta in @('sistema', 'nucleo', 'datos', 'plantillas')) {
        Copiar-Codigo -Origen (Join-Path $Raiz $carpeta) -Destino (Join-Path $app $carpeta)
    }
    foreach ($archivo in @('VERSION', 'LICENSE')) {
        Copy-Item -LiteralPath (Join-Path $Raiz $archivo) -Destination (Join-Path $app $archivo) -Force
    }

    Paso 'Servicios (WinSW) y TLS (Caddy)'
    $servicios = Join-Path $Paquete 'servicios'
    New-Item -ItemType Directory -Path $servicios -Force | Out-Null
    foreach ($nombre in @('AriasmosWeb', 'AriasmosTrabajador', 'AriasmosTLS')) {
        Copy-Item -LiteralPath $exeWinsw -Destination (Join-Path $servicios "$nombre.exe") -Force
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot "servicios\$nombre.xml") -Destination (Join-Path $servicios "$nombre.xml") -Force
    }
    $carpetaCaddy = Join-Path $Paquete 'caddy'
    $temporalCaddy = Join-Path $Descargas 'caddy-extraido'
    if (Test-Path -LiteralPath $temporalCaddy) { Remove-Item -LiteralPath $temporalCaddy -Recurse -Force }
    Expand-Archive -LiteralPath $zipCaddy -DestinationPath $temporalCaddy -Force
    New-Item -ItemType Directory -Path $carpetaCaddy -Force | Out-Null
    foreach ($archivo in @('caddy.exe', 'LICENSE')) {
        $origen = Join-Path $temporalCaddy $archivo
        if (-not (Test-Path -LiteralPath $origen)) { throw "El zip de Caddy no trae $archivo." }
        Copy-Item -LiteralPath $origen -Destination (Join-Path $carpetaCaddy $archivo) -Force
    }
    $versionCaddy = Ejecutar -Archivo (Join-Path $carpetaCaddy 'caddy.exe') -Argumentos @('version')
    if (($versionCaddy -join ' ') -notmatch [regex]::Escape("v$($dependencias.caddy.version)")) { throw "caddy.exe no es la versión $($dependencias.caddy.version): $($versionCaddy -join ' ')" }

    Paso 'Herramientas del instalador'
    $herramientas = Join-Path $Paquete 'herramientas'
    Copiar-Codigo -Origen (Join-Path $PSScriptRoot 'herramientas') -Destino $herramientas

    Paso 'Precompilando el código de Python'
    Ejecutar -Archivo $pythonEmbebido -Argumentos @('-m', 'compileall', '-q', '--invalidation-mode', 'unchecked-hash', $app, $sitio) | Out-Null

    Paso 'Comprobando el paquete con el Python embebido'
    $importaciones = "import django, argon2, waitress, reportlab, PIL, pypdf, segno, cryptography, openpyxl, charset_normalizer, tzdata, sqlite3, zoneinfo; zoneinfo.ZoneInfo('America/Mexico_City'); print('ok')"
    Ejecutar -Archivo $pythonEmbebido -Argumentos @('-c', $importaciones) | Out-Null
    $manage = Join-Path $app 'sistema\manage.py'
    $mostrada = Ejecutar -Archivo $pythonEmbebido -Argumentos @('-X', 'utf8', $manage, 'version')
    if (($mostrada -join '').Trim() -ne "Ariasmos $version") { throw "manage.py version mostró '$($mostrada -join ' ')' y se esperaba 'Ariasmos $version'." }
    $instanciaPrueba = Join-Path $Salida 'instancia-de-prueba'
    if (Test-Path -LiteralPath $instanciaPrueba) { Remove-Item -LiteralPath $instanciaPrueba -Recurse -Force }
    $env:COBRO_INSTANCIA = $instanciaPrueba
    try {
        Ejecutar -Archivo $pythonEmbebido -Argumentos @('-X', 'utf8', $manage, 'inicializar', '--host', 'construccion') | Out-Null
        Ejecutar -Archivo $pythonEmbebido -Argumentos @('-X', 'utf8', $manage, 'migrate', '--noinput') | Out-Null
        Ejecutar -Archivo $pythonEmbebido -Argumentos @('-X', 'utf8', $manage, 'check', '--deploy', '--fail-level', 'WARNING') | Out-Null
    }
    finally {
        Remove-Item Env:\COBRO_INSTANCIA -ErrorAction SilentlyContinue
        if (Test-Path -LiteralPath $instanciaPrueba) { Remove-Item -LiteralPath $instanciaPrueba -Recurse -Force }
    }
    Get-ChildItem -LiteralPath $Paquete -Recurse -Include '*.sqlite3', '*.sqlite3-wal', '*.sqlite3-shm', 'configuracion.json' | ForEach-Object { throw "El paquete contiene un archivo que no debe llevar: $($_.FullName)" }

    Paso "Paquete listo en $Paquete"
    exit 0
}
catch {
    Paso "ERROR: $($_.Exception.Message)"
    exit 1
}
