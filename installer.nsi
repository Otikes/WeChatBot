; WeChatBot Windows Installer
; Build: "C:\Program Files (x86)\NSIS\makensis.exe" installer.nsi
; Output: dist/WeChatBot-setup.exe

Unicode true
!include "MUI2.nsh"
!include "FileFunc.nsh"
!include "LogicLib.nsh"
!include "nsDialogs.nsh"

; ── Product Info ──────────────────────────────────────────────────────
!define PRODUCT_NAME "WeChatBot"
!define PRODUCT_DESC "WeChatBot - 微信 AI 群聊助手"
!ifndef PRODUCT_VERSION
!define PRODUCT_VERSION "1.2.2"
!endif
!define PRODUCT_PUBLISHER "Otikes"
!define PRODUCT_URL "https://github.com/Otikes/WeChatBot"
!define REG_UNINSTALL_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}"
; 旧版 webot 的注册表键：升级时用它找回原安装目录与数据目录
!define LEGACY_REG_UNINSTALL_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\webot"

Name "${PRODUCT_NAME} ${PRODUCT_VERSION}"
OutFile "dist\WeChatBot-setup.exe"
InstallDir "$LOCALAPPDATA\${PRODUCT_NAME}"
InstallDirRegKey HKCU "${REG_UNINSTALL_KEY}" "InstallLocation"
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

; ── Upgrade Defaults ──────────────────────────────────────────────────
Function .onInit
  Call RestorePreviousInstallDir
  Call RestorePreviousWebotDataDir
FunctionEnd

Function RestorePreviousInstallDir
  StrCpy $1 ""

  ReadRegStr $0 HKCU "${REG_UNINSTALL_KEY}" "InstallLocation"
  ${If} "$0" != ""
    IfFileExists "$0\*.*" 0 +2
      StrCpy $1 "$0"
  ${EndIf}

  ; 从旧版 webot 升级：新注册表键还不存在时读旧键
  ${If} "$1" == ""
    ReadRegStr $0 HKCU "${LEGACY_REG_UNINSTALL_KEY}" "InstallLocation"
    ${If} "$0" != ""
      IfFileExists "$0\*.*" 0 +2
        StrCpy $1 "$0"
    ${EndIf}
  ${EndIf}

  ; Older installers did not persist InstallLocation. Fall back to the
  ; registered uninstaller path and use its parent directory.
  ${If} "$1" == ""
    ReadRegStr $0 HKCU "${REG_UNINSTALL_KEY}" "UninstallString"
    ${If} "$0" != ""
      StrCpy $2 $0 1
      ${If} "$2" == '"'
        StrCpy $0 $0 "" 1
      ${EndIf}
      ${GetParent} "$0" $1
    ${EndIf}
  ${EndIf}

  ${If} "$1" != ""
    IfFileExists "$1\*.*" 0 +2
      StrCpy $INSTDIR "$1"
  ${EndIf}
FunctionEnd

Function RestorePreviousWebotDataDir
  ReadRegStr $WebotDataDir HKCU "${REG_UNINSTALL_KEY}" "WebotDataDir"
  ${If} "$WebotDataDir" == ""
    ReadRegStr $WebotDataDir HKCU "${LEGACY_REG_UNINSTALL_KEY}" "WebotDataDir"
  ${EndIf}
  ${If} "$WebotDataDir" == ""
    Call ReadWebotDataDirFromEnv
  ${EndIf}
FunctionEnd

Function ReadWebotDataDirFromEnv
  IfFileExists "$INSTDIR\.env" 0 done

  ClearErrors
  FileOpen $0 "$INSTDIR\.env" r
  IfErrors done

  loop:
    FileRead $0 $1
    IfErrors close

    StrCpy $2 $1 15
    ${If} "$2" == "WEBOT_DATA_DIR="
      StrCpy $WebotDataDir $1 "" 15

      StrCpy $2 $WebotDataDir 1 -1
      ${If} "$2" == "$\n"
        StrCpy $WebotDataDir $WebotDataDir -1
      ${EndIf}

      StrCpy $2 $WebotDataDir 1 -1
      ${If} "$2" == "$\r"
        StrCpy $WebotDataDir $WebotDataDir -1
      ${EndIf}
    ${EndIf}
    Goto loop

  close:
    FileClose $0

  done:
FunctionEnd

; ── Data Directory Page ────────────────────────────────────────────────
Function WebotDataDirPageCreate
  !insertmacro MUI_HEADER_TEXT "选择数据存储位置" "选择 WeChatBot 自身数据的保存文件夹。"

  ${If} "$WebotDataDir" == ""
    StrCpy $WebotDataDir "$INSTDIR\data"
  ${EndIf}

  nsDialogs::Create 1018
  Pop $0
  ${If} $0 == error
    Abort
  ${EndIf}

  ${NSD_CreateLabel} 0 0 100% 28u "WeChatBot 自身生成的数据会保存在下面的目录，包括 messages.db、bot.log、昵称、欢迎模板、群缓存等。$\r$\n微信自己的聊天记录目录不会被移动或修改。"
  Pop $0

  ${NSD_CreateGroupBox} 0 44u 100% 52u "WeChatBot 数据目录"
  Pop $0

  ${NSD_CreateText} 12u 64u 68% 13u "$WebotDataDir"
  Pop $WebotDataDirText

  ${NSD_CreateBrowseButton} 76% 62u 22% 16u "浏览(&B)..."
  Pop $0
  ${NSD_OnClick} $0 WebotDataDirBrowse

  ${NSD_CreateLabel} 0 108u 100% 18u "之后也可以在 WeChatBot 的「系统配置 → 数据路径」里修改。"
  Pop $0

  nsDialogs::Show
FunctionEnd

Function WebotDataDirBrowse
  nsDialogs::SelectFolderDialog "选择 WeChatBot 数据存储目录" "$WebotDataDir"
  Pop $0
  ${If} $0 != error
    StrCpy $WebotDataDir "$0"
    ${NSD_SetText} $WebotDataDirText "$WebotDataDir"
  ${EndIf}
FunctionEnd

Function WebotDataDirPageLeave
  ${NSD_GetText} $WebotDataDirText $WebotDataDir
  ${If} "$WebotDataDir" == ""
    MessageBox MB_ICONEXCLAMATION "请选择 WeChatBot 数据存储目录。"
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
    FileWrite $0 "$\r$\n; WeChatBot data dir selected by installer.$\r$\nWEBOT_DATA_DIR=$WebotDataDir$\r$\n"
    FileClose $0
FunctionEnd

Function PrepareWebotExeForUpdate
  IfFileExists "$INSTDIR\WeChatBot.exe" 0 done

  ClearErrors
  Delete "$INSTDIR\WeChatBot.exe"
  IfErrors 0 done

  IfSilent close_running_webot 0
  MessageBox MB_OKCANCEL|MB_ICONINFORMATION \
    "检测到 WeChatBot 正在运行或 WeChatBot.exe 正被占用。安装程序需要先关闭 WeChatBot，然后继续更新。$\r$\n$\r$\n点击「确定」自动关闭 WeChatBot 并继续安装；点击「取消」停止安装。" \
    IDOK close_running_webot IDCANCEL cancel_install

  close_running_webot:
    DetailPrint "正在关闭运行中的 WeChatBot..."
    nsExec::ExecToStack '"$SYSDIR\taskkill.exe" /IM WeChatBot.exe /T /F'
    Pop $0
    Pop $1
    ; 旧版进程仍叫 webot.exe，一并关闭，否则旧 EXE 会占用文件
    nsExec::ExecToStack '"$SYSDIR\taskkill.exe" /IM webot.exe /T /F'
    Pop $0
    Pop $1
    Sleep 1500

  ClearErrors
  Delete "$INSTDIR\WeChatBot.exe"
  IfErrors still_locked done

  still_locked:
    IfSilent silent_abort 0
    MessageBox MB_RETRYCANCEL|MB_ICONEXCLAMATION \
      "仍然无法写入：$\r$\n$INSTDIR\WeChatBot.exe$\r$\n$\r$\n请确认 WeChatBot 已关闭，然后点击「重试」；或点击「取消」停止安装。" \
      IDRETRY close_running_webot IDCANCEL cancel_install

  silent_abort:
    Abort "无法更新 $INSTDIR\WeChatBot.exe。请关闭 WeChatBot 后重试安装。"

  cancel_install:
    Abort

  done:
FunctionEnd

; ── Install Section ────────────────────────────────────────────────────
Section "Install"
  SetOutPath "$INSTDIR"

  ; Main executable
  Call PrepareWebotExeForUpdate
  File "dist\WeChatBot.exe"
  File ".env.example"

  ; Native DLLs (VC++ runtime + wx_key hook fallback)
  SetOutPath "$INSTDIR\native\windows"
  File "native\windows\wx_key.dll"
  File "native\windows\MSVCP140.dll"
  File "native\windows\VCRUNTIME140.dll"
  File "native\windows\VCRUNTIME140_1.dll"
  SetOutPath "$INSTDIR"

  ; Create selected WeChatBot data directory and persist it to .env.
  Call WriteWebotDataDirEnv

  ; Start Menu shortcut
  CreateDirectory "$SMPROGRAMS\${PRODUCT_NAME}"
  CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\${PRODUCT_NAME}.lnk" \
    "$INSTDIR\WeChatBot.exe" "" "$INSTDIR\WeChatBot.exe" 0

  CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\卸载 WeChatBot.lnk" \
    "$INSTDIR\uninstall.exe"

  ; Desktop shortcut
  CreateShortCut "$DESKTOP\${PRODUCT_NAME}.lnk" \
    "$INSTDIR\WeChatBot.exe" "" "$INSTDIR\WeChatBot.exe" 0

  ; Write uninstaller
  WriteUninstaller "$INSTDIR\uninstall.exe"

  ; Registry for Add/Remove Programs
  WriteRegStr HKCU "${REG_UNINSTALL_KEY}" \
    "DisplayName" "${PRODUCT_NAME} - ${PRODUCT_DESC}"
  WriteRegStr HKCU "${REG_UNINSTALL_KEY}" \
    "UninstallString" "$INSTDIR\uninstall.exe"
  WriteRegStr HKCU "${REG_UNINSTALL_KEY}" \
    "QuietUninstallString" "$INSTDIR\uninstall.exe /S"
  WriteRegStr HKCU "${REG_UNINSTALL_KEY}" \
    "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${REG_UNINSTALL_KEY}" \
    "WebotDataDir" "$WebotDataDir"
  WriteRegStr HKCU "${REG_UNINSTALL_KEY}" \
    "DisplayIcon" "$INSTDIR\WeChatBot.exe"
  WriteRegStr HKCU "${REG_UNINSTALL_KEY}" \
    "DisplayVersion" "${PRODUCT_VERSION}"
  WriteRegStr HKCU "${REG_UNINSTALL_KEY}" \
    "Publisher" "${PRODUCT_PUBLISHER}"
  WriteRegStr HKCU "${REG_UNINSTALL_KEY}" \
    "URLInfoAbout" "${PRODUCT_URL}"

  ; Size estimation
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  WriteRegDWORD HKCU "${REG_UNINSTALL_KEY}" \
    "EstimatedSize" $0
  WriteRegDWORD HKCU "${REG_UNINSTALL_KEY}" \
    "NoModify" 1
  WriteRegDWORD HKCU "${REG_UNINSTALL_KEY}" \
    "NoRepair" 1
SectionEnd

; ── Uninstall Section ──────────────────────────────────────────────────
Section "Uninstall"
  ; Remove installed files (preserve user data: .env, data/*)
  Delete "$INSTDIR\WeChatBot.exe"
  ; 兼容旧版安装残留
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
  Delete "$SMPROGRAMS\${PRODUCT_NAME}\卸载 WeChatBot.lnk"
  ; 兼容旧版快捷方式
  Delete "$SMPROGRAMS\webot\卸载 webot.lnk"
  Delete "$SMPROGRAMS\webot\webot.lnk"
  RMDir "$SMPROGRAMS\webot"
  RMDir "$SMPROGRAMS\${PRODUCT_NAME}"
  Delete "$DESKTOP\${PRODUCT_NAME}.lnk"
  Delete "$DESKTOP\webot.lnk"

  ; Remove registry
  DeleteRegKey HKCU "${REG_UNINSTALL_KEY}"
  DeleteRegKey HKCU "${LEGACY_REG_UNINSTALL_KEY}"

  ; Remove install dir if empty (user data may remain)
  RMDir "$INSTDIR"
SectionEnd

; ── Version Info ───────────────────────────────────────────────────────
VIProductVersion "${PRODUCT_VERSION}.0"
VIAddVersionKey "ProductName" "${PRODUCT_NAME}"
VIAddVersionKey "ProductVersion" "${PRODUCT_VERSION}"
VIAddVersionKey "FileVersion" "${PRODUCT_VERSION}"
VIAddVersionKey "FileDescription" "${PRODUCT_DESC}"
VIAddVersionKey "LegalCopyright" "MIT License"
VIAddVersionKey "CompanyName" "${PRODUCT_PUBLISHER}"
