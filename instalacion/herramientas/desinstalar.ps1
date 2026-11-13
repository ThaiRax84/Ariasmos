param(
    [Parameter(Mandatory = $true)][string]$Programa,
    [Parameter(Mandatory = $true)][string]$Datos,
    [ValidateSet('conservar', 'borrar')][string]$DatosAccion = 'conservar'
)

. (Join-Path $PSScriptRoot 'comun.ps1')

$R = Rutas -Programa $Programa -Datos $Datos
$errores = @()
if (Test-Path -LiteralPath $R.Registros) {
    Iniciar-Registro -Ruta (Join-Path $R.Registros 'instalacion.log')
}
Escribir-Registro 'Desinstalando'
foreach ($paso in @(
        @{ Nombre = 'servicios'; Accion = { Quitar-Servicios -R $R } },
        @{ Nombre = 'firewall'; Accion = { Quitar-Firewall } },
        @{ Nombre = 'certificado'; Accion = { Quitar-Certificado -R $R } }
    )) {
    try {
        & $paso.Accion
    }
    catch {
        $errores += "$($paso.Nombre): $($_.Exception.Message)"
        Escribir-Registro "ERROR al quitar $($paso.Nombre): $($_.Exception.Message)"
    }
}
if ($DatosAccion -eq 'borrar') {
    try {
        $script:Registro = $null
        Remove-Item -LiteralPath $R.Datos -Recurse -Force
        Write-Host 'Datos borrados.'
    }
    catch {
        $errores += "datos: $($_.Exception.Message)"
    }
}
else {
    Escribir-Registro "Los datos se conservan en $($R.Datos)"
}
if ($errores.Count -gt 0) {
    [Console]::Out.WriteLine("ERROR-DESINSTALACION: $($errores -join '; ')")
    exit 1
}
exit 0
