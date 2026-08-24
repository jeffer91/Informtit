const { app, BrowserWindow, dialog, shell, Menu } = require('electron');
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const http = require('node:http');
const net = require('node:net');
const path = require('node:path');

const HOST = '127.0.0.1';
const REQUIRED_CAPABILITY = 'schedules';

let backendProcess = null;
let backendPort = null;
let appUrl = null;
let mainWindow = null;

function backendRoot() {
  return app.isPackaged ? process.resourcesPath : path.resolve(__dirname, '..');
}

function pythonCandidates() {
  const root = backendRoot();
  const localPython = process.platform === 'win32'
    ? path.join(root, '.venv', 'Scripts', 'python.exe')
    : path.join(root, '.venv', 'bin', 'python');

  const candidates = [];

  if (process.env.INFORMTIT_PYTHON) {
    candidates.push({ command: process.env.INFORMTIT_PYTHON, prefix: [] });
  }

  if (fs.existsSync(localPython)) {
    candidates.push({ command: localPython, prefix: [] });
  }

  if (process.platform === 'win32') {
    candidates.push(
      { command: 'py', prefix: ['-3'] },
      { command: 'python', prefix: [] },
      { command: 'python3', prefix: [] },
    );
  } else {
    candidates.push(
      { command: 'python3', prefix: [] },
      { command: 'python', prefix: [] },
    );
  }

  return candidates;
}

function findFreePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.once('error', reject);
    server.listen(0, HOST, () => {
      const address = server.address();
      const port = typeof address === 'object' && address ? address.port : null;
      server.close(() => {
        if (port) resolve(port);
        else reject(new Error('No se pudo asignar un puerto local.'));
      });
    });
  });
}

function checkBackend(url) {
  return new Promise((resolve) => {
    const request = http.get(`${url}/api/health`, (response) => {
      let body = '';
      response.setEncoding('utf8');
      response.on('data', (chunk) => { body += chunk; });
      response.on('end', () => {
        try {
          const data = JSON.parse(body);
          const capabilities = Array.isArray(data.capabilities) ? data.capabilities : [];
          resolve(
            response.statusCode >= 200
            && response.statusCode < 300
            && data.ok === true
            && capabilities.includes(REQUIRED_CAPABILITY)
          );
        } catch (_error) {
          resolve(false);
        }
      });
    });
    request.setTimeout(800, () => {
      request.destroy();
      resolve(false);
    });
    request.on('error', () => resolve(false));
  });
}

async function waitForBackend(url, maxAttempts = 100) {
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    if (await checkBackend(url)) return true;
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  return false;
}

function spawnPython(candidate, port) {
  const root = backendRoot();
  const script = path.join(root, 'desktop_entry.py');
  const args = [
    ...candidate.prefix,
    script,
    '--host', HOST,
    '--port', String(port),
    '--no-browser',
  ];

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

async function stopProcess(processHandle) {
  if (!processHandle || processHandle.killed) return;
  processHandle.kill();
  await new Promise((resolve) => setTimeout(resolve, 200));
}

async function startBackend() {
  let lastError = null;

  for (const candidate of pythonCandidates()) {
    const port = await findFreePort();
    const url = `http://${HOST}:${port}`;

    try {
      console.log(`[Informtit] Probando Python: ${candidate.command} ${candidate.prefix.join(' ')}`);
      console.log(`[Informtit] Backend local: ${url}`);
      const processHandle = spawnPython(candidate, port);
      backendProcess = processHandle;

      processHandle.stdout.on('data', (chunk) => console.log(`[Informtit] ${chunk}`));
      processHandle.stderr.on('data', (chunk) => console.error(`[Informtit] ${chunk}`));

      const started = await Promise.race([
        waitForBackend(url),
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

      if (started) {
        backendPort = port;
        appUrl = url;
        return;
      }

      await stopProcess(processHandle);
      backendProcess = null;
    } catch (error) {
      lastError = error;
      await stopProcess(backendProcess);
      backendProcess = null;
    }
  }

  throw lastError || new Error('No se encontró una instalación funcional de Python 3.');
}

function toggleDevTools() {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  if (mainWindow.webContents.isDevToolsOpened()) mainWindow.webContents.closeDevTools();
  else mainWindow.webContents.openDevTools({ mode: 'detach' });
}

function installDeveloperAccess() {
  if (!mainWindow) return;

  // F12 y Ctrl+Shift+I abren/cierra la consola de Chromium.
  mainWindow.webContents.on('before-input-event', (event, input) => {
    const key = String(input.key || '').toLowerCase();
    const shortcut = input.key === 'F12' || (input.control && input.shift && key === 'i');
    if (!shortcut) return;
    event.preventDefault();
    toggleDevTools();
  });

  // Clic derecho permite abrir la consola o inspeccionar el elemento señalado.
  mainWindow.webContents.on('context-menu', (_event, params) => {
    const template = [
      {
        label: 'Inspeccionar elemento',
        click: () => {
          mainWindow.webContents.inspectElement(params.x, params.y);
          if (!mainWindow.webContents.isDevToolsOpened()) {
            mainWindow.webContents.openDevTools({ mode: 'detach' });
          }
        },
      },
      { type: 'separator' },
      { label: 'Abrir/Cerrar consola', accelerator: 'F12', click: toggleDevTools },
      { label: 'Recargar interfaz', accelerator: 'Ctrl+R', click: () => mainWindow.webContents.reload() },
    ];
    Menu.buildFromTemplate(template).popup({ window: mainWindow });
  });
}

function createWindow() {
  if (!appUrl) throw new Error('El backend local no está disponible.');

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
      devTools: true,
    },
  });

  installDeveloperAccess();
  mainWindow.once('ready-to-show', () => mainWindow.show());
  mainWindow.loadURL(appUrl);

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
      `${error.message}\n\nEjecuta en PowerShell:\n.\\scripts\\configurar.ps1 -InstalarPython\n\nLuego cierra y abre Visual Studio Code y ejecuta:\nnpm start`,
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
  backendPort = null;
  appUrl = null;
});
