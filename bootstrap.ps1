# ISD Ecosystem Windows Bootstrap (Refined)
$ErrorActionPreference = 'Stop'

# Get directory of this script
$ScriptDir = $PSScriptRoot
if (-not $ScriptDir) { $ScriptDir = Get-Location }
$CliSource = Join-Path $ScriptDir "isd.py"

# Create a local bin folder in user profile if it doesn't exist
$BinPath = Join-Path $env:USERPROFILE ".isd\bin"
if (-not (Test-Path $BinPath)) { 
    New-Item -ItemType Directory -Path $BinPath -Force | Out-Null
}

# Create isd.bat wrapper
$BatchFile = Join-Path $BinPath "isd.bat"
"@echo off`npython `"$CliSource`" %*" | Out-File -FilePath $BatchFile -Encoding ascii

# Add to User PATH permanently if not already there
$CurrentPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($CurrentPath -notlike "*$BinPath*") {
    Write-Host "➕ Adding $BinPath to User PATH..." -ForegroundColor Cyan
    [Environment]::SetEnvironmentVariable("Path", "$CurrentPath;$BinPath", "User")
    $env:Path += ";$BinPath"
}

Write-Host "✅ ISD CLI wrapper created at: $BatchFile" -ForegroundColor Green
Write-Host "🚀 Installation successful!" -ForegroundColor Green
