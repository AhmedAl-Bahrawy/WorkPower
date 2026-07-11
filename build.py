"""
FocusLock v3.0.0 - Build Orchestrator
Professional build script that produces a standalone Windows executable.

Usage:
    python build.py              # Clean + Build
    python build.py --fast       # Build only (skip clean)
    python build.py --clean      # Clean only
    python build.py --dist       # Build + create distribution folder
"""

import argparse
import os
import shutil
import subprocess
import sys
import time

# ── Configuration ────────────────────────────────────────────────────────────
APP_NAME = "FocusLock"
VERSION = "3.0.0"
ENTRY_POINT = "src/focuslock_app.py"
SPEC_FILE = "FocusLock.spec"
SRC_DIR = "src"

DIST_DIR = "dist"
BUILD_DIR = "build"
WORK_DIR = "build/build_tmp"
ICON_PATH = "assets/icon.ico"  # Optional

# ── Helpers ──────────────────────────────────────────────────────────────────
def banner(text):
    width = max(len(text) + 4, 50)
    print("\n" + "=" * width)
    print(f"  {text}")
    print("=" * width + "\n")


def run(cmd, **kwargs):
    """Run a command and exit on failure."""
    print(f"  > {' '.join(cmd)}")
    result = subprocess.run(cmd, **kwargs)
    if result.returncode != 0:
        print(f"\n  [FAIL] Command failed with exit code {result.returncode}")
        sys.exit(result.returncode)
    return result


def file_size_mb(path):
    return os.path.getsize(path) / (1024 * 1024)


# ── Steps ────────────────────────────────────────────────────────────────────
def check_prerequisites():
    banner("Checking prerequisites")

    # Python version
    v = sys.version_info
    print(f"  Python {v.major}.{v.minor}.{v.micro}")
    if v < (3, 10):
        print("  [FAIL] Python 3.10+ is required")
        sys.exit(1)

    # Required packages
    required = {
        "PySide6": "PySide6",
        "sqlalchemy": "SQLAlchemy",
        "psutil": "psutil",
        "PyInstaller": "pyinstaller",
    }
    missing = []
    for module, package in required.items():
        try:
            mod = __import__(module)
            ver = getattr(mod, "__version__", "?")
            print(f"  {package:20s} {ver}")
        except ImportError:
            missing.append(package)
            print(f"  {package:20s} MISSING")

    if missing:
        print(f"\n  Installing missing packages: {', '.join(missing)}")
        run([sys.executable, "-m", "pip", "install", "--quiet"] + missing)

    print("\n  All prerequisites OK.")


def clean():
    banner("Cleaning previous builds")
    for d in [BUILD_DIR, DIST_DIR, WORK_DIR]:
        if os.path.isdir(d):
            shutil.rmtree(d)
            print(f"  Removed {d}/")

    # Remove __pycache__ recursively
    for root, dirs, files in os.walk(SRC_DIR):
        for d in dirs:
            if d == "__pycache__":
                shutil.rmtree(os.path.join(root, d))
    print("  Cleaned.\n")


def build():
    banner(f"Building {APP_NAME} v{VERSION}")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--windowed",
        "--name", APP_NAME,
        "--paths", SRC_DIR,
        # Hidden imports that PyInstaller may miss
        "--hidden-import", "PySide6.QtCore",
        "--hidden-import", "PySide6.QtGui",
        "--hidden-import", "PySide6.QtWidgets",
        "--hidden-import", "PySide6.QtSvg",
        "--hidden-import", "PySide6.QtNetwork",
        "--hidden-import", "PySide6.shiboken6",
        "--hidden-import", "sqlalchemy",
        "--hidden-import", "sqlalchemy.dialects.sqlite",
        "--hidden-import", "sqlalchemy.pool",
        "--hidden-import", "sqlalchemy.orm",
        "--hidden-import", "sqlalchemy.orm.session",
        "--hidden-import", "greenlet",
        "--hidden-import", "psutil",
        "--hidden-import", "psutil._pswindows",
        "--hidden-import", "winreg",
        "--hidden-import", "ctypes.wintypes",
        "--hidden-import", "winsound",
        "--hidden-import", "focuslock",
        "--hidden-import", "focuslock.constants",
        "--hidden-import", "focuslock.config",
        "--hidden-import", "focuslock.core",
        "--hidden-import", "focuslock.core.timer",
        "--hidden-import", "focuslock.core.security",
        "--hidden-import", "focuslock.blocking",
        "--hidden-import", "focuslock.blocking.app_blocker",
        "--hidden-import", "focuslock.blocking.website_blocker",
        "--hidden-import", "focuslock.platform",
        "--hidden-import", "focuslock.platform.startup",
        "--hidden-import", "focuslock.platform.notifications",
        "--hidden-import", "focuslock.platform.subprocess_patch",
        "--hidden-import", "focuslock.ui",
        "--hidden-import", "focuslock.ui.widgets",
        "--hidden-import", "focuslock.ui.dialogs",
        # Exclude heavy unused libs
        "--exclude-module", "tkinter",
        "--exclude-module", "matplotlib",
        "--exclude-module", "numpy",
        "--exclude-module", "pandas",
        "--exclude-module", "pytest",
        "--exclude-module", "unittest",
        # Build paths
        "--distpath", DIST_DIR,
        "--workpath", WORK_DIR,
        "--specpath", ".",
        ENTRY_POINT,
    ]

    # Add icon if it exists
    if os.path.isfile(ICON_PATH):
        cmd.insert(-1, "--icon")
        cmd.insert(-1, ICON_PATH)

    start = time.time()
    run(cmd)
    elapsed = time.time() - start

    exe_dir = os.path.join(DIST_DIR, APP_NAME)
    print(f"\n  Build completed in {elapsed:.1f}s")
    print(f"  Output: {exe_dir}/")

    # Verify the exe exists
    exe_path = os.path.join(exe_dir, f"{APP_NAME}.exe")
    if os.path.isfile(exe_path):
        size = file_size_mb(exe_path)
        print(f"  {APP_NAME}.exe  ({size:.1f} MB)")
    else:
        print(f"  [WARN] {APP_NAME}.exe not found at expected path")
        # List what IS there
        if os.path.isdir(exe_dir):
            for f in os.listdir(exe_dir):
                fp = os.path.join(exe_dir, f)
                if os.path.isfile(fp):
                    print(f"    {f}  ({file_size_mb(fp):.1f} MB)")

    return exe_dir


def create_distribution(exe_dir):
    banner("Creating distribution package")

    release_dir = os.path.join(DIST_DIR, f"{APP_NAME}-{VERSION}")
    if os.path.isdir(release_dir):
        shutil.rmtree(release_dir)

    # Copy the entire onedir output
    shutil.copytree(exe_dir, release_dir)

    # Create an install helper script
    install_bat = os.path.join(release_dir, "Install.bat")
    with open(install_bat, "w") as f:
        f.write(f"""@echo off
echo ==========================================
echo  {APP_NAME} v{VERSION} - Installer
echo ==========================================
echo.
echo This will create a shortcut on your Desktop.
echo.

:: Create desktop shortcut
set SCRIPT_DIR=%~dp0
set SHORTCUT_PATH=%USERPROFILE%\\Desktop\\{APP_NAME}.lnk
set TARGET=%SCRIPT_DIR%{APP_NAME}.exe

powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%SHORTCUT_PATH%'); $s.TargetPath = '%TARGET%'; $s.WorkingDirectory = '%SCRIPT_DIR%'; $s.Save()"

echo.
echo Desktop shortcut created!
echo You can now run {APP_NAME} from your Desktop.
echo.
echo To uninstall: just delete this folder and the Desktop shortcut.
echo.
pause
""")

    # Create uninstall helper
    uninstall_bat = os.path.join(release_dir, "Uninstall.bat")
    with open(uninstall_bat, "w") as f:
        f.write(f"""@echo off
echo Uninstalling {APP_NAME}...

:: Remove desktop shortcut
del "%USERPROFILE%\\Desktop\\{APP_NAME}.lnk" 2>nul

echo Desktop shortcut removed.
echo You can now delete this folder: %~dp0
echo.
pause
""")

    # Create a README
    readme = os.path.join(release_dir, "README.txt")
    with open(readme, "w") as f:
        f.write(f"""{APP_NAME} v{VERSION}
{'=' * 40}

Quick Start:
  1. Run {APP_NAME}.exe
  2. Or double-click "Install.bat" for a Desktop shortcut

Features:
  - Pomodoro timer with work/break/long-break cycles
  - App and website blocking during focus sessions
  - Customizable durations and presets
  - Sound and notification alerts
  - Dark and Light themes
  - Session statistics and streak tracking
  - Password protection

System Requirements:
  - Windows 10 or later
  - No Python installation required

Uninstall:
  1. Run "Uninstall.bat" to remove the Desktop shortcut
  2. Delete this entire folder

Version: {VERSION}
""")

    size = sum(
        file_size_mb(os.path.join(dp, f))
        for dp, _, files in os.walk(release_dir)
        for f in files
    )
    print(f"  Distribution: {release_dir}/")
    print(f"  Total size:   {size:.1f} MB")
    print(f"  Contents:")
    for f in sorted(os.listdir(release_dir)):
        fp = os.path.join(release_dir, f)
        if os.path.isfile(fp):
            print(f"    {f}  ({file_size_mb(fp):.1f} MB)")
        else:
            print(f"    {f}/")

    return release_dir


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description=f"Build {APP_NAME} v{VERSION}")
    parser.add_argument("--fast", action="store_true", help="Skip clean step")
    parser.add_argument("--clean", action="store_true", help="Clean only")
    parser.add_argument("--dist", action="store_true", help="Build + create distribution folder")
    args = parser.parse_args()

    banner(f"{APP_NAME} v{VERSION} Build System")

    check_prerequisites()

    if args.clean:
        clean()
        print("Clean complete.\n")
        return

    if not args.fast:
        clean()

    exe_dir = build()

    if args.dist:
        create_distribution(exe_dir)

    banner("Build complete!")
    print(f"  To run:  {os.path.join(DIST_DIR, APP_NAME, APP_NAME + '.exe')}")
    if args.dist:
        print(f"  To ship: {os.path.join(DIST_DIR, f'{APP_NAME}-{VERSION}')}/")
    print()


if __name__ == "__main__":
    main()
