param(
    [Parameter(Mandatory = $true)][string]$Programa,
    [Parameter(Mandatory = $true)][string]$Datos
)

. (Join-Path $PSScriptRoot 'comun.ps1')

$R = Rutas -Programa $Programa -Datos $Datos
try {
    Iniciar-Registro -Ruta (Join-Path $R.Registros 'instalacion.log')
    Escribir-Registro 'Preparando la actualización'
    Detener-Servicios -R $R
    if (-not (Test-Path -LiteralPath (Join-Path $R.Instancia 'configuracion.json'))) {
        Escribir-Registro 'No hay instancia que respaldar.'
        exit 0
    }
    $destino = Join-Path $R.Copias (Get-Date -Format 'yyyyMMdd-HHmmss')
    New-Item -ItemType Directory -Path $destino -Force | Out-Null
    Copy-Item -LiteralPath $R.Instancia -Destination $destino -Recurse -Force
    $original = (Get-ChildItem -LiteralPath $R.Instancia -Recurse -File | Measure-Object -Property Length -Sum).Sum
    $copia = (Get-ChildItem -LiteralPath (Join-Path $destino 'instancia') -Recurse -File | Measure-Object -Property Length -Sum).Sum
    if ($original -ne $copia) { throw "La copia de la instancia en $destino no coincide con el original." }
    Escribir-Registro "Copia de la instancia en $destino"
    if (Test-Path -LiteralPath $R.Python) {
        try {
            Manage -R $R -Argumentos @('respaldar', '--si-hay-carpeta') -Descripcion 'Respaldo antes de actualizar' | Out-Null
        }
        catch {
            Escribir-Registro "AVISO: el respaldo antes de actualizar falló ($($_.Exception.Message)); se continúa con la copia local en $destino."
            [Console]::Out.WriteLine('AVISO-RESPALDO: el respaldo cifrado falló; se guardó una copia local de la instancia.')
        }
    }
    exit 0
}
catch {
    Escribir-Registro "ERROR: $($_.Exception.Message)"
    [Console]::Out.WriteLine("ERROR-INSTALACION: $($_.Exception.Message)")
    exit 1
}
