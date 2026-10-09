$ErrorActionPreference = 'Stop'
$projectDirectory = $PSScriptRoot
$nativePython = Join-Path $projectDirectory '.venv-native\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $nativePython)) {
    py -3.11 -m venv (Join-Path $projectDirectory '.venv-native')
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 is required to create the native environment.' }
}
& $nativePython -m pip install -r (Join-Path $projectDirectory 'native\requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Native dependencies could not be installed.' }
Push-Location $projectDirectory
try { & $nativePython -m native }
finally { Pop-Location }

