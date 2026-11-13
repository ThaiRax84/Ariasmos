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
CloseApplications=no
LicenseFile={#Raiz}\LICENSE
SetupIconFile={#Raiz}\instalacion\ariasmos.ico
UninstallDisplayIcon={app}\ariasmos.ico

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Files]
Source: "{#Paquete}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "{#Raiz}\instalacion\ariasmos.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Ariasmos"; Filename: "https://localhost/"; IconFilename: "{app}\ariasmos.ico"
Name: "{commondesktop}\Ariasmos"; Filename: "https://localhost/"; IconFilename: "{app}\ariasmos.ico"
Name: "{group}\Generar token nuevo del asistente"; Filename: "{app}\herramientas\token-nuevo.cmd"; WorkingDir: "{app}\herramientas"
Name: "{group}\Dar permiso a una carpeta"; Filename: "{app}\herramientas\permiso-carpeta.cmd"; WorkingDir: "{app}\herramientas"
Name: "{group}\Instalar actualización"; Filename: "{app}\herramientas\instalar-actualizacion.cmd"; WorkingDir: "{app}\herramientas"; IconFilename: "{app}\ariasmos.ico"
Name: "{group}\Desinstalar Ariasmos"; Filename: "{uninstallexe}"

[Run]
Filename: "https://localhost/"; Description: "Abrir Ariasmos en el navegador"; Flags: postinstall shellexec nowait skipifsilent

[Code]
const
  WM_COPY = $0301;

var
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

function PowerShell(): String;
begin
  Result := ExpandConstant('{sysnative}\WindowsPowerShell\v1.0\powershell.exe');
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
begin
  Actualizacion := HayInstancia();
  PaginaRestaurar := CreateCustomPage(wpLicense, 'Restaurar desde un respaldo', 'Solo si este equipo reemplaza a otro donde ya se usaba el sistema.');
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
  Result := (PageID = PaginaRestaurar.ID) and Actualizacion;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID = PaginaRestaurar.ID) and CasillaRestaurar.Checked then
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
begin
  Result := '';
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
  Modo: String;
  Codigo: Integer;
begin
  if CurStep <> ssPostInstall then
    Exit;
  ErrorInstalacion := '';
  if (not Actualizacion) and CasillaRestaurar.Checked then
    Restaurar();
  if ErrorInstalacion <> '' then
  begin
    SuppressibleMsgBox(ErrorInstalacion + #13#10#13#10 + 'Revisa ' + CarpetaDatos() + '\registros\instalacion.log', mbCriticalError, MB_OK, IDOK);
    Exit;
  end;
  if Actualizacion then
    Modo := 'actualizar'
  else if Restaurada then
    Modo := 'restaurada'
  else
    Modo := 'nueva';
  Codigo := EjecutarScript('instalar.ps1', ' -Modo ' + Modo, Salida);
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
