param(
    [string]$Programa = (Split-Path -Parent $PSScriptRoot),
    [string]$Datos = (Join-Path $env:ProgramData 'Ariasmos'),
    [string]$Carpeta = ''
)

. (Join-Path $PSScriptRoot 'comun.ps1')

function Validar-Carpeta {
    param([Parameter(Mandatory = $true)][string]$Texto, [Parameter(Mandatory = $true)]$R, [switch]$Crear)
    if ($Texto.Length -lt 4 -or $Texto.Length -gt 240) { throw 'La ruta es demasiado corta o demasiado larga.' }
    if ($Texto -notmatch '^[A-Za-z]:\\[^\\]') { throw 'Escribe una ruta completa de este equipo, que empiece con la letra de la unidad (por ejemplo D:\Cortes).' }
    if ($Texto.EndsWith('\')) { throw 'La ruta no debe terminar en una diagonal.' }
    foreach ($segmento in $Texto.Substring(3).Split('\')) {
        if (-not $segmento -or $segmento -eq '.' -or $segmento -eq '..') { throw 'La ruta tiene partes vacías, «.» o «..».' }
        if ($segmento -match '[<>:"/|?*~\x00-\x1F]' -or $segmento.EndsWith('.') -or $segmento.EndsWith(' ') -or $segmento.StartsWith(' ')) { throw 'La ruta tiene caracteres que no se aceptan.' }
        if ($segmento -match '^(CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9])(\..*)?$') { throw 'La ruta usa un nombre reservado de Windows.' }
    }
    $unidad = New-Object System.IO.DriveInfo($Texto.Substring(0, 1))
    if (@('Fixed', 'Removable') -notcontains "$($unidad.DriveType)") { throw "La unidad $($unidad.Name) no es un disco de este equipo." }
    if ($Texto -ne [System.IO.Path]::GetFullPath($Texto)) { throw 'La ruta no es una ruta completa normal.' }
    if (-not (Test-Path -LiteralPath $Texto)) {
        if (-not $Crear) { throw 'La carpeta no existe.' }
        $padre = Split-Path -Parent $Texto
        if (-not (Test-Path -LiteralPath $padre -PathType Container)) { throw 'La carpeta que la contiene no existe.' }
        New-Item -ItemType Directory -Path $Texto | Out-Null
        Write-Host "Se creó la carpeta $Texto"
    }
    $elemento = Get-Item -LiteralPath $Texto -Force
    if (-not $elemento.PSIsContainer) { throw 'La ruta no es una carpeta.' }
    $actual = $elemento
    while ($null -ne $actual) {
        if ($actual.Attributes -band [System.IO.FileAttributes]::ReparsePoint) { throw "La ruta pasa por un enlace o una unión ($($actual.FullName)); elige la carpeta real." }
        $actual = $actual.Parent
    }
    $carpeta = $elemento.FullName.TrimEnd('\')
    if ($carpeta -ne $Texto.TrimEnd('\')) { throw 'La ruta no coincide con la carpeta real.' }
    if ($carpeta.Length -le 3) { throw 'No se puede dar permiso sobre una unidad completa.' }
    $protegidas = @($R.Programa, $R.Datos, $env:SystemRoot, ${env:ProgramFiles}, ${env:ProgramFiles(x86)}, $env:ProgramData)
    foreach ($prohibida in $protegidas) {
        if (-not $prohibida) { continue }
        $base = [System.IO.Path]::GetFullPath($prohibida).TrimEnd('\') + '\'
        $esta = $carpeta + '\'
        if ($esta.StartsWith($base, [System.StringComparison]::OrdinalIgnoreCase) -or $base.StartsWith($esta, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "No se puede dar permiso sobre ${carpeta}: está dentro de (o contiene) una carpeta del sistema o del programa."
        }
    }
    return $carpeta
}

$R = Rutas -Programa $Programa -Datos $Datos
try {
    if ($Carpeta) {
        $elegida = Validar-Carpeta -Texto $Carpeta -R $R
    }
    else {
        Write-Host 'Esta utilidad deja que el sistema escriba cortes o respaldos en una carpeta tuya.'
        Write-Host 'Ejemplo: D:\Respaldos, o una carpeta de OneDrive dentro de tu usuario'
        Write-Host ''
        $texto = (Read-Host 'Escribe o pega la ruta completa de la carpeta').Trim().Trim('"')
        if (-not $texto) { throw 'No escribiste ninguna ruta.' }
        $elegida = Validar-Carpeta -Texto $texto -R $R -Crear
    }
    Ejecutar -Archivo 'icacls.exe' -Argumentos @($elegida, '/grant', "*$($script:SidServicio):(OI)(CI)M", '/Q') | Out-Null
    Write-Host ''
    Write-Host "Listo: el sistema ya puede escribir en $elegida."
    Write-Host 'Vuelve a la pantalla de destinos o de respaldo y guarda la carpeta otra vez.'
    exit 0
}
catch {
    Write-Host "ERROR: $($_.Exception.Message)"
    exit 1
}
