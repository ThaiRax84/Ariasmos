param(
    [Parameter(Mandatory = $true)][string]$Programa,
    [Parameter(Mandatory = $true)][string]$Datos,
    [Parameter(Mandatory = $true)][string]$Archivo,
    [Parameter(Mandatory = $true)][string]$ClaveArchivo
)

. (Join-Path $PSScriptRoot 'comun.ps1')

$R = Rutas -Programa $Programa -Datos $Datos
try {
    Proteger-Datos -R $R
    Iniciar-Registro -Ruta (Join-Path $R.Registros 'instalacion.log')
    if (-not (Test-Path -LiteralPath $Archivo -PathType Leaf)) { throw "No existe el archivo de respaldo $Archivo." }
    if (Test-Path -LiteralPath (Join-Path $R.Instancia 'configuracion.json')) { throw 'Ya hay una instalación con datos en este equipo; la restauración desde el instalador solo se hace en un equipo nuevo.' }
    Manage -R $R -Argumentos @('restaurar', '--archivo', $Archivo, '--clave-archivo', $ClaveArchivo) -Descripcion "Restaurando desde $(Split-Path -Leaf $Archivo)" | Out-Null
    Comprobar-Privado -Ruta $R.Instancia
    exit 0
}
catch {
    Escribir-Registro "ERROR: $($_.Exception.Message)"
    [Console]::Out.WriteLine("ERROR-INSTALACION: $($_.Exception.Message)")
    exit 1
}
finally {
    if (Test-Path -LiteralPath $ClaveArchivo) { Remove-Item -LiteralPath $ClaveArchivo -Force }
}
