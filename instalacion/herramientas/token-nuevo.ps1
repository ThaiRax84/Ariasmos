param(
    [string]$Programa = (Split-Path -Parent $PSScriptRoot),
    [string]$Datos = (Join-Path $env:ProgramData 'Ariasmos')
)

. (Join-Path $PSScriptRoot 'comun.ps1')

$R = Rutas -Programa $Programa -Datos $Datos
try {
    $salida = Manage -R $R -Argumentos @('inicializar', '--nuevo-token') -Silencioso
    $token = ''
    foreach ($renglon in $salida) {
        if ($renglon -match '^Token del asistente: (\S+)$') { $token = $Matches[1] }
    }
    if (-not $token) { throw 'No se pudo generar el token.' }
    Write-Host ''
    Write-Host 'Token nuevo del asistente (escríbelo en el primer paso del asistente):'
    Write-Host ''
    Write-Host "    $token"
    Write-Host ''
    Write-Host 'El token anterior ya no sirve. Este token no se guarda en ningún lado: cópialo ahora.'
    exit 0
}
catch {
    Write-Host "ERROR: $($_.Exception.Message)"
    exit 1
}
