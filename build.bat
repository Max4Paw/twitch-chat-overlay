@echo off
REM ============================================================
REM  Сборка Twitch Chat Overlay в один .exe с правильной иконкой.
REM  В конце автоматически сбрасывается кэш иконок Windows.
REM ============================================================

cd /d "%~dp0"

if not exist assets\icon.ico (
    echo [ERR] Не найден assets\icon.ico — сборка остановлена.
    pause
    exit /b 1
)

echo Сборка из chat_overlay.py (основной код программы)
echo.
echo [1/5] Установка зависимостей...
python -m pip install --upgrade pip >nul
python -m pip install pyinstaller pystray Pillow keyboard

echo.
echo [2/5] Очистка прошлой сборки...
if exist build  rmdir /s /q build
if exist dist   rmdir /s /q dist
REM удаляем старый spec — чтобы PyInstaller не подхватил его без наших флагов
if exist twitch_overlay.spec del /q twitch_overlay.spec

echo.
echo [3/5] Сборка PyInstaller (без UPX — UPX иногда портит иконку)...
python -m PyInstaller ^
    --onefile ^
    --windowed ^
    --noupx ^
    --name=twitch_overlay ^
    --icon=assets\icon.ico ^
    --add-data "assets;assets" ^
    --add-data "web;web" ^
    --clean --noconfirm ^
    chat_overlay.py

if not exist dist\twitch_overlay.exe (
    echo [ERR] Сборка не удалась. Смотрите сообщения выше.
    pause
    exit /b 1
)

echo.
echo [4/5] Сброс кэша иконок Windows...
REM Закрываем Explorer, чистим IconCache, перезапускаем Explorer
taskkill /IM explorer.exe /F >nul 2>&1
del /A /Q "%LocalAppData%\IconCache.db" >nul 2>&1
del /A /F /Q "%LocalAppData%\Microsoft\Windows\Explorer\iconcache*" >nul 2>&1
del /A /F /Q "%LocalAppData%\Microsoft\Windows\Explorer\thumbcache*" >nul 2>&1
start "" explorer.exe

echo.
echo [5/5] Готово!
echo ===========================================================
echo  Готовый .exe лежит здесь:
echo    %CD%\dist\twitch_overlay.exe
echo.
echo  Если иконка всё равно не подтянулась — перезагрузите ПК
echo  один раз: Windows полностью пересоберёт кэш иконок.
echo ===========================================================
pause
