#ifndef AppVersion
#define AppVersion "0.1.0"
#endif

[Setup]
AppId={{A48AB087-6A0D-42E8-A5EA-2A97855BF04C}
AppName=Development Control Platform
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\Development Control Platform
DefaultGroupName=Development Control Platform
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\..\dist
OutputBaseFilename=Development-Control-Platform-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName=Development Control Platform

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "..\..\dashboard\*"; DestDir: "{app}\dashboard"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\tools\*"; DestDir: "{app}\tools"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\schemas\*"; DestDir: "{app}\schemas"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\Open-DCP-Dashboard.cmd"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\Run-DCP-Gateway.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\Setup-DCP-Local.cmd"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\Setup-DCP-Local.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\Start-DCP-Dashboard.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\Start-DCP-Local.cmd"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\Start-DCP-Local.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\requirements-cloud-gateway.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Development Control Platform\Start DCP"; Filename: "{app}\Start-DCP-Local.cmd"; WorkingDir: "{app}"
Name: "{autoprograms}\Development Control Platform\Setup Checks"; Filename: "{app}\Setup-DCP-Local.cmd"; WorkingDir: "{app}"
Name: "{autodesktop}\Development Control Platform"; Filename: "{app}\Start-DCP-Local.cmd"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\Start-DCP-Local.cmd"; Description: "Start Development Control Platform"; Flags: postinstall nowait skipifsilent unchecked

[Code]
function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
begin
  Result := Exec('py.exe', '-3 -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  if Result then
    Result := ResultCode = 0;
  if not Result then
    MsgBox('Python 3.10+ and the Python Launcher (py.exe) are required. Install them, then run this installer again.', mbError, MB_OK);
end;
