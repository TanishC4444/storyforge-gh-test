"""Shared local document/query encoder. No hosted inference or API key."""
from functools import lru_cache

import numpy as np

from rag.identity import MODEL_NAME, MODEL_REVISION, INDEX_VERSION


@lru_cache(maxsize=1)
def get_model():
    from sentence_transformers import SentenceTransformer

    print(f"Loading {MODEL_NAME} locally (first use downloads model files)…", flush=True)
    return SentenceTransformer(MODEL_NAME, revision=MODEL_REVISION, device="cpu", trust_remote_code=False)


def encode_texts(texts: list[str]) -> list[list[float]]:
    """Pool token windows so long records aren't silently truncated by MiniLM."""
    if not texts:
        return []
    model = get_model()
    tokenizer = model.tokenizer
    window = model.max_seq_length - tokenizer.num_special_tokens_to_add(pair=False)
    chunks, counts = [], []
    for text in texts:
        tokens = tokenizer.encode(text, add_special_tokens=False, truncation=False)
        windows = [tokens[start:start + window] for start in range(0, len(tokens), window)] or [[]]
        counts.append(len(windows))
        chunks.extend(tokenizer.decode(tokens, skip_special_tokens=True) for tokens in windows)
    vectors = model.encode(chunks, batch_size=32, normalize_embeddings=True,
                           convert_to_numpy=True, show_progress_bar=False)
    result, offset = [], 0
    for count in counts:
        vector = np.mean(vectors[offset:offset + count], axis=0)
        norm = np.linalg.norm(vector)
        if not np.isfinite(norm) or norm == 0:
            raise ValueError("Embedding model returned an invalid vector.")
        result.append((vector / norm).tolist())
        offset += count
    return result
