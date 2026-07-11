@echo off
:: ==========================================
::  FocusLock v3.0.0 - Build Script
:: ==========================================
::  Builds a professional standalone distribution.
::  No Python required on the target machine.
::
::  Usage:
::    build.bat              Full clean + build + distribution
::    build.bat --fast       Build only (skip clean)
::    build.bat --clean      Clean only
:: ==========================================
echo.

if "%1"=="--clean" (
    python build.py --clean
) else if "%1"=="--fast" (
    python build.py --fast --dist
) else (
    python build.py --dist
)

echo.
