const { contextBridge } = require('electron');

contextBridge.exposeInMainWorld('informtitDesktop', {
  isElectron: true,
  platform: process.platform,
  versions: {
    electron: process.versions.electron,
    chrome: process.versions.chrome,
  },
});
