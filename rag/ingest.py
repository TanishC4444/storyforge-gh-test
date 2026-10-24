"""Resume Gemini embedding indexing of every record in the corpus."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from rag.db import DatabaseError, existing_record_ids, indexed_contents, upsert_documents
from rag.documents import document_text, location_text
from rag.embeddings import INDEX_VERSION, encode_texts
from rag.settings import Settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", required=True, type=Path)
    args = parser.parse_args()
    settings = Settings.from_environment()
    corpus = json.loads(args.json.read_text(encoding="utf-8-sig"))
    records = corpus.get("records", [])
    if not records or any(not isinstance(r, dict) or not r.get("id") for r in records):
        raise SystemExit("Expected a nonempty records array with an ID on every record.")
    expected = {r["id"] for r in records}
    if len(expected) != len(records):
        raise SystemExit("Duplicate record IDs in the corpus.")
    from rag.db import connection, initialize
    with connection(settings) as conn:
        initialize(conn)
        for record in records:
            retrieval = record.get("retrieval") or {}
            conn.execute("UPDATE rag_documents SET enabled=?, record=? WHERE record_id=?", (int(retrieval.get("enabled", True)), json.dumps(record, ensure_ascii=False), record["id"]))
    existing = indexed_contents(settings)
    pending = [r for r in records if existing.get(r["id"]) != document_text(r)]
    completed = len(records) - len(pending)
    print(f"Gemini encoder: {INDEX_VERSION}", flush=True)
    print(f"{completed}/{len(records)} up to date; {len(pending)} to embed with Gemini.", flush=True)
    for start in range(0, len(pending), 32):
        batch = pending[start:start + 32]
        contents = [document_text(r) for r in batch]
        print(f"Embedding {len(batch)} records with Gemini…", flush=True)
        vectors = encode_texts(contents)
        rows = []
        for record, content, vector in zip(batch, contents, vectors, strict=True):
            retrieval = record.get("retrieval") or {}
            rows.append({
                "corpus_name": corpus.get("title", "Untitled corpus"),
                "record_id": record["id"], "parent_id": record.get("parent_id"),
                "canonical_id": retrieval.get("canonical_id", record["id"]),
                "record_type": record.get("record_type", "unknown"),
                "title": record.get("title", "Untitled"),
                "location": location_text(record.get("location")),
                "enabled": retrieval.get("enabled", True), "content": content,
                "record": json.dumps(record, ensure_ascii=False), "embedding": vector,
            })
        completed += upsert_documents(settings, rows)
        print(f"Indexed {completed}/{len(records)} records", flush=True)
    missing = expected - existing_record_ids(settings)
    if missing:
        raise SystemExit(f"Index incomplete: {len(missing)} missing records. Run again to resume.")
    print(f"Index complete: all {len(records)}/{len(records)} source records embedded with Gemini.", flush=True)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, DatabaseError) as exc:
        raise SystemExit(str(exc)) from exc
