# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['src\\focuslock_app.py'],
    pathex=['src'],
    binaries=[],
    datas=[],
    hiddenimports=['PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets', 'PySide6.QtSvg', 'PySide6.QtNetwork', 'PySide6.shiboken6', 'sqlalchemy', 'sqlalchemy.dialects.sqlite', 'sqlalchemy.pool', 'sqlalchemy.orm', 'sqlalchemy.orm.session', 'greenlet', 'psutil', 'psutil._pswindows', 'winreg', 'ctypes.wintypes', 'winsound', 'focuslock', 'focuslock.constants', 'focuslock.config', 'focuslock.core', 'focuslock.core.timer', 'focuslock.core.security', 'focuslock.blocking', 'focuslock.blocking.app_blocker', 'focuslock.blocking.website_blocker', 'focuslock.platform', 'focuslock.platform.startup', 'focuslock.platform.notifications', 'focuslock.platform.subprocess_patch', 'focuslock.ui', 'focuslock.ui.widgets', 'focuslock.ui.dialogs'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy', 'pandas', 'pytest', 'unittest'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='FocusLock',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='FocusLock',
)
