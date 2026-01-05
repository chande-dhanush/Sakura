# -*- mode: python ; coding: utf-8 -*-
# Sakura V10 Backend - PyInstaller Spec
# Build command: pyinstaller backend.spec

import os
import sys

block_cipher = None

# Get the backend directory
backend_dir = os.path.dirname(os.path.abspath(SPEC))

a = Analysis(
    ['server.py'],
    pathex=[backend_dir],
    binaries=[],
    datas=[
        # Include data directories
        ('sakura_assistant', 'sakura_assistant'),
        ('data', 'data'),  # Bundle default data (bookmarks, etc.)
        # Note: 'Notes' and 'data' folders are created at runtime in AppData
    ] + ([('Notes', 'Notes')] if os.path.exists(os.path.join(backend_dir, 'Notes')) else []),
    hiddenimports=[
        # LangChain imports
        'langchain',
        'langchain_core',
        'langchain_community',
        'langchain_openai',
        'langchain_groq',
        'langchain_google_genai',
        # FastAPI
        'uvicorn',
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        # ChromaDB
        'chromadb',
        'chromadb.config',
        # Sentence Transformers (for embeddings)
        'sentence_transformers',
        # Other tools
        'spotipy',
        'google.auth',
        'google.oauth2',
        'googleapiclient',
        'requests',
        'bs4',  # beautifulsoup4 module name
        'sympy',
        'tiktoken',
        'structlog',
        # Audio (optional, may fail on some systems)
        'pygame',
        'soundfile',
        'kokoro',
        'speech_recognition',
        'faiss',
        'AppOpener',
        'plyer',
        'pycaw',
        'mss',
        'pystray',
        'PIL',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',  # Not needed
        'matplotlib',  # Not needed
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='sakura-backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Keep console for debugging; set False for silent
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico' if os.path.exists('assets/icon.ico') else None,
)
