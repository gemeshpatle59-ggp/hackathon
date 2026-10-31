"""
Long-term patient memory.
  add(pid, text, kind="fact")  -> store a memory
  search(pid, query, n=5)      -> list of the most relevant memories (strings)

Uses ChromaDB if it is installed and working; otherwise falls back automatically to a simple
JSON file with keyword matching, so the project still runs (e.g. on Python 3.14 where chromadb may not install).
"""
import json
import os
import re
import uuid
from datetime import datetime

import config

_FALLBACK_FILE = "memory_fallback.json"
_collection = None
_chroma_failed = False


def _get_collection():
    global _collection, _chroma_failed
    if _chroma_failed:
        return None
    if _collection is None:
        try:
            import chromadb
            client = chromadb.PersistentClient(path=config.CHROMA_DIR)
            _collection = client.get_or_create_collection("patient_memory")
        except Exception:
            _chroma_failed = True
            return None
    return _collection


# ---- fallback store ------------------------------------------------------------
def _load() -> list:
    if os.path.exists(_FALLBACK_FILE):
        try:
            with open(_FALLBACK_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def _save(items: list):
    with open(_FALLBACK_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=1)


def _words(text: str) -> set:
    return set(re.findall(r"\w+", text.lower()))


# ---- public API ------------------------------------------------------------------
def add(pid: str, text: str, kind: str = "fact"):
    if not text or not text.strip():
        return
    col = _get_collection()
    if col is not None:
        try:
            col.add(documents=[text], metadatas=[{"patient_id": pid, "kind": kind}], ids=[str(uuid.uuid4())])
            return
        except Exception:
            pass
    items = _load()
    items.append({"pid": pid, "kind": kind, "text": text, "ts": datetime.now().isoformat(timespec="seconds")})
    _save(items)


def search(pid: str, query: str, n: int = 5) -> list:
    col = _get_collection()
    if col is not None:
        try:
            res = col.query(query_texts=[query], n_results=n, where={"patient_id": pid})
            return res["documents"][0] if res.get("documents") else []
        except Exception:
            pass
    mine = [m for m in _load() if m["pid"] == pid]
    q = _words(query)
    scored = sorted(mine, key=lambda m: len(q & _words(m["text"])), reverse=True)
    hits = [m["text"] for m in scored if q & _words(m["text"])][:n]
    return hits or [m["text"] for m in mine[-3:]]          # nothing matched: most recent memories
