# Ferrox CLI Setup Script for Windows
# Run this script in PowerShell: .\setup.ps1

param(
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "`n[Ferrox] $Message" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "[OK] $Message" -ForegroundColor Green
}

function Write-Warning {
    param([string]$Message)
    Write-Host "[WARN] $Message" -ForegroundColor Yellow
}

function Write-Error-Step {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

function Test-PythonInstalled {
    try {
        $version = python --version 2>&1
        return $true
    } catch {
        return $false
    }
}

function Get-PythonVersion {
    try {
        $version = python --version 2>&1
        return $version.ToString()
    } catch {
        return $null
    }
}

function Ensure-ConfigDirectory {
    $configDir = "$env:USERPROFILE\.ferrox"
    if (-not (Test-Path $configDir)) {
        New-Item -ItemType Directory -Path $configDir -Force | Out-Null
        Write-Step "Created config directory: $configDir"
    }
    return $configDir
}

function Get-PythonPath {
    $pythonPath = python -c "import sys; print(sys.executable)" 2>&1
    if ($pythonPath) {
        return Split-Path -Parent $pythonPath
    }
    return $null
}

function Add-PythonScriptsToPath {
    $pythonDir = Get-PythonPath
    $scriptsDir = Join-Path $pythonDir "Scripts"

    if (-not (Test-Path $scriptsDir)) {
        Write-Warning "Python Scripts folder not found: $scriptsDir"
        return $false
    }

    $currentPath = [Environment]::GetEnvironmentVariable("PATH", "User")
    if ($currentPath -like "*$scriptsDir*") {
        Write-Success "Python Scripts already in PATH"
        return $true
    }

    [Environment]::SetEnvironmentVariable("PATH", "$currentPath;$scriptsDir", "User")
    $env:PATH = "$scriptsDir;$env:PATH"
    Write-Success "Added Python Scripts to PATH (permanent)"
    return $true
}

function Install-Ferrox {
    Write-Step "Setting up Ferrox CLI..."

    # Check Python
    if (-not (Test-PythonInstalled)) {
        Write-Error-Step "Python not found. Please install Python 3.8+ from https://python.org"
        Write-Host "After installing Python, restart PowerShell and run this script again."
        exit 1
    }

    $pythonVersion = Get-PythonVersion
    Write-Success "Found $pythonVersion"

    # Add Python Scripts to PATH (permanent + current session)
    Add-PythonScriptsToPath

    # Create config directory
    $configDir = Ensure-ConfigDirectory

    # Install dependencies
    Write-Step "Installing Python dependencies..."
    python -m pip install --upgrade pip 2>&1 | Out-Null

    $dependencies = @("click", "rich", "prompt_toolkit", "pydantic", "httpx")
    foreach ($dep in $dependencies) {
        python -m pip install $dep --quiet 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Success "Installed $dep"
        } else {
            Write-Error-Step "Failed to install $dep"
            exit 1
        }
    }

    # Install Ferrox package
    Write-Step "Installing Ferrox package..."
    $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    python -m pip install -e $scriptDir --quiet 2>&1 | Out-Null

    if ($LASTEXITCODE -eq 0) {
        Write-Success "Installed Ferrox"
    } else {
        Write-Error-Step "Failed to install Ferrox package"
        exit 1
    }

    # Create default config if not exists
    $configFile = Join-Path $configDir "config.json"
    if (-not (Test-Path $configFile)) {
        $defaultConfig = @{
            provider_name = "custom"
            base_url = "https://api.openai.com/v1"
            api_key = "your-api-key-here"
            default_model = $null
            timeout = 30
            max_tokens = 4096
            temperature = 0.7
        }
        $defaultConfig | ConvertTo-Json -Depth 3 | Set-Content -Path $configFile -Encoding UTF8
        Write-Success "Created default config at $configFile"
        Write-Warning "Please edit the config file and add your API key"
    }

    # Add to PATH suggestion
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Yellow
    Write-Host "  Ferrox installed successfully!" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Run 'ferrox' to start the CLI."
    Write-Host "Run 'ferrox config' to edit configuration."
    Write-Host ""
    Write-Host "First time setup:"
    Write-Host "  1. Run: ferrox config"
    Write-Host "  2. Update base_url and api_key"
    Write-Host "  3. Run: ferrox models"
    Write-Host "  4. Select your model"
    Write-Host "  5. Run: ferrox"
    Write-Host ""
}

function Uninstall-Ferrox {
    Write-Step "Uninstalling Ferrox..."

    python -m pip uninstall ferrox -y 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Success "Uninstalled Ferrox package"
    }

    $configDir = "$env:USERPROFILE\.ferrox"
    if (Test-Path $configDir) {
        Write-Warning "Config directory kept at: $configDir"
        Write-Host "Remove manually with: Remove-Item -Recurse $configDir"
    }

    Write-Success "Uninstall complete"
}

# Main
if ($Uninstall) {
    Uninstall-Ferrox
} else {
    Install-Ferrox
}