# -*- mode: python ; coding: utf-8 -*-
# Sakura V10 Backend - PyInstaller Spec
# Build command: pyinstaller backend.spec

import os
import sys

block_cipher = None

# Get the backend directory
backend_dir = os.path.dirname(os.path.abspath(SPEC))
# V17: Get venv site-packages (PA folder is sibling to backend)
venv_site_packages = os.path.join(os.path.dirname(backend_dir), 'PA', 'Lib', 'site-packages')

a = Analysis(
    ['server.py'],
    pathex=[backend_dir],
    binaries=[],
    datas=[
        # Data files only - NOT source code (that's handled by hiddenimports)
        ('data', 'data'),  # Bundle default data (bookmarks, world_graph, etc.)
        # Note: 'Notes' folder is created at runtime in AppData
    ] + ([('Notes', 'Notes')] if os.path.exists(os.path.join(backend_dir, 'Notes')) else []),
    hiddenimports=[
        # ===== V17 Core Refactor - Subdirectory Imports =====
        # PyInstaller static analysis doesn't discover these automatically
        'sakura_assistant.core',
        'sakura_assistant.core.llm',
        'sakura_assistant.core.tools',
        'sakura_assistant.core.ingest_state',
        # context/
        'sakura_assistant.core.context',
        'sakura_assistant.core.context.manager',
        'sakura_assistant.core.context.governor',
        'sakura_assistant.core.context.state',
        # execution/
        'sakura_assistant.core.execution',
        'sakura_assistant.core.execution.context',
        'sakura_assistant.core.execution.dispatcher',
        'sakura_assistant.core.execution.emitter',
        'sakura_assistant.core.execution.executor',
        'sakura_assistant.core.execution.oneshot_runner',
        'sakura_assistant.core.execution.planner',
        # graph/
        'sakura_assistant.core.graph',
        'sakura_assistant.core.graph.world_graph',
        'sakura_assistant.core.graph.identity',
        'sakura_assistant.core.graph.ephemeral',
        # infrastructure/
        'sakura_assistant.core.infrastructure',
        'sakura_assistant.core.infrastructure.broadcaster',
        'sakura_assistant.core.infrastructure.container',
        'sakura_assistant.core.infrastructure.rate_limiter',
        'sakura_assistant.core.infrastructure.scheduler',
        'sakura_assistant.core.infrastructure.voice',
        # models/
        'sakura_assistant.core.models',
        'sakura_assistant.core.models.responder',
        'sakura_assistant.core.models.wrapper',
        # routing/
        'sakura_assistant.core.routing',
        'sakura_assistant.core.routing.router',
        'sakura_assistant.core.routing.forced_router',
        'sakura_assistant.core.routing.micro_toolsets',
        # cognitive/
        'sakura_assistant.core.cognitive',
        'sakura_assistant.core.cognitive.desire',
        'sakura_assistant.core.cognitive.proactive',
        'sakura_assistant.core.cognitive.state',
        'sakura_assistant.core.memory.reflection',
        # tools_libs/
        'sakura_assistant.core.tools_libs',
        'sakura_assistant.core.tools_libs.audio_tools',
        'sakura_assistant.core.tools_libs.code_interpreter',
        'sakura_assistant.core.tools_libs.common',
        'sakura_assistant.core.tools_libs.google',
        'sakura_assistant.core.tools_libs.memory_tools',
        'sakura_assistant.core.tools_libs.research',
        'sakura_assistant.core.tools_libs.spotify',
        'sakura_assistant.core.tools_libs.system',
        'sakura_assistant.core.tools_libs.web',
        # ===== Third-Party Dependencies =====
        # LangChain
        'langchain',
        'langchain_core',
        'langchain_community',
        'langchain_openai',
        'langchain_groq',
        'langchain_google_genai',
        # FastAPI/Uvicorn
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
        # ChromaDB & Embeddings
        'chromadb',
        'chromadb.config',
        'sentence_transformers',
        # Google APIs
        'google.auth',
        'google.oauth2',
        'googleapiclient',
        # Kokoro TTS chain
        'kokoro',
        'misaki',
        'phonemizer',
        'segments',
        'csvw',
        'language_tags',
        # Other tools
        'spotipy',
        'requests',
        'bs4',
        'sympy',
        'tiktoken',
        'structlog',
        'pygame',
        'soundfile',
        'speech_recognition',
        'faiss',
        'AppOpener',
        'plyer',
        'pycaw',
        'mss',
        'pystray',
        'PIL',
    ],
    hookspath=['hooks'],  # V17: Custom hooks for data file bundling
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
