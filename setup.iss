[Setup]
AppName=Sistema Ponto
AppVersion=1.0
AppPublisher=Idenilson
DefaultDirName={autopf}\SistemaPonto
DefaultGroupName=Sistema Ponto
OutputDir=installer
OutputBaseFilename=InstaladorPonto
Compression=lzma
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Files]
Source: "dist\Ponto2.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\config.ini"; DestDir: "{app}"; Flags: onlyifdoesntexist
Source: "dist\database.db"; DestDir: "{app}"; Flags: onlyifdoesntexist

[Icons]
Name: "{group}\Sistema Ponto"; Filename: "{app}\Ponto2.exe"
Name: "{commondesktop}\Sistema Ponto"; Filename: "{app}\Ponto2.exe"

[Run]
Filename: "{app}\Ponto2.exe"; Description: "Executar Sistema Ponto"; Flags: nowait postinstall skipifsilent
