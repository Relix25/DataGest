param(
    [string]$Version = ""
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot
try {
    python -m pip install --upgrade pip
    pip install -e ".[dev]"

    pyinstaller packaging/datagest.spec --noconfirm

    if (-not $Version) {
        $Version = python -c "import sys; sys.path.insert(0, 'src'); from version import APP_VERSION; print(APP_VERSION)"
        $Version = $Version.Trim()
    }

    $zipPath = "dist/DataGest-v$Version.zip"
    if (Test-Path $zipPath) {
        Remove-Item $zipPath -Force
    }
    Compress-Archive -Path "dist/DataGest/*" -DestinationPath $zipPath

    Write-Host "Build complete: $zipPath"
}
finally {
    Pop-Location
}
