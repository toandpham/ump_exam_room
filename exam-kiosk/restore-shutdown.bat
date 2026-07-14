@echo off
REM ============================================================
REM  Khoi phuc nut Shutdown / nguon sau khi thoat Exam Kiosk
REM  Chay bang quyen Administrator (chuot phai -> Run as administrator)
REM ============================================================
echo Dang khoi phuc chinh sach Windows...

REM --- Xoa cac policy khoa (idempotent - khong sao neu da xoa) ---
for %%H in (HKLM HKCU) do (
  reg delete "%%H\Software\Microsoft\Windows\CurrentVersion\Policies\Explorer" /v NoClose /f >nul 2>&1
  reg delete "%%H\Software\Microsoft\Windows\CurrentVersion\Policies\Explorer" /v NoLogoff /f >nul 2>&1
  reg delete "%%H\Software\Microsoft\Windows\CurrentVersion\Policies\Explorer" /v StartMenuLogOff /f >nul 2>&1
  reg delete "%%H\Software\Microsoft\Windows\CurrentVersion\Policies\System" /v DisableTaskMgr /f >nul 2>&1
  reg delete "%%H\Software\Microsoft\Windows\CurrentVersion\Policies\System" /v DisableLockWorkstation /f >nul 2>&1
  reg delete "%%H\Software\Microsoft\Windows\CurrentVersion\Policies\System" /v DisableChangePassword /f >nul 2>&1
)

REM --- Nut nguon tren man dang nhap / Ctrl+Alt+Del ---
reg add "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System" /v shutdownwithoutlogon /t REG_DWORD /d 1 /f >nul 2>&1
reg delete "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System" /v HideFastUserSwitching /f >nul 2>&1

REM --- Bat lai Task Manager ---
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Policies\System" /v DisableTaskMgr /f >nul 2>&1

REM --- Refresh Explorer de nut Shut Down hien lai NGAY (khong can reboot) ---
echo Dang khoi dong lai Explorer...
taskkill /f /im explorer.exe >nul 2>&1
start "" explorer.exe

echo.
echo Xong! Nut Shutdown da duoc khoi phuc.
echo Neu van chua thay, hay khoi dong lai may (Restart).
pause
