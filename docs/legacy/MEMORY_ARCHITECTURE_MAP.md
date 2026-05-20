# Sakura Legacy Memory Architecture Map

This document outlines the four parallel storage layers, schemas, and persistence models of the legacy Sakura memory system.

## 1. The Four Memory Layers

```
+-------------------------------------------------------------------------+
|                         SAKURA MEMORY PIPELINE                          |
+-------------------------------------------------------------------------+
|                                                                         |
| 1. FAISS Episodic Store      2. WorldGraph (JSON)   3. Summary Memory   |
| (Semantic Embeddings)       (Entities & Actions)    (Compressed history)|
|                                                                         |
| 4. Ephemeral Logs (Local raw text files, context scraping)               |
+-------------------------------------------------------------------------+
```

### Layer 1: Episodic Vector Store (FAISS)
*   **Format:** `data/vector_store.bin` (Pickled FAISS index + numpy indices).
*   **Access:** Sync read at start, debounced async background saves.
*   **Mechanism:** Queries are embedded using a local SentenceTransformer model (running under PyTorch). Memory entries are parsed after each turn by the `MemoryJudger` LLM, scoring utility from 1–10. Scores $\ge 7$ are indexed.

### Layer 2: World Graph Nodes & Actions (JSON + SQLite)
*   **Format:**
    *   `data/world_graph.json`: Stores user profiles, preferences, custom entities, and their familiarity scores/half-life decay parameters.
    *   `data/actions.db`: An SQLite database containing the history of system actions/runs.
*   **Access:** Thread-locked via `RLock` for JSON reads/writes.
*   **Mechanism:** Updates are made asynchronously after each request turn via the `ReflectionEngine` (running an independent LLM prompt).

### Layer 3: Summary Memory
*   **Format:** In-memory configuration string injected into the model prompt.
*   **Access:** Read dynamically on context manager query.
*   **Mechanism:** Compresses past conversation turns once history exceeds the token ceiling, replacing the raw history logs with a single-paragraph summary of the dialog.

### Layer 4: Ephemeral Scrapes
*   **Format:** Temporary text files (`data/ephemeral_scrapes/`) containing screenshots, website text, or clipboard dumps.
*   **Access:** Single-run duration lifetimes.
*   **Mechanism:** Cleaned up after trace completion.

## 2. Ingestion & Retrieval Matrix

| Memory Layer | Trigger Ingestion | Trigger Retrieval | Index Size on Disk | RAM Footprint |
| :--- | :--- | :--- | :--- | :--- |
| **FAISS Vector** | Post-turn LLM judge | Context signals / recall query | ~2MB - 10MB | ~350MB (PyTorch/sentence-trans) |
| **WorldGraph** | Background reflection LLM | Context Manager `IdentityBlock` | ~500KB | <10MB |
| **Summary Memory**| Token limit overflow | Every conversation turn | In-memory | <1MB |
| **Ephemeral Scrapes**| Direct vision/copy tool | Active tool execution | Variable (Temp) | Variable |
