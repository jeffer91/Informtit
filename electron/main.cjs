const { app, BrowserWindow, dialog, shell, Menu, ipcMain, session } = require('electron');
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

function storageRoot() {
  const root = backendRoot();
  // Durante `npm start` se usa de forma explícita la base del repositorio.
  // En la aplicación instalada se conserva AppData/userData para persistencia.
  return app.isPackaged ? app.getPath('userData') : path.join(root, 'data');
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
  const storage = storageRoot();
  const args = [
    ...candidate.prefix,
    script,
    '--host', HOST,
    '--port', String(port),
    '--no-browser',
  ];

  console.log(`[Informtit] Código: ${root}`);
  console.log(`[Informtit] Almacenamiento: ${storage}`);

  return spawn(candidate.command, args, {
    cwd: root,
    windowsHide: true,
    env: {
      ...process.env,
      PYTHONUNBUFFERED: '1',
      INFORMTIT_STORAGE_DIR: storage,
      INFORMTIT_DESKTOP_MODE: app.isPackaged ? 'packaged' : 'development',
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

      processHandle.stdout.on('data', (chunk) => console.log(`[Informtit] ${String(chunk).trimEnd()}`));
      processHandle.stderr.on('data', (chunk) => console.error(`[Informtit] ${String(chunk).trimEnd()}`));

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
        console.log(`[Informtit] Backend listo: ${url}`);
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
  if (!mainWindow || mainWindow.isDestroyed()) return false;
  if (mainWindow.webContents.isDevToolsOpened()) mainWindow.webContents.closeDevTools();
  else mainWindow.webContents.openDevTools({ mode: 'detach' });
  return true;
}

function openDevTools() {
  if (!mainWindow || mainWindow.isDestroyed()) return false;
  if (!mainWindow.webContents.isDevToolsOpened()) {
    mainWindow.webContents.openDevTools({ mode: 'detach' });
  }
  return true;
}

function reloadInterface() {
  if (!mainWindow || mainWindow.isDestroyed()) return false;
  mainWindow.webContents.reloadIgnoringCache();
  return true;
}

function installApplicationMenu() {
  const template = [
    {
      label: 'Archivo',
      submenu: [
        { label: 'Recargar interfaz', accelerator: 'Ctrl+R', click: reloadInterface },
        { type: 'separator' },
        { role: 'quit', label: 'Salir' },
      ],
    },
    {
      label: 'Consola',
      submenu: [
        { label: 'Abrir consola', accelerator: 'F12', click: openDevTools },
        { label: 'Abrir / cerrar consola', accelerator: 'Ctrl+Shift+I', click: toggleDevTools },
        { type: 'separator' },
        {
          label: 'Recargar sin caché',
          click: reloadInterface,
        },
      ],
    },
    {
      label: 'Ver',
      submenu: [
        { role: 'resetZoom', label: 'Tamaño real' },
        { role: 'zoomIn', label: 'Acercar' },
        { role: 'zoomOut', label: 'Alejar' },
        { type: 'separator' },
        { role: 'togglefullscreen', label: 'Pantalla completa' },
      ],
    },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

function installDeveloperAccess() {
  if (!mainWindow) return;

  mainWindow.webContents.on('before-input-event', (event, input) => {
    const key = String(input.key || '').toLowerCase();
    const shortcut = input.key === 'F12' || (input.control && input.shift && key === 'i');
    if (!shortcut) return;
    event.preventDefault();
    toggleDevTools();
  });

  mainWindow.webContents.on('context-menu', (_event, params) => {
    const template = [
      {
        label: 'Inspeccionar elemento',
        click: () => {
          mainWindow.webContents.inspectElement(params.x, params.y);
          openDevTools();
        },
      },
      { type: 'separator' },
      { label: 'Abrir/Cerrar consola', accelerator: 'F12', click: toggleDevTools },
      { label: 'Recargar interfaz', accelerator: 'Ctrl+R', click: reloadInterface },
    ];
    Menu.buildFromTemplate(template).popup({ window: mainWindow });
  });
}

async function createWindow() {
  if (!appUrl) throw new Error('El backend local no está disponible.');

  // El HTML y los scripts cambian con frecuencia durante desarrollo. Limpiar la
  // caché impide que Electron mezcle una interfaz vieja con un backend nuevo.
  try {
    await session.defaultSession.clearCache();
  } catch (_error) {
    // La ausencia de caché no debe impedir el arranque.
  }

  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1100,
    minHeight: 720,
    show: false,
    title: app.isPackaged ? 'Informtit' : 'Informtit · desarrollo',
    backgroundColor: '#f4f7fb',
    autoHideMenuBar: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      devTools: true,
    },
  });

  installApplicationMenu();
  mainWindow.setAutoHideMenuBar(false);
  mainWindow.setMenuBarVisibility(true);
  installDeveloperAccess();
  mainWindow.once('ready-to-show', () => mainWindow.show());
  await mainWindow.loadURL(`${appUrl}/?build=${Date.now()}`);

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('http://') || url.startsWith('https://')) {
      shell.openExternal(url);
    }
    return { action: 'deny' };
  });
}

ipcMain.handle('informtit:toggle-devtools', () => toggleDevTools());
ipcMain.handle('informtit:open-devtools', () => openDevTools());
ipcMain.handle('informtit:reload', () => reloadInterface());

async function boot() {
  try {
    await startBackend();
    await createWindow();
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
  if (BrowserWindow.getAllWindows().length === 0 && backendProcess) void createWindow();
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
