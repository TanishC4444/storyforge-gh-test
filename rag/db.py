from __future__ import annotations
import json, sqlite3
from dataclasses import dataclass
from typing import Any, Iterable
from contextlib import contextmanager
import numpy as np
from rag.settings import Settings
from rag.embeddings import INDEX_VERSION, encode_texts
class DatabaseError(RuntimeError): pass
@dataclass(frozen=True)
class CorpusStats: documents:int; with_location:int; corpus_name:str|None
@dataclass(frozen=True)
class SearchResult: record_id:str; title:str; location:str|None; record_type:str; canonical_id:str; score:float; semantic_rank:int|None; keyword_rank:int|None; record:dict[str,Any]
@contextmanager
def connection(settings):
    try:
        conn=sqlite3.connect(settings.database_path)
    except sqlite3.Error as exc: raise DatabaseError(f"Could not open SQLite: {exc}") from exc
    try:
        conn.row_factory=sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        with conn:
            yield conn
    finally:
        conn.close()
def initialize(conn):
    conn.executescript("""CREATE TABLE IF NOT EXISTS rag_documents(record_id TEXT PRIMARY KEY,corpus_name TEXT NOT NULL,parent_id TEXT,canonical_id TEXT NOT NULL,record_type TEXT NOT NULL,title TEXT NOT NULL,location TEXT,enabled INTEGER NOT NULL,content TEXT NOT NULL,record TEXT NOT NULL,embedding TEXT NOT NULL,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP); CREATE VIRTUAL TABLE IF NOT EXISTS rag_documents_fts USING fts5(record_id UNINDEXED,content);""")
    columns = {row[1] for row in conn.execute("PRAGMA table_info(rag_documents)")}
    if "embedding_model" not in columns:
        conn.execute("ALTER TABLE rag_documents ADD COLUMN embedding_model TEXT NOT NULL DEFAULT 'legacy-gemini'")
def get_corpus_stats(settings):
    with connection(settings) as conn:
        initialize(conn); row=conn.execute("SELECT count(*),count(location),max(corpus_name) FROM rag_documents").fetchone()
    return CorpusStats(*row)
def upsert_documents(settings,documents:Iterable[dict[str,Any]]):
    rows=list(documents)
    with connection(settings) as conn:
        initialize(conn)
        for r in rows:
            conn.execute("INSERT INTO rag_documents(record_id,corpus_name,parent_id,canonical_id,record_type,title,location,enabled,content,record,embedding,embedding_model) VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(record_id) DO UPDATE SET corpus_name=excluded.corpus_name,parent_id=excluded.parent_id,canonical_id=excluded.canonical_id,record_type=excluded.record_type,title=excluded.title,location=excluded.location,enabled=excluded.enabled,content=excluded.content,record=excluded.record,embedding=excluded.embedding,embedding_model=excluded.embedding_model,updated_at=CURRENT_TIMESTAMP",(r['record_id'],r['corpus_name'],r['parent_id'],r['canonical_id'],r['record_type'],r['title'],r['location'],int(r['enabled']),r['content'],r['record'],json.dumps(r['embedding']),INDEX_VERSION))
            conn.execute("DELETE FROM rag_documents_fts WHERE record_id=?",(r['record_id'],)); conn.execute("INSERT INTO rag_documents_fts(record_id,content) VALUES(?,?)",(r['record_id'],r['content']))
    return len(rows)
def existing_record_ids(settings):
    with connection(settings) as conn:
        initialize(conn)
        return {row[0] for row in conn.execute("SELECT record_id FROM rag_documents WHERE embedding_model=?", (INDEX_VERSION,))}
def indexed_contents(settings):
    with connection(settings) as conn:
        initialize(conn)
        return {row[0]: row[1] for row in conn.execute("SELECT record_id,content FROM rag_documents WHERE embedding_model=?", (INDEX_VERSION,))}
def search(settings,query,limit,semantic_weight,record_types,location,adaptation_mode="Balanced"):
    try:
        q=np.array(encode_texts([query])[0],dtype=np.float32)
    except Exception as exc: raise DatabaseError(f"Could not create query embedding: {exc}") from exc
    with connection(settings) as conn:
        initialize(conn); sql="SELECT * FROM rag_documents WHERE enabled=1 AND embedding_model=?"; params=[INDEX_VERSION]
        if record_types: sql += " AND record_type IN ("+','.join('?'*len(record_types))+")"; params+=record_types
        if location: sql += " AND location LIKE ?"; params.append('%'+location+'%')
        rows=conn.execute(sql,params).fetchall()
        if not rows: return []
        keywords=' OR '.join('"'+w.replace('"','')+'"' for w in query.split() if w.isalnum()) or '""'
        allowed={r['record_id'] for r in rows}
        matches=conn.execute("SELECT record_id FROM rag_documents_fts WHERE rag_documents_fts MATCH ? ORDER BY bm25(rag_documents_fts)",(keywords,)).fetchall()
        kw={rid:i+1 for i,rid in enumerate([r['record_id'] for r in matches if r['record_id'] in allowed][:60])}
    vectors=np.array([json.loads(r['embedding']) for r in rows],dtype=np.float32); scores=vectors@q/(np.linalg.norm(vectors,axis=1)*np.linalg.norm(q)); semantic={rows[i]['record_id']:rank+1 for rank,i in enumerate(np.argsort(scores)[::-1][:60])}; sw=min(max(semantic_weight,0),1); ids=set(semantic)|set(kw); ranked=[]
    for rid in ids:
        row=next(r for r in rows if r['record_id']==rid); sr=semantic.get(rid); kr=kw.get(rid); score=sw/(60+(sr or 1000))+(1-sw)/(60+(kr or 1000)); ranked.append(SearchResult(rid,row['title'],row['location'],row['record_type'],row['canonical_id'],score,sr,kr,json.loads(row['record'])))
    ordered=sorted(ranked,key=lambda r:r.score,reverse=True)
    if adaptation_mode == "Focused adaptation":
        # Keep the closest result first and prefer its canonical work for supporting context.
        if ordered:
            primary=ordered[0].canonical_id
            ordered.sort(key=lambda r:(r.canonical_id != primary,-r.score))
        return ordered[:limit]
    if adaptation_mode == "Combinatory":
        # Deterministically diversify by source work and collection before filling remaining slots.
        selected=[]; seen_canonical=set(); seen_collections=set()
        for result in ordered:
            collection=(result.record.get("collection") or "").casefold()
            if result.canonical_id in seen_canonical or collection in seen_collections: continue
            selected.append(result); seen_canonical.add(result.canonical_id); seen_collections.add(collection)
            if len(selected)==limit: return selected
        for result in ordered:
            if result not in selected: selected.append(result)
            if len(selected)==limit: break
        return selected
    return ordered[:limit]
def update_location(settings,record_id,location):
    with connection(settings) as conn:
        initialize(conn); row=conn.execute("SELECT record FROM rag_documents WHERE record_id=?",(record_id,)).fetchone()
        if not row: raise DatabaseError(f"No record exists with ID {record_id!r}.")
        record=json.loads(row['record']); record['location']=location; conn.execute("UPDATE rag_documents SET location=?,record=?,updated_at=CURRENT_TIMESTAMP WHERE record_id=?",(location,json.dumps(record),record_id))
