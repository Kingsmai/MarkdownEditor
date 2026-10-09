param([string]$OutputDirectory = "desktop-dist")

$ErrorActionPreference = 'Stop'
$projectDirectory = $PSScriptRoot
$nativePython = Join-Path $projectDirectory '.venv-native\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $nativePython)) { throw 'Run run-native.ps1 once to create the Python environment.' }
Push-Location $projectDirectory
try {
    & $nativePython -X utf8 -m native.build --output-dir $OutputDirectory --smoke-test
    if ($LASTEXITCODE -ne 0) { throw 'Native application build failed.' }
}
finally { Pop-Location }
