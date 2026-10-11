$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$pythonGrifo = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $pythonGrifo)) {
    throw 'No se encuentra .venv. Crea el entorno e instala requirements.txt primero.'
}
# Detectar ambos puertos usados durante la validación; no cerrar procesos ajenos.
$ocupadosGrifo = @(Get-NetTCPConnection -State Listen -ErrorAction Stop |
    Where-Object { $_.LocalPort -in @(8000, 8001) })
if ($ocupadosGrifo.Count -gt 0) {
    $ocupadosGrifo | Select-Object LocalAddress, LocalPort, OwningProcess | Format-Table
    Write-Host 'Ya hay un servidor en 8000 o 8001. Cierra las ventanas de GRIFO con Ctrl+C y vuelve a ejecutar este script.'
    Write-Host 'No se ha detenido ningun proceso ni iniciado otra instancia.'
    exit 1
}
Write-Host 'GRIFO: http://127.0.0.1:8000 - deja esta ventana abierta. Para detener: Ctrl+C.'
& $pythonGrifo -m uvicorn realtime_server:app --host 127.0.0.1 --port 8000
exit $LASTEXITCODE
