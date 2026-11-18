param(
    [Parameter(Mandatory = $true)][ValidateSet('Validar', 'Instalar', 'Generar')][string]$Accion,
    [string]$Archivo = '',
    [string]$Datos = (Join-Path $env:ProgramData 'Ariasmos'),
    [string]$Direccion = 'localhost',
    [int]$Puerto = 443,
    [string]$Certificado = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$TamanoMaximo = 2048
$Formato = '^\s*\{\s*"producto"\s*:\s*"ariasmos"\s*,\s*"formato"\s*:\s*1\s*,\s*"direccion"\s*:\s*"([a-z0-9.-]{1,253})"\s*,\s*"puerto"\s*:\s*([1-9][0-9]{0,4})\s*,\s*"huella"\s*:\s*"([0-9A-F]{64})"\s*\}\s*$'

function Direccion-Valida {
    param([string]$Texto)
    if (-not $Texto -or $Texto.Length -gt 253 -or $Texto -cne $Texto.ToLowerInvariant()) { return $false }
    $partes = $Texto.Split('.')
    if ($partes.Count -eq 4 -and @($partes | Where-Object { $_ -match '^(0|[1-9][0-9]{0,2})$' -and [int]$_ -le 255 }).Count -eq 4) { return $true }
    foreach ($parte in $partes) {
        if ($parte -notmatch '^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$') { return $false }
    }
    if (@($partes | Where-Object { $_ -notmatch '^[0-9]+$' }).Count -eq 0) { return $false }
    if ($partes.Count -gt 1 -and $partes[-1] -match '^[0-9]') { return $false }
    return $true
}

function Leer-Conexion {
    param([string]$Ruta)
    if (-not $Ruta -or -not (Test-Path -LiteralPath $Ruta -PathType Leaf)) { throw 'No existe el archivo de conexión.' }
    $bytes = [System.IO.File]::ReadAllBytes($Ruta)
    if ($bytes.Length -eq 0 -or $bytes.Length -gt $TamanoMaximo) { throw 'El archivo de conexión está vacío o es demasiado grande.' }
    $inicio = 0
    if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) { $inicio = 3 }
    try {
        $texto = (New-Object System.Text.UTF8Encoding($false, $true)).GetString($bytes, $inicio, $bytes.Length - $inicio)
    }
    catch {
        throw 'El archivo de conexión no es UTF-8.'
    }
    $coincidencia = [regex]::Match($texto, $Formato)
    if (-not $coincidencia.Success) { throw 'El archivo no es un archivo de conexión de Ariasmos o tiene campos de más o de menos.' }
    $direccionLeida = $coincidencia.Groups[1].Value
    $puertoLeido = [int]$coincidencia.Groups[2].Value
    if (-not (Direccion-Valida $direccionLeida)) { throw 'La dirección del servidor no es válida.' }
    if ($puertoLeido -lt 1 -or $puertoLeido -gt 65535) { throw 'El puerto no es válido.' }
    return [pscustomobject]@{ Direccion = $direccionLeida; Puerto = $puertoLeido; Huella = $coincidencia.Groups[3].Value }
}

function Texto-Conexion {
    param($Conexion)
    return ('{{"producto": "ariasmos", "formato": 1, "direccion": "{0}", "puerto": {1}, "huella": "{2}"}}' -f $Conexion.Direccion, $Conexion.Puerto, $Conexion.Huella) + "`n"
}

function Escribir-Conexion {
    param($Conexion, [string]$Carpeta)
    if (-not (Test-Path -LiteralPath $Carpeta)) {
        New-Item -ItemType Directory -Path $Carpeta -Force | Out-Null
        & icacls.exe $Carpeta /inheritance:r /grant:r '*S-1-5-32-544:(OI)(CI)F' '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-545:(OI)(CI)RX' /Q | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "No se pudieron fijar los permisos de $Carpeta." }
    }
    $destino = Join-Path $Carpeta 'conexion.json'
    $temporal = Join-Path $Carpeta ('.conexion-{0}.tmp' -f [guid]::NewGuid().ToString('N'))
    [System.IO.File]::WriteAllText($temporal, (Texto-Conexion $Conexion), (New-Object System.Text.UTF8Encoding($false)))
    Move-Item -LiteralPath $temporal -Destination $destino -Force
    & icacls.exe $destino /inheritance:r /grant:r '*S-1-5-32-544:F' '*S-1-5-18:F' '*S-1-5-32-545:R' /Q | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "No se pudieron fijar los permisos de $destino." }
    $comprobada = Leer-Conexion -Ruta $destino
    if ($comprobada.Huella -ne $Conexion.Huella) { throw 'El archivo de conexión escrito no coincide.' }
    return $destino
}

try {
    switch ($Accion) {
        'Validar' {
            $conexion = Leer-Conexion -Ruta $Archivo
        }
        'Instalar' {
            $conexion = Leer-Conexion -Ruta $Archivo
            Escribir-Conexion -Conexion $conexion -Carpeta $Datos | Out-Null
        }
        'Generar' {
            if (-not (Direccion-Valida $Direccion)) { throw 'La dirección no es válida.' }
            if ($Puerto -lt 1 -or $Puerto -gt 65535) { throw 'El puerto no es válido.' }
            if (-not $Certificado -or -not (Test-Path -LiteralPath $Certificado -PathType Leaf)) { throw 'No existe el certificado del servidor.' }
            $objeto = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2(, [System.IO.File]::ReadAllBytes($Certificado))
            $sha = [System.Security.Cryptography.SHA256]::Create()
            try {
                $huella = -join ($sha.ComputeHash($objeto.RawData) | ForEach-Object { $_.ToString('X2') })
            }
            finally {
                $sha.Dispose()
            }
            $conexion = [pscustomobject]@{ Direccion = $Direccion; Puerto = $Puerto; Huella = $huella }
            Escribir-Conexion -Conexion $conexion -Carpeta $Datos | Out-Null
        }
    }
    [Console]::Out.WriteLine(('CONEXION: {0}:{1} {2}' -f $conexion.Direccion, $conexion.Puerto, $conexion.Huella))
    exit 0
}
catch {
    [Console]::Out.WriteLine("ERROR-CONEXION: $($_.Exception.Message)")
    exit 1
}
