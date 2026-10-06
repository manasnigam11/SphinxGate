<#
.SYNOPSIS
  Installs a pinned, checksum-verified Gitleaks binary into tools/gitleaks/ (Windows x64).

.DESCRIPTION
  SphinxGate uses Gitleaks (https://github.com/gitleaks/gitleaks) as its secret scanner.
  We do NOT ship a home-made scanner.  This script downloads the official release,
  verifies its SHA-256 against the published checksums file, and unpacks it into
  tools/gitleaks/ (git-ignored).  Linux/macOS/CI users install gitleaks via their
  package manager or the official GitHub Action (see .github/workflows/security.yml).
#>
param(
    [string]$Version = "8.30.1"
)

$ErrorActionPreference = "Stop"
$root    = Split-Path -Parent $PSScriptRoot
$dest    = Join-Path $root "tools\gitleaks"
$exe     = Join-Path $dest "gitleaks.exe"
$zipName = "gitleaks_${Version}_windows_x64.zip"
$base    = "https://github.com/gitleaks/gitleaks/releases/download/v$Version"

if (Test-Path $exe) {
    Write-Host "gitleaks already installed: $exe"
    & $exe version
    exit 0
}

New-Item -ItemType Directory -Force -Path $dest | Out-Null
$zipPath  = Join-Path $dest $zipName
$sumsPath = Join-Path $dest "checksums.txt"

Invoke-WebRequest -Uri "$base/$zipName" -OutFile $zipPath
Invoke-WebRequest -Uri "$base/gitleaks_${Version}_checksums.txt" -OutFile $sumsPath

$expected = (Select-String -Path $sumsPath -Pattern ([regex]::Escape($zipName))).Line.Split(" ")[0].ToLower()
$actual   = (Get-FileHash -Algorithm SHA256 -Path $zipPath).Hash.ToLower()
if ($expected -ne $actual) {
    Remove-Item $zipPath -Force
    throw "Checksum mismatch for $zipName (expected $expected, got $actual)"
}

Expand-Archive -Path $zipPath -DestinationPath $dest -Force
Remove-Item $zipPath -Force
Write-Host "Installed: $exe"
& $exe version
