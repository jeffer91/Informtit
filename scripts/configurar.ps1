$ErrorActionPreference = 'Stop'

Write-Host 'Configurando Informtit...' -ForegroundColor Cyan

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    throw 'Node.js no está instalado o no está disponible en PATH.'
}

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw 'npm no está instalado o no está disponible en PATH.'
}

$pythonCommand = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
    $pythonCommand = 'py -3'
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonCommand = 'python'
} else {
    throw 'Python 3 no está instalado o no está disponible en PATH.'
}

Write-Host 'Instalando dependencias de Electron...' -ForegroundColor Yellow
npm install

Write-Host 'Creando entorno virtual de Python...' -ForegroundColor Yellow
Invoke-Expression "$pythonCommand -m venv .venv"

Write-Host 'Instalando dependencias de Python...' -ForegroundColor Yellow
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt

Write-Host ''
Write-Host 'Configuración terminada.' -ForegroundColor Green
Write-Host 'Para abrir la aplicación ejecuta:' -ForegroundColor Green
Write-Host '$env:INFORMTIT_PYTHON=".venv\Scripts\python.exe"; npm start'
