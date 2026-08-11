; webot Windows Installer
; Build: "C:\Program Files (x86)\NSIS\makensis.exe" installer.nsi
; Output: dist/webot-setup.exe

Unicode true
!include "MUI2.nsh"
!include "FileFunc.nsh"
!include "LogicLib.nsh"
!include "nsDialogs.nsh"

; ── Product Info ──────────────────────────────────────────────────────
!define PRODUCT_NAME "webot"
!define PRODUCT_DESC "微信 AI 群聊助手"
!ifndef PRODUCT_VERSION
!define PRODUCT_VERSION "1.2.2"
!endif
!define PRODUCT_PUBLISHER "cancelGuMu"
!define PRODUCT_URL "https://github.com/cancelGuMu/webot"

Name "${PRODUCT_NAME} ${PRODUCT_VERSION}"
OutFile "dist\webot-setup.exe"
InstallDir "$LOCALAPPDATA\${PRODUCT_NAME}"
RequestExecutionLevel user
ShowInstDetails show
SetCompressor /SOLID lzma

; ── Installer State ───────────────────────────────────────────────────
Var WebotDataDir
Var WebotDataDirText

; ── Interface Settings ─────────────────────────────────────────────────
!define MUI_ABORTWARNING
!define MUI_ICON "image\logo_assets\logo.ico"
!define MUI_UNICON "image\logo_assets\logo.ico"

; ── Pages ──────────────────────────────────────────────────────────────
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "LICENSE"
!insertmacro MUI_PAGE_DIRECTORY
Page custom WebotDataDirPageCreate WebotDataDirPageLeave
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "SimpChinese"

; ── Data Directory Page ────────────────────────────────────────────────
Function WebotDataDirPageCreate
  !insertmacro MUI_HEADER_TEXT "选择数据存储位置" "选择 webot 自身数据的保存文件夹。"

  ${If} "$WebotDataDir" == ""
    StrCpy $WebotDataDir "$INSTDIR\data"
  ${EndIf}

  nsDialogs::Create 1018
  Pop $0
  ${If} $0 == error
    Abort
  ${EndIf}

  ${NSD_CreateLabel} 0 0 100% 28u "webot 自身生成的数据会保存在下面的目录，包括 messages.db、bot.log、昵称、欢迎模板、群缓存等。$\r$\n微信自己的聊天记录目录不会被移动或修改。"
  Pop $0

  ${NSD_CreateGroupBox} 0 44u 100% 52u "webot 数据目录"
  Pop $0

  ${NSD_CreateText} 12u 64u 68% 13u "$WebotDataDir"
  Pop $WebotDataDirText

  ${NSD_CreateBrowseButton} 76% 62u 22% 16u "浏览(&B)..."
  Pop $0
  ${NSD_OnClick} $0 WebotDataDirBrowse

  ${NSD_CreateLabel} 0 108u 100% 18u "之后也可以在 webot 的「系统配置 → 数据路径」里修改。"
  Pop $0

  nsDialogs::Show
FunctionEnd

Function WebotDataDirBrowse
  nsDialogs::SelectFolderDialog "选择 webot 数据存储目录" "$WebotDataDir"
  Pop $0
  ${If} $0 != error
    StrCpy $WebotDataDir "$0"
    ${NSD_SetText} $WebotDataDirText "$WebotDataDir"
  ${EndIf}
FunctionEnd

Function WebotDataDirPageLeave
  ${NSD_GetText} $WebotDataDirText $WebotDataDir
  ${If} "$WebotDataDir" == ""
    MessageBox MB_ICONEXCLAMATION "请选择 webot 数据存储目录。"
    Abort
  ${EndIf}
FunctionEnd

Function WriteWebotDataDirEnv
  ${If} "$WebotDataDir" == ""
    StrCpy $WebotDataDir "$INSTDIR\data"
  ${EndIf}

  CreateDirectory "$WebotDataDir"

  IfFileExists "$INSTDIR\.env" env_ready 0
    CopyFiles /SILENT "$INSTDIR\.env.example" "$INSTDIR\.env"
    IfErrors 0 env_ready
      FileOpen $0 "$INSTDIR\.env" w
      FileClose $0

  env_ready:
    FileOpen $0 "$INSTDIR\.env" a
    FileSeek $0 0 END
    FileWrite $0 "$\r$\n; webot data dir selected by installer.$\r$\nWEBOT_DATA_DIR=$WebotDataDir$\r$\n"
    FileClose $0
FunctionEnd

; ── Install Section ────────────────────────────────────────────────────
Section "Install"
  SetOutPath "$INSTDIR"

  ; Main executable
  File "dist\webot.exe"
  File ".env.example"

  ; Native DLLs (VC++ runtime + WCDB + wx_key hook)
  SetOutPath "$INSTDIR\native\windows"
  File "native\windows\wx_key.dll"
  File "native\windows\wcdb_api.dll"
  File "native\windows\WCDB.dll"
  File "native\windows\MSVCP140.dll"
  File "native\windows\VCRUNTIME140.dll"
  File "native\windows\VCRUNTIME140_1.dll"
  SetOutPath "$INSTDIR"

  ; Create selected webot data directory and persist it to .env.
  Call WriteWebotDataDirEnv

  ; Start Menu shortcut
  CreateDirectory "$SMPROGRAMS\${PRODUCT_NAME}"
  CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\${PRODUCT_NAME}.lnk" \
    "$INSTDIR\webot.exe" "" "$INSTDIR\webot.exe" 0

  CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\卸载 webot.lnk" \
    "$INSTDIR\uninstall.exe"

  ; Desktop shortcut
  CreateShortCut "$DESKTOP\${PRODUCT_NAME}.lnk" \
    "$INSTDIR\webot.exe" "" "$INSTDIR\webot.exe" 0

  ; Write uninstaller
  WriteUninstaller "$INSTDIR\uninstall.exe"

  ; Registry for Add/Remove Programs
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" \
    "DisplayName" "${PRODUCT_NAME} - ${PRODUCT_DESC}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" \
    "UninstallString" "$INSTDIR\uninstall.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" \
    "DisplayIcon" "$INSTDIR\webot.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" \
    "DisplayVersion" "${PRODUCT_VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" \
    "Publisher" "${PRODUCT_PUBLISHER}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" \
    "URLInfoAbout" "${PRODUCT_URL}"

  ; Size estimation
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" \
    "EstimatedSize" $0
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" \
    "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" \
    "NoRepair" 1
SectionEnd

; ── Uninstall Section ──────────────────────────────────────────────────
Section "Uninstall"
  ; Remove installed files (preserve user data: .env, data/*)
  Delete "$INSTDIR\webot.exe"
  Delete "$INSTDIR\.env.example"
  Delete "$INSTDIR\uninstall.exe"
  ; Native DLLs
  Delete "$INSTDIR\native\windows\wx_key.dll"
  Delete "$INSTDIR\native\windows\wcdb_api.dll"
  Delete "$INSTDIR\native\windows\WCDB.dll"
  Delete "$INSTDIR\native\windows\MSVCP140.dll"
  Delete "$INSTDIR\native\windows\VCRUNTIME140.dll"
  Delete "$INSTDIR\native\windows\VCRUNTIME140_1.dll"
  RMDir "$INSTDIR\native\windows"
  RMDir "$INSTDIR\native"
  ; data/ directory contains user data (messages.db, bot.log, lots.json, etc.)
  ; and is NOT removed -- the user keeps their chat history and configuration.

  ; Remove shortcuts
  Delete "$SMPROGRAMS\${PRODUCT_NAME}\${PRODUCT_NAME}.lnk"
  Delete "$SMPROGRAMS\${PRODUCT_NAME}\卸载 webot.lnk"
  RMDir "$SMPROGRAMS\${PRODUCT_NAME}"
  Delete "$DESKTOP\${PRODUCT_NAME}.lnk"

  ; Remove registry
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}"

  ; Remove install dir if empty (user data may remain)
  RMDir "$INSTDIR"
SectionEnd

; ── Version Info ───────────────────────────────────────────────────────
VIProductVersion "${PRODUCT_VERSION}.0"
VIAddVersionKey "ProductName" "${PRODUCT_NAME}"
VIAddVersionKey "ProductVersion" "${PRODUCT_VERSION}"
VIAddVersionKey "FileDescription" "${PRODUCT_DESC}"
VIAddVersionKey "LegalCopyright" "MIT License"
VIAddVersionKey "CompanyName" "${PRODUCT_PUBLISHER}"
