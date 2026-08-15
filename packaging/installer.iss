; Inno Setup 6 script — optional Windows installer for Hung Phat Accounting.
; Compiled by packaging/build.ps1 -Installer, which passes /DAppVersion=x.y.z.
; Requires that dist/HungPhatAccounting/ already exists (run PyInstaller first).

#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

#define AppName "Hung Phat Accounting"
#define AppExe "HungPhatAccounting.exe"

[Setup]
AppId={{7C3E9A24-5B41-4E8D-9F2A-1D6B8C0E4A17}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Hung Phat M&&E
DefaultDirName={autopf}\HungPhatAccounting
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Per-user install by default: no admin prompt, and the app only ever writes to
; %APPDATA% anyway. Users who pick an admin location get elevated automatically.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=HungPhatAccounting-Setup-{#AppVersion}
SetupIconFile=HungPhat.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "vi"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Tao bieu tuong tren man hinh nen"; GroupDescription: "Tuy chon:"

[Files]
Source: "..\dist\HungPhatAccounting\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Go cai dat {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Mo {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Only the program folder. The accounting book lives in
; %APPDATA%\HungPhatAccounting (ketoan.db + einvoices\) and must survive an
; uninstall or a reinstall — never add it here.
Type: filesandordirs; Name: "{app}"
