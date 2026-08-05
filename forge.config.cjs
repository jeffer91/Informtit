module.exports = {
  packagerConfig: {
    asar: true,
    name: 'Informtit',
    executableName: 'Informtit',
    extraResource: [
      'app.py',
      'ai_service.py',
      'analytics.py',
      'db.py',
      'parser.py',
      'report_service.py',
      'requirements.txt',
      'static',
    ],
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
