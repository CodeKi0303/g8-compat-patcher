param(
    [Parameter(Mandatory=$true)][string]$BuildPython,
    [string]$OutputDirectory
)
$ErrorActionPreference = 'Stop'
$taskRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if (-not (Test-Path -LiteralPath $BuildPython -PathType Leaf)) {
    throw 'Supply an existing Python environment with requirements-build.txt installed.'
}
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $taskRoot 'dist\g8-compat-patcher-0.1.0-windows-x64' }
$taskOutput = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $taskOutput) { throw 'Choose a new output directory; previous releases are preserved.' }
Push-Location $taskRoot
try {
    & $BuildPython -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed.' }
    New-Item -ItemType Directory -Path $taskOutput | Out-Null
    & $BuildPython scripts/collect-licenses.py (Join-Path $taskOutput 'licenses')
    if ($LASTEXITCODE -ne 0) { throw 'Runtime license collection failed.' }
    $taskArgs = @('-m', 'PyInstaller', '--noconfirm', '--onefile', '--console', '--hide-console', 'hide-early', '--noupx',
        '--name', 'G8-Compat-Patcher', '--paths', $taskRoot,
        '--distpath', $taskOutput, '--workpath', (Join-Path $taskRoot 'build\pyinstaller'),
        '--specpath', (Join-Path $taskRoot 'build\spec'),
        '--add-data', ((Join-Path $taskRoot 'g8_patcher\profiles.json') + ';g8_patcher'),
        '--add-data', ((Join-Path $taskOutput 'licenses') + ';licenses'),
        '--add-data', ((Join-Path $taskRoot 'LICENSE') + ';.'),
        '--add-data', ((Join-Path $taskRoot 'THIRD_PARTY_NOTICES.md') + ';.'),
        (Join-Path $taskRoot 'launcher.py'))
    & $BuildPython @taskArgs
    if ($LASTEXITCODE -ne 0) { throw 'Executable build failed.' }
    foreach ($taskFile in @('README.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md')) {
        Copy-Item -LiteralPath (Join-Path $taskRoot $taskFile) -Destination (Join-Path $taskOutput $taskFile)
    }
    $taskExe = Join-Path $taskOutput 'G8-Compat-Patcher.exe'
    & $taskExe profiles
    if ($LASTEXITCODE -ne 0) { throw 'Packaged executable smoke check failed.' }
    $taskHash = (Get-FileHash -LiteralPath $taskExe -Algorithm SHA256).Hash.ToLowerInvariant()
    [IO.File]::WriteAllText((Join-Path $taskOutput 'SHA256SUMS.txt'), "$taskHash  G8-Compat-Patcher.exe`n", [Text.Encoding]::ASCII)
    $taskZip = $taskOutput + '.zip'
    if (Test-Path -LiteralPath $taskZip) { throw 'Release ZIP already exists.' }
    Compress-Archive -LiteralPath $taskOutput -DestinationPath $taskZip -CompressionLevel Optimal
    Get-FileHash -LiteralPath $taskZip -Algorithm SHA256
} finally { Pop-Location }
