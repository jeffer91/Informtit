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
  // Con `asar: false`, Electron Forge instala el código de la aplicación en
  // resources/app. Python necesita archivos reales (no contenidos dentro de
  // app.asar), por lo que esta ruta debe apuntar exactamente a ese directorio.
  return app.isPackaged
    ? path.join(process.resourcesPath, 'app')
    : path.resolve(__dirname, '..');
}

function storageRoot() {
  // La base de escritorio siempre es persistente en userData. Durante desarrollo,
  // storage_migration.py recupera automáticamente data/informtit.db si userData
  // todavía no contiene trabajo real. Esto evita alternar entre dos SQLite.
  return app.getPath('userData');
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
  console.log(`[Informtit] Almacenamiento persistente: ${storage}`);

  if (!fs.existsSync(script)) {
    throw new Error(`No se encontró el backend de Informtit en ${script}.`);
  }

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

function safePdfFilename(value) {
  let name = String(value || 'Informe_Titulacion.pdf')
    .replace(/[<>:"/\\|?*\x00-\x1F]/g, '_')
    .trim();
  name = name.replace(/\.pdf$/i, '').trim();
  if (!name) name = 'Informe_Titulacion';
  // Reservar siempre espacio para la extensión; un nombre largo no debe terminar
  // perdiendo ".pdf" al recortarse.
  return `${name.slice(0, 175).trim() || 'Informe_Titulacion'}.pdf`;
}

function isAllowedPdfDownloadPath(value) {
  const relative = String(value || '');
  return /^\/api\/pdf-jobs\/[a-f0-9]{32}\/download$/.test(relative)
    || /^\/api\/reports\/\d+\/pdf-cache\/download$/.test(relative);
}

function downloadBackendPdf(relativeUrl, destinationPath) {
  return new Promise((resolve, reject) => {
    if (!appUrl) {
      reject(new Error('El backend local de Informtit no está disponible.'));
      return;
    }
    if (!isAllowedPdfDownloadPath(relativeUrl)) {
      reject(new Error('La ruta solicitada no corresponde a un PDF de Informtit.'));
      return;
    }

    const target = new URL(relativeUrl, appUrl);
    const tempPath = `${destinationPath}.informtit-${process.pid}-${Date.now()}.part`;
    const cleanupTemp = () => {
      fs.rm(tempPath, { force: true }, () => {});
    };

    const request = http.get(target, (response) => {
      const status = Number(response.statusCode || 0);
      if (status < 200 || status >= 300) {
        let body = '';
        response.setEncoding('utf8');
        response.on('data', (chunk) => {
          if (body.length < 4096) body += chunk;
        });
        response.on('end', () => {
          let detail = body.trim();
          try {
            const parsed = JSON.parse(body);
            detail = parsed?.error || detail;
          } catch (_error) {
            // Mantener el texto recibido si no es JSON.
          }
          reject(new Error(detail || `El backend respondió con HTTP ${status}.`));
        });
        return;
      }

      const file = fs.createWriteStream(tempPath, { flags: 'w' });
      let bytes = 0;
      let header = Buffer.alloc(0);

      response.on('data', (chunk) => {
        bytes += chunk.length;
        if (header.length < 5) {
          const needed = 5 - header.length;
          header = Buffer.concat([header, chunk.subarray(0, needed)]);
        }
      });
      response.on('error', (error) => {
        file.destroy();
        cleanupTemp();
        reject(error);
      });
      file.on('error', (error) => {
        response.destroy();
        cleanupTemp();
        reject(error);
      });
      file.on('finish', () => {
        file.close(async () => {
          if (bytes < 5 || header.toString('ascii') !== '%PDF-') {
            cleanupTemp();
            reject(new Error('El backend no entregó un archivo PDF válido.'));
            return;
          }

          const backupPath = `${destinationPath}.informtit-backup-${process.pid}-${Date.now()}`;
          let backupCreated = false;
          try {
            if (fs.existsSync(destinationPath)) {
              await fs.promises.rename(destinationPath, backupPath);
              backupCreated = true;
            }
            try {
              await fs.promises.rename(tempPath, destinationPath);
            } catch (error) {
              if (backupCreated && fs.existsSync(backupPath)) {
                await fs.promises.rename(backupPath, destinationPath).catch(() => {});
              }
              throw error;
            }
            if (backupCreated) {
              await fs.promises.rm(backupPath, { force: true }).catch(() => {});
            }
            resolve({ bytes });
          } catch (error) {
            cleanupTemp();
            reject(error);
          }
        });
      });
      response.pipe(file);
    });

    request.setTimeout(120000, () => {
      request.destroy(new Error('La descarga del PDF superó el tiempo máximo de espera.'));
    });
    request.on('error', (error) => {
      cleanupTemp();
      reject(error);
    });
  });
}

async function savePdfFromBackend(args = {}) {
  if (!mainWindow || mainWindow.isDestroyed()) {
    throw new Error('La ventana principal de Informtit no está disponible.');
  }

  const relativeUrl = String(args?.url || '');
  if (!isAllowedPdfDownloadPath(relativeUrl)) {
    throw new Error('Ruta de descarga PDF no permitida.');
  }

  const filename = safePdfFilename(args?.filename);
  const selection = await dialog.showSaveDialog(mainWindow, {
    title: 'Guardar PDF de Informtit',
    defaultPath: path.join(app.getPath('downloads'), filename),
    buttonLabel: 'Guardar PDF',
    filters: [{ name: 'Documento PDF', extensions: ['pdf'] }],
    properties: ['showOverwriteConfirmation'],
  });

  if (selection.canceled || !selection.filePath) {
    return { ok: false, canceled: true };
  }

  const destinationPath = selection.filePath.toLowerCase().endsWith('.pdf')
    ? selection.filePath
    : `${selection.filePath}.pdf`;
  const result = await downloadBackendPdf(relativeUrl, destinationPath);
  return {
    ok: true,
    canceled: false,
    path: destinationPath,
    bytes: result.bytes,
  };
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
        { label: 'Recargar sin caché', click: reloadInterface },
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

  // Duplica los errores del renderer en PowerShell para que un fallo de interfaz
  // no vuelva a quedar oculto detrás de una ventana sin respuesta.
  mainWindow.webContents.on('console-message', (_event, level, message, line, sourceId) => {
    const prefix = level >= 2 ? '[Informtit renderer ERROR]' : '[Informtit renderer]';
    console.log(`${prefix} ${message} (${sourceId || 'interfaz'}:${line || 0})`);
  });
  mainWindow.webContents.on('render-process-gone', (_event, details) => {
    console.error(`[Informtit] El proceso de interfaz terminó: ${details.reason} (${details.exitCode})`);
  });
}

async function createWindow() {
  if (!appUrl) throw new Error('El backend local no está disponible.');

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
ipcMain.handle('informtit:save-pdf', (_event, args) => savePdfFromBackend(args));

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