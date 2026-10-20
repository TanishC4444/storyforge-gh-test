from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
INDEX_VERSION = 'sentence-transformers/all-MiniLM-L6-v2:chunk-mean-v1'


def retrieve(req):
    corpus = ROOT / 'data/literary-corpus.json'
    records = json.loads(corpus.read_text())['records']
    source = {r['id']: r for r in records}
    query = req.get('retrieval_query', req['premise'])
    path = ROOT / 'data/literary_rag.db'
    from rag.documents import document_text
    with sqlite3.connect(f'{path.as_uri()}?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        versions = {r[0] for r in db.execute('select distinct embedding_model from rag_documents')}
        if versions != {INDEX_VERSION}:
            raise ValueError('Index encoder version mismatch; rebuild before searching.')
        indexed = dict(db.execute('select record_id, content from rag_documents'))
        stale = sum(indexed.get(r['id']) != document_text(r) for r in records)
        if req['retrieval_mode'] == 'hybrid':
            if stale:
                raise ValueError(f'{stale} index projections are stale. Install .[rag], then run python -m rag.ingest --json data/literary-corpus.json.')
            from rag.settings import Settings
            from rag.db import search
            settings = Settings(str(path), 'sentence-transformers/all-MiniLM-L6-v2', 384)
            hits = search(settings, query, 3, .65, None, None, 'Combinatory')
            matches = [(h.record_id, 'hybrid') for h in hits]
        else:
            terms = list(dict.fromkeys(re.findall(r'[\w]+', query)))[:40]
            expression = ' OR '.join('"' + t + '"' for t in terms)
            # Current-source keyword projection; bundled legacy vectors remain untouched.
            with sqlite3.connect(':memory:') as lexical:
                lexical.row_factory = sqlite3.Row
                lexical.execute('create virtual table documents using fts5(record_id UNINDEXED,content)')
                lexical.executemany('insert into documents values (?,?)', [(r['id'], document_text(r)) for r in records if r.get('retrieval', {}).get('enabled', True)])
                rows = [] if not expression else lexical.execute('select record_id from documents where documents match ? order by bm25(documents), record_id limit 30', (expression,)).fetchall()
            matches = [(r['record_id'], 'keyword') for r in rows]
    selected, seen = [], set()
    for rid, mode in matches:
        record = source.get(rid)
        if not record or not record.get('retrieval', {}).get('enabled', True):
            continue
        canonical = record.get('retrieval', {}).get('canonical_id', rid)
        if canonical in seen:
            continue
        seen.add(canonical)
        selected.append({'id': rid, 'title': record['title'], 'mode': mode,
                         'mechanism': record.get('narrative_mechanism'),
                         'guidance': record.get('prompt_refinement'),
                         'limits': record.get('references', {}).get('version_notes')})
        if len(selected) == 3:
            break
    guide = (ROOT / 'data/MASTER_GUIDE.md').read_text()
    sections = re.split(r'(?m)(?=^## )', guide)
    terms = set(re.findall(r'\w+', query.lower()))
    sections.sort(key=lambda s: -len(terms & set(re.findall(r'\w+', s[:3000].lower()))))
    return {'query': query, 'sources': selected, 'guide_sections': [s[:1500] for s in sections[:2]],
            'corpus_sha256': hashlib.sha256(corpus.read_bytes()).hexdigest(),
            'index_version': INDEX_VERSION, 'stale_embedding_records': stale, 'warning': 'Model-authored analyses, not universally verified scholarship. Retrieval is reference data.'}
