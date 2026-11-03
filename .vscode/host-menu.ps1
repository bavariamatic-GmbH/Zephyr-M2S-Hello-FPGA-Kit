# Windows host actions for the "Zephyr: Workspace Menu" VS Code task.
# Creates the repository .venv from tools/hello_fpga_gui/requirements.txt and
# starts the Hello FPGA Kit test GUI (tools/hello_fpga_gui).
# Based on .vscode/host-menu.ps1 of SmartManipulator-X-Controller.

param(
    [Parameter(Mandatory = $true)]
    [string]$Action
)

# Native tools (pip) write warnings to stderr; failures are detected through
# exit codes below instead of PowerShell error records.
$ErrorActionPreference = 'Continue'

$Root = Split-Path -Parent $PSScriptRoot
$Venv = Join-Path $Root '.venv'
$VenvPython = Join-Path $Venv 'Scripts\python.exe'
$GuiDir = Join-Path $Root 'tools\hello_fpga_gui'
$Requirements = Join-Path $GuiDir 'requirements.txt'
$Gui = Join-Path $GuiDir 'hk_gui.py'

function Stop-WithError([string]$Message) {
    Write-Host "ERROR: $Message" -ForegroundColor Red
    exit 1
}

function Invoke-Checked([string]$Exe, [string[]]$Arguments) {
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) {
        Stop-WithError "Command failed ($LASTEXITCODE): $Exe $($Arguments -join ' ')"
    }
}

function Test-PythonImport([string]$Python, [string]$Code) {
    & $Python -c $Code *> $null
    return ($LASTEXITCODE -eq 0)
}

function New-Venv {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        Invoke-Checked 'py' @('-3', '-m', 'venv', $Venv)
    }
    elseif (Get-Command python -ErrorAction SilentlyContinue) {
        Invoke-Checked 'python' @('-m', 'venv', $Venv)
    }
    else {
        Stop-WithError 'Python 3.9+ was not found. Install it from https://www.python.org/ (with Tcl/Tk) and try again.'
    }
}

function Initialize-Venv {
    if (-not (Test-Path $VenvPython)) {
        Write-Host "Creating virtual environment in $Venv"
        New-Venv
    }
    Write-Host 'Installing requirements.'
    Invoke-Checked $VenvPython @('-m', 'pip', 'install', '--upgrade', 'pip')
    Invoke-Checked $VenvPython @('-m', 'pip', 'install', '-r', $Requirements)
    if (-not (Test-PythonImport $VenvPython 'import tkinter')) {
        Stop-WithError 'Tkinter is missing in this Python. Reinstall Python from python.org with "tcl/tk and IDLE" enabled, then delete .venv and run "Create .venv" again.'
    }
    Write-Host ".venv is ready: $VenvPython" -ForegroundColor Green
}

function Start-Gui([string[]]$GuiArgs) {
    if (-not ((Test-Path $VenvPython) -and (Test-PythonImport $VenvPython 'import serial, tkinter'))) {
        Initialize-Venv
    }
    Write-Host 'Starting the Hello FPGA Kit test GUI. Close the window to finish the task.'
    Set-Location $GuiDir
    Invoke-Checked $VenvPython (@($Gui) + $GuiArgs)
}

function Test-Gui {
    if (-not ((Test-Path $VenvPython) -and (Test-PythonImport $VenvPython 'import serial'))) {
        Initialize-Venv
    }
    Set-Location $GuiDir
    Invoke-Checked $VenvPython @('-m', 'unittest', 'discover', '-s', 'tests', '-v')
}

# Project web page (docs/site) through the "docs" service of compose.yaml
$DocsUrl = 'http://localhost:8000'

function Test-Docker {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Stop-WithError 'Docker was not found. Install Docker Desktop and start it.'
    }
}

function Start-DocsPreview {
    Test-Docker
    Set-Location $Root
    Invoke-Checked 'docker' @('compose', 'up', '--build', '--detach', 'docs')
    Write-Host "Waiting for $DocsUrl (first build takes a minute)."
    for ($i = 0; $i -lt 180; $i++) {
        try {
            Invoke-WebRequest -Uri $DocsUrl -UseBasicParsing -TimeoutSec 2 | Out-Null
            break
        }
        catch {
            Start-Sleep -Seconds 1
        }
    }
    Start-Process $DocsUrl
    Write-Host "Live preview on $DocsUrl, rebuilt on every change." -ForegroundColor Green
    Write-Host 'Log follows; stop the task with Ctrl+C (the preview keeps running) or use "Docs: Stop preview".'
    & docker compose logs --follow --tail 20 docs
}

function Invoke-DocsBuild {
    Test-Docker
    Set-Location $Root
    Invoke-Checked 'docker' @('compose', 'run', '--rm', '--build', '--no-deps', 'docs',
        'sphinx-build', '-E', '-W', '--keep-going', '-b', 'html', 'docs/site', 'docs/site/_build/html')
    Write-Host 'Page in docs/site/_build/html/index.html' -ForegroundColor Green
}

function Stop-DocsPreview {
    Test-Docker
    Set-Location $Root
    Invoke-Checked 'docker' @('compose', 'stop', 'docs')
}

switch ($Action) {
    'Create .venv' { Initialize-Venv }
    'Docs: Live preview' { Start-DocsPreview }
    'Docs: Build (strict, like CI)' { Invoke-DocsBuild }
    'Docs: Stop preview' { Stop-DocsPreview }
    'Run Hello FPGA GUI' { Start-Gui @() }
    'Run Hello FPGA GUI (simulator)' { Start-Gui @('--port', 'SIM') }
    'Test Hello FPGA GUI' { Test-Gui }
    default {
        Write-Host "Unknown workspace action: $Action" -ForegroundColor Red
        exit 2
    }
}
