# DEPENDENCY_AUDIT.md

This audit tracks the usage of packages in `requirements.txt` as of Phase 3 (Sakura V19.0). 
We only remove packages in the **Clearly Unused** category.

## Audit Table

| Package | Imported by | Runtime Critical? | Safe to Remove? | Action Taken |
| :--- | :--- | :--- | :--- | :--- |
| `fastapi` | `server.py` | Highly | No | Retained |
| `uvicorn` | `server.py` | Highly | No | Retained |
| `pydantic` | `core/models/request.py` (Indirect) | Yes | No | Retained |
| `python-dotenv` | `server.py` | Yes | No | Retained |
| `langchain-*` | `core/llm.py`, `core/routing/router.py` | Highly | No | Retained |
| `chromadb` | `memory/chroma_store/store.py` | Yes (RAG) | No (Decision 1) | Retained |
| `faiss-cpu` | `memory/faiss_store.py` | Highly (Episodic) | No (Decision 1) | Retained |
| `sentence-transformers` | `memory/vector_store.py` | Yes | No | Retained |
| `google-api-*` | `core/tools_libs/google.py` | Yes | No | Retained |
| `requests` | Throughout | Yes | No | Retained |
| `beautifulsoup4` | `core/tools_libs/web.py` | Yes | No | Retained |
| `tavily-python` | `core/tools_libs/web.py` | Yes | No | Retained |
| `SpeechRecognition` | `core/infrastructure/voice.py` | Yes (Voice) | No | Retained |
| `pyaudio` | `utils/shared_mic.py`, `utils/wake_word.py` | Yes | No | Retained |
| `kokoro` | `utils/tts.py` | Yes (Voice) | No | Retained |
| `soundfile` | `utils/tts.py` | Yes | No | Retained |
| `pygame` | `utils/tts.py` | Yes | No | Retained |
| `spotipy` | `core/tools_libs/spotify.py` | Yes | No | Retained |
| `psutil` | `utils/metrics.py`, `core/tools_libs/system.py` | Yes | No | Retained |
| `pycaw` | `core/tools_libs/system.py` | Yes (Windows) | No | Retained |
| `AppOpener` | `core/tools_libs/system.py` | Yes | No | Retained |
| `pyperclip` | `core/tools_libs/system.py` | Yes | No | Retained |
| `plyer` | (Not found) | No | **YES** | **REMOVED** |
| `mss` | `core/tools_libs/system.py` | Yes | No | Retained |
| `pytesseract` | `core/tools_libs/system.py` | Yes | No | Retained |
| `Pillow` | `core/tools_libs/system.py` | Yes | No | Retained |
| `numpy` | `core/graph/world_graph.py` | Yes | No | Retained |
| `scipy` | `utils/wake_word.py` | Yes | No | Retained |
| `sympy` | `core/tools.py` | Yes | No | Retained |
| `tiktoken` | `utils/token_counter.py` | Yes | No | Retained |
| `aiofiles` | (Not found) | No | **YES** | **REMOVED** |
| `prometheus_client` | (Not found) | No | **YES** | **REMOVED** |
| `bandit` | (Not found in code) | No | **YES** | **REMOVED** |
| `pytest-cov` | (Not found in code) | No | **YES** | **REMOVED** |
| `pydub` | `core/tools_libs/audio_tools.py` | Yes | No | Retained |
| `nest-asyncio` | `core/tools_libs/system.py` | Yes | No | Retained |
| `structlog` | `utils/logging.py` | Yes | No | Retained |
| `pytz` | `core/tools_libs/system.py` | Yes | No | Retained |

## Summary
The audit has identified 5 clearly unused packages. These are either legacy artifacts from previous versions or were never fully implemented in the current Sakura V19 runtime path. All other packages are verified as active.
