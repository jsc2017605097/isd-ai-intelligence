@echo off
:: ISD Ecosystem Windows One-Click Installer
:: This script bypasses execution policies to run the powershell bootstrap.

TITLE ISD Ecosystem Installer

echo ==================================================
echo      ISD Ecosystem Easy Setup (Windows)
echo ==================================================
echo.

:: Check for Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Error: Python is not installed or not in PATH.
    echo Please install Python from https://www.python.org/
    pause
    exit /b 1
)

:: Check for Node
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Error: Node.js is not installed or not in PATH.
    echo Please install Node.js from https://nodejs.org/
    pause
    exit /b 1
)

echo 🧰 Running bootstrap script...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0bootstrap.ps1"

if %errorlevel% neq 0 (
    echo.
    echo ❌ Something went wrong during installation.
    pause
    exit /b %errorlevel%
)

echo.
echo ✅ ISD CLI has been set up!
echo 👉 You can now use the 'isd' command in any NEW terminal.
echo.
echo 🚀 Next step: Run 'isd install' to setup the projects.
echo.
pause
