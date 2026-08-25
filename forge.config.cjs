module.exports = {
  packagerConfig: {
    // Informtit ejecuta el backend Python como un proceso externo. Mantener la
    // aplicación fuera de ASAR garantiza que desktop_entry.py y todos sus
    // módulos estén disponibles como archivos reales para el intérprete.
    asar: false,
    name: 'Informtit',
    executableName: 'Informtit',
  },
  rebuildConfig: {},
  makers: [
    {
      name: '@electron-forge/maker-squirrel',
      config: {
        name: 'Informtit',
        setupExe: 'Informtit-Setup.exe',
      },
    },
    {
      name: '@electron-forge/maker-zip',
      platforms: ['win32'],
    },
  ],
};