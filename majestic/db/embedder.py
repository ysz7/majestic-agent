"""
fastembed singleton — sentence-transformers/all-MiniLM-L6-v2

384-dim embeddings, CPU-only, ~15ms per query after first load.
First call downloads ~80 MB model to ~/.cache/fastembed/.
"""
from __future__ import annotations

import os
import threading
import warnings

# Suppress HuggingFace Hub download progress bars and auth warnings
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("HF_HUB_VERBOSITY", "error")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
warnings.filterwarnings("ignore", category=UserWarning, module="huggingface_hub")
warnings.filterwarnings("ignore", message=".*HF_HUB_DISABLE_PROGRESS_BARS.*")

_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
_model = None
_lock  = threading.Lock()


def _get() -> object:
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                from fastembed import TextEmbedding
                _model = TextEmbedding(_MODEL_NAME)
    return _model


def embed(text: str) -> list[float]:
    """Embed a single string. Returns a 384-dim float list."""
    import numpy as np
    result = next(iter(_get().embed([text])))
    arr = np.asarray(result, dtype=np.float32)
    return arr.tolist()


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed a list of strings. Returns list of 384-dim float lists."""
    import numpy as np
    results = []
    for vec in _get().embed(texts):
        results.append(np.asarray(vec, dtype=np.float32).tolist())
    return results
