param(
    [string]$Programa = (Split-Path -Parent $PSScriptRoot),
    [string]$Datos = (Join-Path $env:ProgramData 'Ariasmos')
)

. (Join-Path $PSScriptRoot 'comun.ps1')

$R = Rutas -Programa $Programa -Datos $Datos
try {
    Write-Host 'Esta utilidad deja que el sistema escriba cortes o respaldos en una carpeta tuya.'
    Write-Host 'Ejemplo: D:\Respaldos, o una carpeta de OneDrive dentro de tu usuario'
    Write-Host ''
    $texto = (Read-Host 'Escribe o pega la ruta completa de la carpeta').Trim().Trim('"')
    if (-not $texto) { throw 'No escribiste ninguna ruta.' }
    if (-not [System.IO.Path]::IsPathRooted($texto) -or $texto.StartsWith('\\')) { throw 'Escribe una ruta completa de este equipo, que empiece con la letra de la unidad (por ejemplo C:\).' }
    if (-not (Test-Path -LiteralPath $texto)) {
        New-Item -ItemType Directory -Path $texto -Force | Out-Null
        Write-Host "Se creó la carpeta $texto"
    }
    $carpeta = (Resolve-Path -LiteralPath $texto).ProviderPath
    if (-not (Test-Path -LiteralPath $carpeta -PathType Container)) { throw 'La ruta no es una carpeta.' }
    foreach ($prohibida in @($R.Programa, $R.Datos, $env:SystemRoot)) {
        $base = [System.IO.Path]::GetFullPath($prohibida).TrimEnd('\') + '\'
        $esta = [System.IO.Path]::GetFullPath($carpeta).TrimEnd('\') + '\'
        if ($esta.StartsWith($base, [System.StringComparison]::OrdinalIgnoreCase) -or $base.StartsWith($esta, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "No se puede dar permiso sobre ${carpeta}: está dentro de (o contiene) una carpeta del sistema o del programa."
        }
    }
    Ejecutar -Archivo 'icacls.exe' -Argumentos @($carpeta, '/grant', "*$($script:SidServicio):(OI)(CI)M", '/Q') | Out-Null
    Write-Host ''
    Write-Host "Listo: el sistema ya puede escribir en $carpeta."
    Write-Host 'Vuelve a la pantalla de destinos o de respaldo y guarda la carpeta otra vez.'
    exit 0
}
catch {
    Write-Host "ERROR: $($_.Exception.Message)"
    exit 1
}
