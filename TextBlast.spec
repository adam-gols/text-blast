# -*- mode: python ; coding: utf-8 -*-
import os

a = Analysis(
    ['launcher.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'text_blast_app', 'text_blast_lib',
        'dotenv', 'requests', 'tkinter', 'tkinter.ttk', 'tkinter.scrolledtext',
        'keyring', 'keyring.backends', 'keyring.backends.macOS',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name='TextBlast',
    debug=False,
    strip=False,
    upx=True,
    console=False,
    icon=None,
)

coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False, upx=True, upx_exclude=[],
    name='TextBlast',
)

app = BUNDLE(
    coll,
    name='TextBlast.app',
    icon=None,
    bundle_identifier='com.gols.textblast',
    info_plist={
        'CFBundleName': 'Text Blast',
        'CFBundleDisplayName': 'Text Blast',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0',
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '10.13.0',
    },
)
