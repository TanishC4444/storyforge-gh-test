"""Shared Gemini document/query encoder. Reads GEMINI_API_KEY (or GEMINI_API_KEYS)."""
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np

from rag.identity import MODEL_NAME, EMBEDDING_DIMENSIONS, INDEX_VERSION

ENDPOINT = f'https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:batchEmbedContents'
BATCH_SIZE = 100


def api_key() -> str:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / '.env', override=False)
    key = os.getenv('GEMINI_API_KEY', '').strip()
    if key:
        return key
    try:
        backups = json.loads(os.getenv('GEMINI_API_KEYS', '[]'))
    except ValueError:
        backups = []
    for candidate in backups if isinstance(backups, list) else []:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    raise RuntimeError('GEMINI_API_KEY is required for Gemini embeddings.')


def _post(body: dict, key: str, attempts: int = 5) -> dict:
    request = urllib.request.Request(ENDPOINT, data=json.dumps(body).encode(),
                                     headers={'x-goog-api-key': key, 'Content-Type': 'application/json'})
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            # Never surface provider messages; they can echo request details.
            if exc.code not in {429, 500, 503} or attempt == attempts - 1:
                raise RuntimeError(f'Gemini embedding request failed: HTTP {exc.code}') from None
            time.sleep(min(60, 2 ** attempt * 5))
    raise RuntimeError('Gemini embedding request failed.')


def encode_texts(texts: list[str], task_type: str = 'RETRIEVAL_DOCUMENT') -> list[list[float]]:
    """Embed with Gemini; vectors below 3072 dimensions are renormalized as Google requires."""
    if not texts:
        return []
    key = api_key()
    result = []
    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start:start + BATCH_SIZE]
        body = {'requests': [{'model': f'models/{MODEL_NAME}', 'content': {'parts': [{'text': text}]},
                              'taskType': task_type, 'outputDimensionality': EMBEDDING_DIMENSIONS}
                             for text in batch]}
        embeddings = _post(body, key).get('embeddings', [])
        if len(embeddings) != len(batch):
            raise ValueError('Embedding model returned the wrong number of vectors.')
        for item in embeddings:
            vector = np.asarray(item.get('values', []), dtype=np.float32)
            norm = np.linalg.norm(vector)
            if vector.shape != (EMBEDDING_DIMENSIONS,) or not np.isfinite(norm) or norm == 0:
                raise ValueError('Embedding model returned an invalid vector.')
            result.append((vector / norm).tolist())
    return result


def encode_query(query: str) -> list[float]:
    return encode_texts([query], task_type='RETRIEVAL_QUERY')[0]
