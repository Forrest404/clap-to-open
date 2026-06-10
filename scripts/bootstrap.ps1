# One-command installer for Clap to Open on Windows.
#
#   irm https://raw.githubusercontent.com/Forrest404/clap-to-open/main/scripts/bootstrap.ps1 | iex
#
# Clones (or updates) the repo into %LOCALAPPDATA%\clap-to-open and runs install.ps1.
$ErrorActionPreference = "Stop"

$Repo = "https://github.com/Forrest404/clap-to-open.git"
$Dir  = Join-Path $env:LOCALAPPDATA "clap-to-open"

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
  throw "git is required. Install Git for Windows (https://git-scm.com) and retry."
}

if (Test-Path (Join-Path $Dir ".git")) {
  Write-Host "==> Updating existing checkout at $Dir"
  git -C $Dir pull --ff-only
} else {
  Write-Host "==> Cloning $Repo -> $Dir"
  git clone --depth 1 $Repo $Dir
}

powershell -ExecutionPolicy Bypass -File (Join-Path $Dir "scripts\install.ps1")
