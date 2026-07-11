@echo off
:: FocusLock v3.0.0 - Build Script
:: Creates a standalone FocusLock.exe using PyInstaller
:: Run this on Windows with Python + PyInstaller installed

echo =======================================
echo  FocusLock v3.0.0 Build Script
echo =======================================
echo.

pip install pyinstaller --quiet

pyinstaller ^
  --onefile ^
  --windowed ^
  --name FocusLock ^
  --icon assets/icon.ico ^
  --paths src ^
  src/focuslock_app.py

echo.
echo Done! Find FocusLock.exe in the dist/ folder.
pause
