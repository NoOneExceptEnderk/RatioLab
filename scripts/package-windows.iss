; SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
; SPDX-License-Identifier: GPL-3.0-only
; Compile with scripts/package-windows.ps1 after the native bundle passes checks.
#ifndef BundleDir
  #error BundleDir must name a verified native RatioLab onedir bundle
#endif
#ifndef OutputDir
  #error OutputDir is required
#endif
#ifndef AppVersion
  #error AppVersion is required
#endif
#ifndef SetupIcon
  #error SetupIcon is required
#endif

[Setup]
AppId=local.solidcraft.reducers
AppName=RatioLab
AppVersion={#AppVersion}
AppVerName=RatioLab {#AppVersion}
DefaultDirName={localappdata}\Programs\RatioLab
DefaultGroupName=RatioLab
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.22000
OutputDir={#OutputDir}
OutputBaseFilename=RatioLab-{#AppVersion}-windows-x86_64-setup
SetupIconFile={#SetupIcon}
UninstallDisplayIcon={app}\RatioLab.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
ChangesAssociations=no

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[InstallDelete]
; This reserved application runtime is replaced on upgrade. Preferences and
; default exports live in AppData/RatioLab, outside {app}, and are preserved.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#BundleDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\RatioLab"; Filename: "{app}\RatioLab.exe"; AppUserModelID: "local.solidcraft.reducers"
Name: "{autodesktop}\RatioLab"; Filename: "{app}\RatioLab.exe"; Tasks: desktopicon; AppUserModelID: "local.solidcraft.reducers"

[Run]
Filename: "{app}\RatioLab.exe"; Description: "Start RatioLab"; Flags: nowait postinstall skipifsilent
