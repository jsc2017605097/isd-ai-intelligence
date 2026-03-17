# ISD Ecosystem Windows Bootstrap
# This script sets up the 'isd' command for PowerShell.

$ErrorActionPreference = 'Stop'

Write-Host "🧰 Installing ISD CLI for Windows..." -ForegroundColor Blue

# Get the absolute path of isd.py in the current directory
$ScriptDir = $PSScriptRoot
if (-not $ScriptDir) { $ScriptDir = Get-Location }
$CliSource = Join-Path $ScriptDir "isd.py"

if (-not (Test-Path $CliSource)) {
    Write-Host "❌ Error: isd.py not found in this folder!" -ForegroundColor Red
    exit
}

# Create a function in the current PowerShell profile or just a simple alias for the session
# For a permanent installation, we suggest adding it to the Path or Profile.
# Here we'll create a small wrapper cmd file in a common path or just advise the user.

$BinPath = Join-Path $env:USERPROFILE "bin"
if (-not (Test-Path $BinPath)) { New-Item -ItemType Directory -Path $BinPath }

$BatchFile = Join-Path $BinPath "isd.bat"
"@echo off`npython `"$CliSource`" %*" | Out-File -FilePath $BatchFile -Encoding ascii

Write-Host "✅ ISD CLI wrapper created at $BatchFile" -ForegroundColor Green
Write-Host "👉 Make sure '$BinPath' is in your System PATH." -ForegroundColor Yellow
Write-Host "After that, you can use the command 'isd' anywhere." -ForegroundColor Blue
Write-Host "Next step: Run 'isd install'" -ForegroundColor Blue
