param(
    [switch]$InstalarPython
)

$ErrorActionPreference = 'Stop'

function Test-PythonCandidate {
    param(
        [string]$Command,
        [string[]]$PrefixArgs = @()
    )

    $isPath = [System.IO.Path]::IsPathRooted($Command) -or $Command.Contains('\') -or $Command.Contains('/')
    if ($isPath) {
        if (-not (Test-Path $Command)) { return $null }
    } elseif (-not (Get-Command $Command -ErrorAction SilentlyContinue)) {
        return $null
    }

    try {
        $output = & $Command @PrefixArgs --version 2>&1 | Out-String
        if ($LASTEXITCODE -eq 0 -and $output -match 'Python\s+3\.') {
            return [PSCustomObject]@{
                Command = $Command
                PrefixArgs = $PrefixArgs
                Version = $output.Trim()
            }
        }
    } catch {
        return $null
    }

    return $null
}

function Find-Python3 {
    $localPython = Join-Path (Resolve-Path (Join-Path $PSScriptRoot '..')).Path '.venv\Scripts\python.exe'
    $candidates = @(
        @{ Command = $localPython; PrefixArgs = @() },
        @{ Command = 'py'; PrefixArgs = @('-3') },
        @{ Command = 'python'; PrefixArgs = @() },
        @{ Command = 'python3'; PrefixArgs = @() }
    )

    foreach ($candidate in $candidates) {
        $result = Test-PythonCandidate -Command $candidate.Command -PrefixArgs $candidate.PrefixArgs
        if ($null -ne $result) { return $result }
    }

    return $null
}

Write-Host 'Configurando Informtit...' -ForegroundColor Cyan

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    throw 'Node.js no está instalado o no está disponible en PATH.'
}

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw 'npm no está instalado o no está disponible en PATH.'
}

$python = Find-Python3

if ($null -eq $python -and $InstalarPython) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw 'No se encontró Python 3 ni WinGet. Instala Python 3.14 desde python.org y vuelve a ejecutar este script.'
    }

    Write-Host 'Python 3 no está instalado. Instalando con WinGet...' -ForegroundColor Yellow
    winget install --id Python.Python.3.14 -e --accept-package-agreements --accept-source-agreements
    Write-Host ''
    Write-Host 'Python fue instalado. Cierra y vuelve a abrir Visual Studio Code; después ejecuta otra vez:' -ForegroundColor Green
    Write-Host '.\scripts\configurar.ps1' -ForegroundColor Green
    exit 0
}

if ($null -eq $python) {
    throw @'
No se encontró una instalación real de Python 3.

El comando "python" de este equipo apunta al alias de Microsoft Store, pero no existe un intérprete instalado.

Ejecuta:
  winget install Python.Python.3.14

Después cierra y vuelve a abrir Visual Studio Code y ejecuta nuevamente:
  .\scripts\configurar.ps1

También puedes ejecutar este script con instalación automática:
  .\scripts\configurar.ps1 -InstalarPython
'@
}

Write-Host "Python detectado: $($python.Version)" -ForegroundColor Green

Write-Host 'Instalando dependencias de Electron...' -ForegroundColor Yellow
npm install

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $projectRoot

Write-Host 'Creando entorno virtual de Python...' -ForegroundColor Yellow
if (Test-Path '.venv') {
    Remove-Item '.venv' -Recurse -Force
}
& $python.Command @($python.PrefixArgs) -m venv .venv

$venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPython)) {
    throw 'No se pudo crear .venv. Verifica la instalación de Python y vuelve a intentarlo.'
}

Write-Host 'Instalando dependencias de Python...' -ForegroundColor Yellow
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r requirements.txt

Write-Host ''
Write-Host 'Configuración terminada.' -ForegroundColor Green
Write-Host 'Para abrir Informtit ejecuta:' -ForegroundColor Green
Write-Host 'npm start' -ForegroundColor Green
