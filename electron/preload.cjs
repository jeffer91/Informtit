const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('informtitDesktop', {
  isElectron: true,
  platform: process.platform,
  versions: {
    electron: process.versions.electron,
    chrome: process.versions.chrome,
  },
  toggleDevTools: () => ipcRenderer.invoke('informtit:toggle-devtools'),
  openDevTools: () => ipcRenderer.invoke('informtit:open-devtools'),
  reload: () => ipcRenderer.invoke('informtit:reload'),
});
