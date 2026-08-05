const { app, BrowserWindow, dialog, shell } = require('electron');
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');

const HOST = '127.0.0.1';
const PORT = 8765;
const APP_URL = `http://${HOST}:${PORT}`;

let backendProcess = null;
let mainWindow = null;

function backendRoot() {
  return app.isPackaged ? process.resourcesPath : path.resolve(__dirname, '..');
}

function pythonCandidates() {
  if (process.env.INFORMTIT_PYTHON) {
    return [{ command: process.env.INFORMTIT_PYTHON, prefix: [] }];
  }

  const root = backendRoot();
  const localPython = process.platform === 'win32'
    ? path.join(root, '.venv', 'Scripts', 'python.exe')
    : path.join(root, '.venv', 'bin', 'python');

  const candidates = [];
  if (fs.existsSync(localPython)) {
    candidates.push({ command: localPython, prefix: [] });
  }

  if (process.platform === 'win32') {
    candidates.push(
      { command: 'py', prefix: ['-3'] },
      { command: 'python', prefix: [] },
    );
  } else {
    candidates.push(
      { command: 'python3', prefix: [] },
      { command: 'python', prefix: [] },
    );
  }

  return candidates;
}

function checkBackend() {
  return new Promise((resolve) => {
    const request = http.get(APP_URL, (response) => {
      response.resume();
      resolve(response.statusCode >= 200 && response.statusCode < 500);
    });
    request.setTimeout(700, () => {
      request.destroy();
      resolve(false);
    });
    request.on('error', () => resolve(false));
  });
}

async function waitForBackend(maxAttempts = 80) {
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    if (await checkBackend()) return true;
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  return false;
}

function spawnPython(candidate) {
  const root = backendRoot();
  const script = path.join(root, 'app.py');
  const args = [...candidate.prefix, script, '--host', HOST, '--port', String(PORT), '--no-browser'];

  return spawn(candidate.command, args, {
    cwd: root,
    windowsHide: true,
    env: {
      ...process.env,
      PYTHONUNBUFFERED: '1',
      INFORMTIT_STORAGE_DIR: app.getPath('userData'),
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
}

async function startBackend() {
  if (await checkBackend()) return;

  let lastError = null;
  for (const candidate of pythonCandidates()) {
    try {
      const processHandle = spawnPython(candidate);
      backendProcess = processHandle;

      processHandle.stdout.on('data', (chunk) => console.log(`[Informtit] ${chunk}`));
      processHandle.stderr.on('data', (chunk) => console.error(`[Informtit] ${chunk}`));

      const started = await Promise.race([
        waitForBackend(),
        new Promise((resolve) => {
          processHandle.once('error', (error) => {
            lastError = error;
            resolve(false);
          });
          processHandle.once('exit', (code) => {
            if (code !== null && code !== 0) {
              lastError = new Error(`El backend terminó con código ${code}.`);
            }
            resolve(false);
          });
        }),
      ]);

      if (started) return;
      if (!processHandle.killed) processHandle.kill();
    } catch (error) {
      lastError = error;
    }
  }

  throw lastError || new Error('No se pudo iniciar Python.');
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1100,
    minHeight: 720,
    show: false,
    backgroundColor: '#f4f7fb',
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  mainWindow.once('ready-to-show', () => mainWindow.show());
  mainWindow.loadURL(APP_URL);

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('http://') || url.startsWith('https://')) {
      shell.openExternal(url);
    }
    return { action: 'deny' };
  });
}

async function boot() {
  try {
    await startBackend();
    createWindow();
  } catch (error) {
    dialog.showErrorBox(
      'No se pudo iniciar Informtit',
      `${error.message}\n\nVerifica que Python 3 esté instalado y ejecuta en PowerShell:\npython -m pip install -r requirements.txt`,
    );
    app.quit();
  }
}

app.whenReady().then(boot);

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0 && backendProcess) createWindow();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', () => {
  if (backendProcess && !backendProcess.killed) {
    backendProcess.kill();
    backendProcess = null;
  }
});
