# Install Clap to Open on Windows: create a self-contained venv, install the
# package + deps, and add Start-Menu + (optional) autostart shortcuts.
# Run from the project root:  powershell -ExecutionPolicy Bypass -File scripts\install.ps1
$ErrorActionPreference = "Stop"

$Project = (Resolve-Path "$PSScriptRoot\..").Path
$Venv    = Join-Path $Project "venv"
Write-Host "==> Project: $Project"

# 1. Find Python (prefer the py launcher).
$py = if (Get-Command py -ErrorAction SilentlyContinue) { "py -3" }
      elseif (Get-Command python -ErrorAction SilentlyContinue) { "python" }
      else { throw "Python 3 not found. Install it from https://python.org and re-run." }

# 2. Self-contained venv (no system-site-packages needed on Windows).
if (-not (Test-Path $Venv)) {
  Write-Host "==> Creating venv at $Venv"
  Invoke-Expression "$py -m venv `"$Venv`""
}
$VPy = Join-Path $Venv "Scripts\python.exe"

Write-Host "==> Installing the package + dependencies (pywin32, psutil, flask, clap-detector)"
& $VPy -m pip install --upgrade pip | Out-Null
& $VPy -m pip install -e $Project
# pywin32 needs a post-install step to register its DLLs.
$pwpi = Join-Path $Venv "Scripts\pywin32_postinstall.py"
if (Test-Path $pwpi) { & $VPy $pwpi -install | Out-Null }

# 3. Default startup sound is data\sounds\boot.wav (shipped in the repo).

# 4. Start-Menu shortcut that opens the control panel.
$Programs = [Environment]::GetFolderPath("Programs")
$WShell = New-Object -ComObject WScript.Shell
$VPyw = Join-Path $Venv "Scripts\pythonw.exe"
$VClap = Join-Path $Venv "Scripts\clap.exe"
$sc = $WShell.CreateShortcut((Join-Path $Programs "Clap to Open.lnk"))
$sc.TargetPath = $VClap
$sc.Arguments = "serve"
$sc.WorkingDirectory = $Project
$sc.Save()
Write-Host "==> Installed 'Clap to Open' Start-Menu shortcut"

Write-Host ""
Write-Host "Done. Next steps:" -ForegroundColor Green
Write-Host "  - Open the control panel:  `"$VClap`" serve"
Write-Host "  - Or launch 'Clap to Open' from the Start Menu."
Write-Host "  - Capture/arrange a layout, tune sensitivity, then turn Listening on."
Write-Host ""
Write-Host "Note: window placement, sound, autostart and the global hotkey are"
Write-Host "Windows-native here and were authored without a Windows test run --"
Write-Host "please report anything that misbehaves."
