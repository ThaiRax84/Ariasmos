param(
    [string]$Programa = (Split-Path -Parent $PSScriptRoot),
    [string]$Datos = (Join-Path $env:ProgramData 'Ariasmos')
)

. (Join-Path $PSScriptRoot 'comun.ps1')

$R = Rutas -Programa $Programa -Datos $Datos
try {
    if (-not (Test-Path -LiteralPath $R.Python)) { throw 'No se encontró el Python del programa.' }
    $env:COBRO_INSTANCIA = $R.Instancia
    $env:PYTHONUTF8 = '1'
    Write-Host 'Comprobando la firma y la huella de la actualización descargada...'
    Write-Host ''
    & $R.Python -X utf8 -B $R.Manage instalar_actualizacion
    if ($LASTEXITCODE -ne 0) { throw 'No se ejecutó el instalador.' }
    exit 0
}
catch {
    Write-Host "ERROR: $($_.Exception.Message)"
    exit 1
}
