#if Ver < EncodeVer(6, 3, 0)
  #error Se necesita Inno Setup 6.3 o posterior (ExecAndCaptureOutput).
#endif

#define Raiz SourcePath + ".."
#define Paquete Raiz + "\build\Ariasmos"
#define VersionApp Trim(FileRead(FileOpen(Raiz + "\VERSION")))

[Setup]
AppId={{0741FDFF-56E6-44BA-9BDF-2EC687A4381E}
AppName=Ariasmos
AppVersion={#VersionApp}
AppVerName=Ariasmos {#VersionApp}
AppPublisher=Ariasmos
DefaultDirName={commonpf}\Ariasmos
DisableDirPage=yes
DefaultGroupName=Ariasmos
DisableProgramGroupPage=yes
OutputDir={#Raiz}\build\salida
OutputBaseFilename=Ariasmos-{#VersionApp}-instalador
Compression=lzma2/max
SolidCompression=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
WizardStyle=modern
UninstallDisplayName=Ariasmos
SetupLogging=yes
CloseApplications=yes
CloseApplicationsFilter=Ariasmos.exe
RestartApplications=no
LicenseFile={#Raiz}\LICENSE
SetupIconFile={#Raiz}\instalacion\ariasmos.ico
UninstallDisplayIcon={app}\ariasmos.ico

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Files]
Source: "{#Paquete}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion; Check: EsPrincipal
Source: "{#Raiz}\build\escritorio\*"; DestDir: "{app}"; Excludes: "*.pdb"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "{#Raiz}\instalacion\ariasmos.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#Raiz}\instalacion\herramientas\conexion.ps1"; Flags: dontcopy
Source: "{#Raiz}\build\descargas\MicrosoftEdgeWebview2Setup.exe"; Flags: dontcopy

[InstallDelete]
Type: files; Name: "{commondesktop}\Ariasmos.url"
Type: files; Name: "{group}\Ariasmos.url"
Type: files; Name: "{commonappdata}\Ariasmos\certificado\instalar-certificado.cmd"

[Registry]
Root: HKLM; Subkey: "SOFTWARE\Ariasmos"; ValueType: string; ValueName: "Modo"; ValueData: "{code:ModoElegido}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "SOFTWARE\Ariasmos"; ValueType: dword; ValueName: "Puerto"; ValueData: "{code:PuertoElegido}"; Check: EsPrincipal

[Icons]
Name: "{group}\Ariasmos"; Filename: "{app}\Ariasmos.exe"; WorkingDir: "{app}"
Name: "{commondesktop}\Ariasmos"; Filename: "{app}\Ariasmos.exe"; WorkingDir: "{app}"
Name: "{group}\Generar token nuevo del asistente"; Filename: "{app}\herramientas\token-nuevo.cmd"; WorkingDir: "{app}\herramientas"; Check: EsPrincipal
Name: "{group}\Dar permiso a una carpeta"; Filename: "{app}\herramientas\permiso-carpeta.cmd"; WorkingDir: "{app}\herramientas"; Check: EsPrincipal
Name: "{group}\Instalar actualización"; Filename: "{app}\herramientas\instalar-actualizacion.cmd"; WorkingDir: "{app}\herramientas"; IconFilename: "{app}\ariasmos.ico"; Check: EsPrincipal
Name: "{group}\Desinstalar Ariasmos"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\Ariasmos.exe"; WorkingDir: "{app}"; Description: "Abrir Ariasmos"; Flags: postinstall nowait skipifsilent runasoriginaluser; Check: InstalacionCorrecta

[Code]
const
  WM_COPY = $0301;

var
  PaginaModo: TInputOptionWizardPage;
  PaginaPuerto: TInputQueryWizardPage;
  PaginaConexion: TInputFileWizardPage;
  Modo: String;
  Puerto: Integer;
  PuertoAnterior: Integer;
  ConexionExistente: Boolean;
  PaginaRestaurar: TWizardPage;
  CasillaRestaurar: TNewCheckBox;
  EtiquetaArchivo: TNewStaticText;
  EditArchivo: TNewEdit;
  BotonArchivo: TNewButton;
  EtiquetaClave: TNewStaticText;
  EditClave: TNewEdit;
  Token: String;
  Actualizacion: Boolean;
  Restaurada: Boolean;
  ErrorInstalacion: String;
  AvisoRespaldo: String;
  EditToken: TNewEdit;

function CarpetaDatos(): String;
begin
  Result := ExpandConstant('{commonappdata}\Ariasmos');
end;

function HayInstancia(): Boolean;
begin
  Result := FileExists(CarpetaDatos() + '\instancia\configuracion.json');
end;

function EsPrincipal(): Boolean;
begin
  Result := Modo = 'principal';
end;

function EsAdicional(): Boolean;
begin
  Result := Modo = 'adicional';
end;

function ModoElegido(Parametro: String): String;
begin
  Result := Modo;
end;

function PuertoElegido(Parametro: String): String;
begin
  Result := IntToStr(Puerto);
end;

function InstalacionCorrecta(): Boolean;
begin
  Result := ErrorInstalacion = '';
end;

function SistemaPowerShell(): String;
begin
  Result := ExpandConstant('{sysnative}\WindowsPowerShell\v1.0\powershell.exe');
end;

function PuertoLibre(Valor: Integer): Boolean;
var
  Codigo: Integer;
begin
  Result := True;
  if Exec(SistemaPowerShell(), '-NoProfile -NonInteractive -Command "if (Get-NetTCPConnection -State Listen -LocalPort ' + IntToStr(Valor) + ' -ErrorAction SilentlyContinue) { exit 1 } else { exit 0 }"', '', SW_HIDE, ewWaitUntilTerminated, Codigo) then
    Result := Codigo = 0;
end;

function PuertoPropuesto(): Integer;
var
  Candidatos: array[0..4] of Integer;
  I: Integer;
begin
  if PuertoAnterior > 0 then
  begin
    Result := PuertoAnterior;
    Exit;
  end;
  Candidatos[0] := 443;
  Candidatos[1] := 8443;
  Candidatos[2] := 9443;
  Candidatos[3] := 10443;
  Candidatos[4] := 44300;
  Result := 443;
  for I := 0 to 4 do
    if PuertoLibre(Candidatos[I]) then
    begin
      Result := Candidatos[I];
      Exit;
    end;
end;

function PuertoValido(const Texto: String; var Valor: Integer; var Motivo: String): Boolean;
begin
  Result := False;
  Valor := StrToIntDef(Trim(Texto), -1);
  if (Valor < 1) or (Valor > 65535) or (IntToStr(Valor) <> Trim(Texto)) then
    Motivo := 'Escribe un puerto entre 1 y 65535.'
  else if (Valor = 80) or (Valor = 8000) then
    Motivo := 'Los puertos 80 y 8000 los usa el propio sistema; elige otro (por ejemplo 443 u 8443).'
  else if (Valor <> PuertoAnterior) and (not PuertoLibre(Valor)) then
    Motivo := 'El puerto ' + IntToStr(Valor) + ' ya lo usa otro programa en esta computadora; elige otro.'
  else
    Result := True;
end;

function WebView2Instalado(): Boolean;
var
  Version: String;
begin
  Result := False;
  if RegQueryStringValue(HKLM32, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) then
    Result := (Version <> '') and (Version <> '0.0.0.0');
  if (not Result) and RegQueryStringValue(HKCU, 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) then
    Result := (Version <> '') and (Version <> '0.0.0.0');
end;

function ValidarConexion(const Ruta: String; var Motivo: String): Boolean;
var
  Resultado: TExecOutput;
  Codigo: Integer;
  I: Integer;
begin
  Result := False;
  Motivo := 'No se pudo revisar el archivo de conexión.';
  if not FileExists(ExpandConstant('{tmp}\conexion.ps1')) then
    ExtractTemporaryFile('conexion.ps1');
  if not ExecAndCaptureOutput(SistemaPowerShell(), '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File ' + AddQuotes(ExpandConstant('{tmp}\conexion.ps1')) + ' -Accion Validar -Archivo ' + AddQuotes(Ruta), ExpandConstant('{tmp}'), SW_HIDE, ewWaitUntilTerminated, Codigo, Resultado) then
    Exit;
  for I := 0 to GetArrayLength(Resultado.StdOut) - 1 do
  begin
    Log('conexion.ps1: ' + Resultado.StdOut[I]);
    if Pos('ERROR-CONEXION:', Resultado.StdOut[I]) = 1 then
      Motivo := Trim(Copy(Resultado.StdOut[I], Length('ERROR-CONEXION:') + 1, MaxInt));
  end;
  Result := Codigo = 0;
end;

function InstalarConexion(const Ruta: String): Boolean;
var
  Resultado: TExecOutput;
  Codigo: Integer;
  I: Integer;
begin
  Result := False;
  if not FileExists(ExpandConstant('{tmp}\conexion.ps1')) then
    ExtractTemporaryFile('conexion.ps1');
  if not ExecAndCaptureOutput(SistemaPowerShell(), '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File ' + AddQuotes(ExpandConstant('{tmp}\conexion.ps1')) + ' -Accion Instalar -Archivo ' + AddQuotes(Ruta) + ' -Datos ' + AddQuotes(CarpetaDatos()), ExpandConstant('{tmp}'), SW_HIDE, ewWaitUntilTerminated, Codigo, Resultado) then
    Exit;
  for I := 0 to GetArrayLength(Resultado.StdOut) - 1 do
    Log('conexion.ps1: ' + Resultado.StdOut[I]);
  Result := Codigo = 0;
end;

procedure InstalarWebView2();
var
  Codigo: Integer;
begin
  if WebView2Instalado() then
  begin
    Log('WebView2 ya está instalado.');
    Exit;
  end;
  Log('Instalando WebView2 con el instalador oficial de Microsoft.');
  ExtractTemporaryFile('MicrosoftEdgeWebview2Setup.exe');
  if (not Exec(ExpandConstant('{tmp}\MicrosoftEdgeWebview2Setup.exe'), '/silent /install', '', SW_HIDE, ewWaitUntilTerminated, Codigo)) or (not WebView2Instalado()) then
    SuppressibleMsgBox('No se pudo instalar el componente WebView2 de Microsoft, que la ventana de Ariasmos necesita. Conecta esta computadora a internet y vuelve a ejecutar el instalador.', mbError, MB_OK, IDOK);
end;

function PowerShell(): String;
begin
  Result := SistemaPowerShell();
end;

function ParametrosScript(const Script, Extra: String): String;
begin
  Result := '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File ' + AddQuotes(ExpandConstant('{app}\herramientas\') + Script) +
    ' -Programa ' + AddQuotes(ExpandConstant('{app}')) + ' -Datos ' + AddQuotes(CarpetaDatos()) + Extra;
end;

function EjecutarScript(const Script, Extra: String; var Salida: TArrayOfString): Integer;
var
  Resultado: TExecOutput;
  Codigo: Integer;
  I: Integer;
begin
  SetArrayLength(Salida, 0);
  Log('Ejecutando ' + Script);
  if not ExecAndCaptureOutput(PowerShell(), ParametrosScript(Script, Extra), ExpandConstant('{app}\herramientas'), SW_HIDE, ewWaitUntilTerminated, Codigo, Resultado) then
  begin
    Log('No se pudo ejecutar ' + Script + ': ' + SysErrorMessage(Codigo));
    Result := -1;
    Exit;
  end;
  Salida := Resultado.StdOut;
  for I := 0 to GetArrayLength(Resultado.StdOut) - 1 do
    if Pos('TOKEN-ASISTENTE:', Resultado.StdOut[I]) = 0 then
      Log(Script + ': ' + Resultado.StdOut[I]);
  for I := 0 to GetArrayLength(Resultado.StdErr) - 1 do
    Log(Script + ' (error): ' + Resultado.StdErr[I]);
  Log(Script + ' terminó con código ' + IntToStr(Codigo));
  Result := Codigo;
end;

function BuscarLinea(const Salida: TArrayOfString; const Prefijo: String): String;
var
  I: Integer;
begin
  Result := '';
  for I := 0 to GetArrayLength(Salida) - 1 do
    if Pos(Prefijo, Salida[I]) = 1 then
      Result := Trim(Copy(Salida[I], Length(Prefijo) + 1, MaxInt));
end;

procedure ElegirArchivo(Sender: TObject);
var
  Archivo: String;
begin
  Archivo := EditArchivo.Text;
  if GetOpenFileName('Archivo de respaldo', Archivo, '', 'Respaldos de Ariasmos (*.respaldo)|*.respaldo', 'respaldo') then
    EditArchivo.Text := Archivo;
end;

procedure CambioRestaurar(Sender: TObject);
begin
  EditArchivo.Enabled := CasillaRestaurar.Checked;
  BotonArchivo.Enabled := CasillaRestaurar.Checked;
  EditClave.Enabled := CasillaRestaurar.Checked;
end;

procedure InitializeWizard();
var
  Parametro: String;
  Anterior: String;
  ValorPuerto: Cardinal;
begin
  Actualizacion := HayInstancia();
  ConexionExistente := FileExists(CarpetaDatos() + '\conexion.json');
  PuertoAnterior := 0;
  if RegQueryDWordValue(HKLM, 'SOFTWARE\Ariasmos', 'Puerto', ValorPuerto) then
    PuertoAnterior := ValorPuerto
  else if Actualizacion then
    PuertoAnterior := 443;
  Anterior := '';
  RegQueryStringValue(HKLM, 'SOFTWARE\Ariasmos', 'Modo', Anterior);
  Parametro := Lowercase(Trim(ExpandConstant('{param:MODO|}')));
  if Actualizacion then
    Modo := 'principal'
  else if (Parametro = 'principal') or (Parametro = 'adicional') then
    Modo := Parametro
  else if (Anterior = 'principal') or (Anterior = 'adicional') then
    Modo := Anterior
  else
    Modo := 'principal';

  PaginaModo := CreateInputOptionPage(wpLicense, 'Tipo de computadora', '¿Qué papel tiene esta computadora?',
    'Si el negocio usa una sola computadora, elige «Computadora principal». Cada computadora adicional necesita el archivo de conexión que se genera en la principal (Equipos, «Conectar otra computadora»).', True, False);
  PaginaModo.Add('Computadora principal: guarda los datos y da servicio a las demás.');
  PaginaModo.Add('Computadora adicional: solo instala el programa y se conecta a la principal.');
  if Modo = 'adicional' then
    PaginaModo.SelectedValueIndex := 1
  else
    PaginaModo.SelectedValueIndex := 0;

  PaginaPuerto := CreateInputQueryPage(PaginaModo.ID, 'Puerto', 'Puerto por el que las demás computadoras se conectan a esta.',
    'Se propone 443; si otro programa ya lo usa, se propone otro libre. El puerto queda en el archivo de conexión.');
  PaginaPuerto.Add('Puerto:', False);
  Parametro := Trim(ExpandConstant('{param:PUERTO|}'));
  if Parametro <> '' then
    PaginaPuerto.Values[0] := Parametro
  else
    PaginaPuerto.Values[0] := IntToStr(PuertoPropuesto());

  PaginaConexion := CreateInputFilePage(PaginaModo.ID, 'Archivo de conexión', 'Elige el archivo de conexión que se generó en la computadora principal.',
    'En la computadora principal: Equipos, «Conectar otra computadora», «Descargar el archivo de conexión». Tráelo en una memoria USB o en persona, nunca por correo ni por un chat.');
  PaginaConexion.Add('Archivo de conexión (ariasmos-conexion.json):', 'Archivo de conexión de Ariasmos (*.json)|*.json|Todos los archivos (*.*)|*.*', '.json');
  PaginaConexion.Values[0] := Trim(ExpandConstant('{param:CONEXION|}'));

  PaginaRestaurar := CreateCustomPage(PaginaPuerto.ID, 'Restaurar desde un respaldo', 'Solo si este equipo reemplaza a otro donde ya se usaba el sistema.');
  CasillaRestaurar := TNewCheckBox.Create(PaginaRestaurar);
  CasillaRestaurar.Parent := PaginaRestaurar.Surface;
  CasillaRestaurar.Caption := 'Restaurar la información desde un archivo de respaldo (.respaldo)';
  CasillaRestaurar.Width := PaginaRestaurar.SurfaceWidth;
  CasillaRestaurar.OnClick := @CambioRestaurar;
  EtiquetaArchivo := TNewStaticText.Create(PaginaRestaurar);
  EtiquetaArchivo.Parent := PaginaRestaurar.Surface;
  EtiquetaArchivo.Top := CasillaRestaurar.Top + ScaleY(32);
  EtiquetaArchivo.Caption := 'Archivo de respaldo:';
  EditArchivo := TNewEdit.Create(PaginaRestaurar);
  EditArchivo.Parent := PaginaRestaurar.Surface;
  EditArchivo.Top := EtiquetaArchivo.Top + ScaleY(18);
  EditArchivo.Width := PaginaRestaurar.SurfaceWidth - ScaleX(90);
  BotonArchivo := TNewButton.Create(PaginaRestaurar);
  BotonArchivo.Parent := PaginaRestaurar.Surface;
  BotonArchivo.Top := EditArchivo.Top - ScaleY(1);
  BotonArchivo.Left := EditArchivo.Width + ScaleX(8);
  BotonArchivo.Width := ScaleX(80);
  BotonArchivo.Caption := 'Elegir...';
  BotonArchivo.OnClick := @ElegirArchivo;
  EtiquetaClave := TNewStaticText.Create(PaginaRestaurar);
  EtiquetaClave.Parent := PaginaRestaurar.Surface;
  EtiquetaClave.Top := EditArchivo.Top + ScaleY(36);
  EtiquetaClave.Caption := 'Clave de recuperación (la que imprimiste al instalar):';
  EditClave := TNewEdit.Create(PaginaRestaurar);
  EditClave.Parent := PaginaRestaurar.Surface;
  EditClave.Top := EtiquetaClave.Top + ScaleY(18);
  EditClave.Width := PaginaRestaurar.SurfaceWidth;
  EditClave.PasswordChar := '*';
  CambioRestaurar(nil);
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
  if PageID = PaginaModo.ID then
    Result := Actualizacion
  else if PageID = PaginaPuerto.ID then
    Result := not EsPrincipal()
  else if PageID = PaginaConexion.ID then
    Result := not EsAdicional()
  else if PageID = PaginaRestaurar.ID then
    Result := Actualizacion or (not EsPrincipal());
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Motivo: String;
  Valor: Integer;
begin
  Result := True;
  if CurPageID = PaginaModo.ID then
  begin
    if PaginaModo.SelectedValueIndex = 1 then
      Modo := 'adicional'
    else
      Modo := 'principal';
  end
  else if CurPageID = PaginaPuerto.ID then
  begin
    if PuertoValido(PaginaPuerto.Values[0], Valor, Motivo) then
      Puerto := Valor
    else
    begin
      SuppressibleMsgBox(Motivo, mbError, MB_OK, IDOK);
      Result := False;
    end;
  end
  else if CurPageID = PaginaConexion.ID then
  begin
    if (Trim(PaginaConexion.Values[0]) = '') and ConexionExistente then
      Result := True
    else if not ValidarConexion(Trim(PaginaConexion.Values[0]), Motivo) then
    begin
      SuppressibleMsgBox('El archivo de conexión no sirve: ' + Motivo, mbError, MB_OK, IDOK);
      Result := False;
    end;
  end
  else if (CurPageID = PaginaRestaurar.ID) and CasillaRestaurar.Checked then
  begin
    if not FileExists(EditArchivo.Text) then
    begin
      MsgBox('Elige un archivo de respaldo que exista.', mbError, MB_OK);
      Result := False;
    end
    else if Length(Trim(EditClave.Text)) < 20 then
    begin
      MsgBox('Escribe la clave de recuperación completa.', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Salida: TArrayOfString;
  Codigo: Integer;
  Motivo: String;
  Valor: Integer;
begin
  Result := '';
  if Actualizacion and EsAdicional() then
  begin
    Result := 'Esta computadora ya es la principal (tiene los datos del negocio): no se puede instalar como adicional.';
    Exit;
  end;
  if EsPrincipal() and (Puerto = 0) then
  begin
    if PuertoValido(PaginaPuerto.Values[0], Valor, Motivo) then
      Puerto := Valor
    else
    begin
      Result := Motivo;
      Exit;
    end;
  end;
  if EsAdicional() and not ((Trim(PaginaConexion.Values[0]) = '') and ConexionExistente) then
    if not ValidarConexion(Trim(PaginaConexion.Values[0]), Motivo) then
    begin
      Result := 'El archivo de conexión no sirve: ' + Motivo;
      Exit;
    end;
  if Actualizacion and FileExists(ExpandConstant('{app}\herramientas\preparar-actualizacion.ps1')) then
  begin
    Codigo := EjecutarScript('preparar-actualizacion.ps1', '', Salida);
    AvisoRespaldo := BuscarLinea(Salida, 'AVISO-RESPALDO:');
    if Codigo <> 0 then
      Result := 'No se pudo preparar la actualización: ' + BuscarLinea(Salida, 'ERROR-INSTALACION:') + #13#10 + 'Revisa ' + CarpetaDatos() + '\registros\instalacion.log';
  end;
end;

procedure Restaurar();
var
  Salida: TArrayOfString;
  ArchivoClave: String;
  Codigo: Integer;
begin
  ArchivoClave := ExpandConstant('{tmp}\clave-recuperacion.txt');
  if not SaveStringToFile(ArchivoClave, Trim(EditClave.Text), False) then
  begin
    ErrorInstalacion := 'No se pudo preparar la restauración.';
    Exit;
  end;
  EditClave.Text := '';
  Codigo := EjecutarScript('restaurar.ps1', ' -Archivo ' + AddQuotes(EditArchivo.Text) + ' -ClaveArchivo ' + AddQuotes(ArchivoClave), Salida);
  DeleteFile(ArchivoClave);
  if Codigo <> 0 then
    ErrorInstalacion := 'La restauración falló: ' + BuscarLinea(Salida, 'ERROR-INSTALACION:')
  else
    Restaurada := True;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Salida: TArrayOfString;
  ModoScript: String;
  Codigo: Integer;
begin
  if CurStep <> ssPostInstall then
    Exit;
  ErrorInstalacion := '';
  InstalarWebView2();
  if EsAdicional() then
  begin
    if not ((Trim(PaginaConexion.Values[0]) = '') and ConexionExistente) then
      if not InstalarConexion(Trim(PaginaConexion.Values[0])) then
      begin
        ErrorInstalacion := 'No se pudo guardar el archivo de conexión.';
        SuppressibleMsgBox(ErrorInstalacion, mbCriticalError, MB_OK, IDOK);
      end;
    Exit;
  end;
  if (not Actualizacion) and CasillaRestaurar.Checked then
    Restaurar();
  if ErrorInstalacion <> '' then
  begin
    SuppressibleMsgBox(ErrorInstalacion + #13#10#13#10 + 'Revisa ' + CarpetaDatos() + '\registros\instalacion.log', mbCriticalError, MB_OK, IDOK);
    Exit;
  end;
  if Actualizacion then
    ModoScript := 'actualizar'
  else if Restaurada then
    ModoScript := 'restaurada'
  else
    ModoScript := 'nueva';
  Codigo := EjecutarScript('instalar.ps1', ' -Modo ' + ModoScript + ' -Puerto ' + IntToStr(Puerto), Salida);
  Token := BuscarLinea(Salida, 'TOKEN-ASISTENTE:');
  if Codigo <> 0 then
  begin
    ErrorInstalacion := BuscarLinea(Salida, 'ERROR-INSTALACION:');
    SuppressibleMsgBox('La instalación no terminó: ' + ErrorInstalacion + #13#10#13#10 + 'Revisa ' + CarpetaDatos() + '\registros\instalacion.log', mbCriticalError, MB_OK, IDOK);
  end
  else if AvisoRespaldo <> '' then
    SuppressibleMsgBox('Aviso: ' + AvisoRespaldo, mbInformation, MB_OK, IDOK);
end;

procedure CopiarToken(Sender: TObject);
begin
  EditToken.SelectAll();
  SendMessage(EditToken.Handle, WM_COPY, 0, 0);
  MsgBox('Token copiado. Pégalo en el primer paso del asistente.', mbInformation, MB_OK);
end;

procedure CurPageChanged(CurPageID: Integer);
var
  Etiqueta: TNewStaticText;
  Boton: TNewButton;
begin
  if CurPageID <> wpFinished then
    Exit;
  Etiqueta := TNewStaticText.Create(WizardForm.FinishedPage);
  Etiqueta.Parent := WizardForm.FinishedPage;
  Etiqueta.Left := WizardForm.FinishedLabel.Left;
  Etiqueta.Top := WizardForm.FinishedLabel.Top + WizardForm.FinishedLabel.Height + ScaleY(12);
  Etiqueta.Width := WizardForm.FinishedLabel.Width;
  Etiqueta.AutoSize := False;
  Etiqueta.WordWrap := True;
  Etiqueta.Height := ScaleY(60);
  if ErrorInstalacion <> '' then
    Etiqueta.Caption := 'La instalación no terminó bien. Revisa ' + CarpetaDatos() + '\registros\instalacion.log y vuelve a ejecutar el instalador.'
  else if EsAdicional() then
    Etiqueta.Caption := 'Ariasmos quedó instalado en esta computadora. Al abrirlo por primera vez queda pendiente de aprobación: apruébala en la computadora principal (Equipos).'
  else if Token <> '' then
  begin
    Etiqueta.Caption := 'Token del asistente. Se pide en el primer paso y no se vuelve a mostrar: cópialo ahora. Si lo pierdes, usa "Generar token nuevo del asistente" en el menú Inicio.';
    EditToken := TNewEdit.Create(WizardForm.FinishedPage);
    EditToken.Parent := WizardForm.FinishedPage;
    EditToken.Left := Etiqueta.Left;
    EditToken.Top := Etiqueta.Top + Etiqueta.Height + ScaleY(4);
    EditToken.Width := Etiqueta.Width - ScaleX(90);
    EditToken.ReadOnly := True;
    EditToken.Text := Token;
    Boton := TNewButton.Create(WizardForm.FinishedPage);
    Boton.Parent := WizardForm.FinishedPage;
    Boton.Left := EditToken.Left + EditToken.Width + ScaleX(8);
    Boton.Top := EditToken.Top - ScaleY(1);
    Boton.Width := ScaleX(80);
    Boton.Caption := 'Copiar';
    Boton.OnClick := @CopiarToken;
  end
  else if Restaurada then
    Etiqueta.Caption := 'La información se restauró desde el respaldo. Entra con tus usuarios de siempre.'
  else
    Etiqueta.Caption := 'Ariasmos se actualizó. Los datos se conservaron.';
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Resultado: TExecOutput;
  Codigo: Integer;
  Accion: String;
begin
  if CurUninstallStep <> usUninstall then
    Exit;
  if not FileExists(ExpandConstant('{app}\herramientas\desinstalar.ps1')) then
  begin
    DeleteFile(ExpandConstant('{commonappdata}\Ariasmos\conexion.json'));
    Exit;
  end;
  Accion := 'conservar';
  if SuppressibleMsgBox('¿Borrar también los datos?' + #13#10#13#10 +
    'Si eliges Sí se borran la base de datos, las claves y los registros de ' + CarpetaDatos() + '. No se puede deshacer y sin un respaldo la información se pierde.' + #13#10#13#10 +
    'Elige No para conservarlos (recomendado).', mbConfirmation, MB_YESNO or MB_DEFBUTTON2, IDNO) = IDYES then
    Accion := 'borrar';
  if not ExecAndCaptureOutput(PowerShell(), ParametrosScript('desinstalar.ps1', ' -DatosAccion ' + Accion), ExpandConstant('{app}\herramientas'), SW_HIDE, ewWaitUntilTerminated, Codigo, Resultado) then
    SuppressibleMsgBox('No se pudo ejecutar el desinstalador de los servicios.', mbError, MB_OK, IDOK)
  else if Codigo <> 0 then
    SuppressibleMsgBox('Algunos pasos de la desinstalación fallaron. Revisa ' + CarpetaDatos() + '\registros\instalacion.log', mbError, MB_OK, IDOK);
end;
