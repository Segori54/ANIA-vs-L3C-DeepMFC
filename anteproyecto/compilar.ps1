$ErrorActionPreference = 'Stop'
$compilerPath = Join-Path $PSScriptRoot '..\local-builds\latex-tools\tectonic.exe'
if (-not (Test-Path -LiteralPath $compilerPath)) {
    throw 'No se encuentra el compilador portátil en local-builds/latex-tools/tectonic.exe.'
}
$env:TECTONIC_CACHE_DIR = Join-Path $PSScriptRoot '..\local-builds\latex-tools\cache'
Push-Location $PSScriptRoot
try {
    New-Item -ItemType Directory -Force -Path pdf | Out-Null
    & $compilerPath --keep-logs --synctex --outdir pdf main.tex
    if ($LASTEXITCODE -ne 0) { throw 'La compilación LaTeX falló; revisar pdf/main.log.' }
    Write-Host 'PDF generado en anteproyecto/pdf/main.pdf'
} finally {
    Pop-Location
}
