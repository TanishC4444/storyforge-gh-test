"""Verify a real prepare artifact uses Gemini retrieval and feeds the writer."""
import argparse,json,math,sqlite3
from pathlib import Path
from rag.identity import MODEL_NAME,INDEX_VERSION,EMBEDDING_DIMENSIONS
from storyforge.retrieval import application_packet


def verify(snapshot,root):
    state=json.loads(Path(snapshot).read_text());req=state['request'];retrieved=state['retrieval']
    if req['retrieval_mode']!='hybrid':raise ValueError('This verification requires hybrid retrieval, not keyword-only search')
    corpus=json.loads((root/'data/literary-corpus.json').read_text())['records']
    with sqlite3.connect(root/'data/literary_rag.db') as db:
        rows=db.execute('select record_id,embedding_model,embedding from rag_documents').fetchall()
    assert {r[0] for r in rows}=={r['id'] for r in corpus},'Corpus/index record mismatch'
    assert {r[1] for r in rows}=={INDEX_VERSION},'Wrong index encoder'
    for _,_,encoded in rows:
        v=json.loads(encoded)
        assert len(v)==EMBEDDING_DIMENSIONS and all(math.isfinite(x) for x in v),'Invalid vector'
        assert abs(sum(x*x for x in v)-1)<1e-4,'Vector is not normalized'
    assert retrieved['index_version']==INDEX_VERSION and not retrieved['stale_embedding_records'],'Stale retrieval'
    semantic=[{'record_id':s['id'],'query':hit['query'],'channel':hit['channel']} for s in retrieved['sources'] for hit in s['retrieval_hits'] if hit['channel'] in {'semantic','hybrid'}]
    assert semantic,'No semantic search evidence in selected sources'
    scene=req['scene_designs'][0]['id']
    writer=application_packet(req,retrieved,'writer',scene)
    assert writer['references'] and writer['craft'],'Writer did not receive reference/craft material'
    return {'pass':True,'embedding_model':MODEL_NAME,'index_version':INDEX_VERSION,'dimensions':EMBEDDING_DIMENSIONS,
            'indexed_records':len(rows),'stale_records':0,'query_facets':len(retrieved['queries']),
            'semantic_hits':semantic,'writer_source_ids':[s['id'] for s in writer['references']],
            'writer_craft_ids':[s['id'] for s in writer['craft']]}


def main():
    p=argparse.ArgumentParser();p.add_argument('--if-hybrid',action='store_true');p.add_argument('--snapshot',default='out/snapshot.json');p.add_argument('--out',default='out/gemini-rag-verification.json');a=p.parse_args()
    if a.if_hybrid and json.loads(Path(a.snapshot).read_text())['request']['retrieval_mode']!='hybrid':return
    result=verify(a.snapshot,Path(__file__).resolve().parents[1])
    Path(a.out).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
