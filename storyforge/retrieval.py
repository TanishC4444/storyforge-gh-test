"""Inspectable literary retrieval: ranked mechanisms, source limits, and role-specific craft."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import sqlite3

ROOT=Path(__file__).resolve().parents[1]
from rag.identity import INDEX_VERSION
STOP={'the','a','an','and','or','to','of','in','on','for','is','are','be','with','that','this','their','her','his','it','as','by','from','who','what','how','will','can','must','not','but'}
ROLE_CHAPTERS={'refiner':[2,3,5,8], 'architect':[3,5,8,9,10], 'scene_designer':[3,9,10,26], 'writer':[9,18,19,20], 'humanizer':[18,19,20,27], 'story_quality':[3,5,8,9,26], 'rhetoric_quality':[18,19,20,27]}
ROLE_TERMS={'refiner':'premise competing obligations choices consequences', 'architect':'causality subplot dependency scene progression', 'scene_designer':'scene change repetition knowledge consequence', 'writer':'viewpoint action dialogue specificity', 'humanizer':'redundancy subtext specificity rhythm imagery', 'story_quality':'agency motives causality knowledge subplot', 'rhetoric_quality':'explanation repetition metaphor dialogue subtext'}


def terms(text):
    return list(dict.fromkeys(t for t in re.findall(r'\w+',text.lower().replace('_',' ')) if t not in STOP and len(t)>2))


def mechanism_terms(text):
    aliases={'duties':'obligation','duty':'obligation','obligations':'obligation','debts':'debt','incompatible':'conflict','conflicting':'conflict','conflicts':'conflict','choices':'choice','costs':'cost','dependencies':'dependence'}
    return {aliases.get(t,t) for t in terms(text)}


def queries(req):
    keywords=req.get('keywords',[])
    grouped={kind:[k['term'] for k in keywords if k['kind']==kind] for kind in ['theme','tension','conflict','technique','relationship']}
    result=[{'id':'themes_conflicts','text':' '.join(grouped['theme']+grouped['tension']+grouped['conflict'])},
            {'id':'character_relationships','text':' '.join(grouped['relationship']+[c.get('value','')+' '+c.get('habitual_strategy','') for c in req['characters']])},
            {'id':'craft','text':' '.join(grouped['technique']+req.get('technique_keywords',[]))}]
    if req.get('retrieval_query'):result.append({'id':'user_query','text':req['retrieval_query']})
    result=[q for q in result if terms(q['text'])]
    for q in result:
        matching=[k.get('priority',2) for k in keywords if k['term'] in q['text']]
        q['weight']=(sum(matching)/len(matching)/2) if matching else 1.0
    return result or [{'id':'premise','text':req['premise']}]


def guide_chunks(text):
    chapters=list(re.finditer(r'(?m)^## (.+)$',text))
    result=[]
    for i,chapter in enumerate(chapters):
        end=chapters[i+1].start() if i+1<len(chapters) else len(text)
        body=text[chapter.end():end]
        headings=list(re.finditer(r'(?m)^### (.+)$',body))
        number=re.match(r'(\d+)\.',chapter[1]);number=int(number[1]) if number else 0
        for j,heading in enumerate(headings):
            stop=headings[j+1].start() if j+1<len(headings) else len(body)
            content=body[heading.start():stop].strip()
            prefix=re.match(r'([A-Z]+-\d+)',heading[1])
            chunk_id=prefix[1] if prefix else hashlib.sha256(content.encode()).hexdigest()[:10]
            result.append({'id':chunk_id,'chapter':number,'heading':heading[1],'content':content})
    return result


def retrieve(req):
    corpus=ROOT/'data/literary-corpus.json'
    records=json.loads(corpus.read_text())['records']
    source={r['id']:r for r in records}
    enabled={r['id']:r for r in records if r.get('retrieval',{}).get('enabled',True)}
    from rag.documents import document_text
    path=ROOT/'data/literary_rag.db'
    with sqlite3.connect(f'{path.as_uri()}?mode=ro',uri=True) as db:
        versions={r[0] for r in db.execute('select distinct embedding_model from rag_documents')}
        if versions!={INDEX_VERSION}:raise ValueError('Index encoder version mismatch; rebuild before searching.')
        indexed=dict(db.execute('select record_id,content from rag_documents'))
    stale=sum(indexed.get(r['id'])!=document_text(r) for r in records)
    facets=queries(req);scores={};hits={}
    explicit_weights=req.get('retrieval_weights')
    weights=explicit_weights or {'semantic_similarity':.6,'keyword_match':.15,'narrative_mechanism_match':.25}
    with sqlite3.connect(':memory:') as lexical:
        lexical.row_factory=sqlite3.Row
        lexical.execute("create virtual table documents using fts5(record_id UNINDEXED, content, tokenize='porter unicode61')")
        lexical.executemany('insert into documents values (?,?)',[(rid,document_text(r)) for rid,r in enabled.items()])
        for q in facets:
            expression=' OR '.join('"'+t+'"' for t in terms(q['text'])[:35])
            rows=lexical.execute('select record_id,bm25(documents) as score from documents where documents match ? order by score,record_id limit 25',(expression,)).fetchall()
            for rank,row in enumerate(rows,1):
                rid=row['record_id'];scores[rid]=scores.get(rid,0)+q.get('weight',1)*(weights['keyword_match']*41/(40+rank) if explicit_weights else 1/(40+rank))
                hits.setdefault(rid,[]).append({'query':q['id'],'channel':'keyword','rank':rank,'bm25':row['score']})
    if req['retrieval_mode']=='hybrid':
        if stale:raise ValueError(f'{stale} index projections are stale. Rebuild before hybrid search.')
        from rag.settings import Settings
        from rag.db import search
        from rag.identity import MODEL_NAME,EMBEDDING_DIMENSIONS
        settings=Settings(str(path),MODEL_NAME,EMBEDDING_DIMENSIONS)
        for q in facets:
            for rank,h in enumerate(search(settings,q['text'],60 if explicit_weights else 8,1.0 if explicit_weights else .65,None,None,'Balanced'),1):
                if explicit_weights and h.semantic_rank is None:continue
                contribution=q.get('weight',1)*(weights['semantic_similarity']*41/(40+h.semantic_rank) if explicit_weights else 1/(40+rank))
                scores[h.record_id]=scores.get(h.record_id,0)+contribution
                hits.setdefault(h.record_id,[]).append({'query':q['id'],'channel':'semantic' if explicit_weights else 'hybrid','rank':h.semantic_rank if explicit_weights else rank,'score':h.score,'weighted_contribution':contribution})
    # Controlled mechanism labels get a traceable boost when all their words match
    # user terms, with a small general morphology/synonym map. No title-specific rules.
    for q in facets:
        wanted=mechanism_terms(q['text'])
        for rid,record in enabled.items():
            mechanism=mechanism_terms(record.get('narrative_mechanism',''))
            overlap=len(mechanism&wanted)/len(mechanism) if mechanism else 0
            if (explicit_weights and overlap>0) or (not explicit_weights and len(mechanism)>=2 and mechanism<=wanted):
                scores[rid]=scores.get(rid,0)+q.get('weight',1)*(weights['narrative_mechanism_match']*overlap if explicit_weights else .035)
                hits.setdefault(rid,[]).append({'query':q['id'],'channel':'controlled_mechanism','matched_terms':sorted(mechanism&wanted),'overlap':overlap})
    requested=req.get('references',[])
    for ref in requested:
        if ref['record_id'] not in enabled:raise ValueError('Requested reference is unavailable or disabled: '+ref['record_id'])
    ordered=list(dict.fromkeys([ref['record_id'] for ref in requested]+sorted(scores,key=lambda r:(-scores[r],r))))
    selected=[];seen=set()
    for rid in ordered:
        record=enabled[rid];canonical=record.get('retrieval',{}).get('canonical_id',rid)
        if canonical in seen:continue
        seen.add(canonical)
        refs=[ref for ref in requested if ref['record_id']==rid]
        selected.append({'id':rid,'title':record['title'],'mode':req['retrieval_mode'],'canonical_id':canonical,
                         'ranking_score':scores.get(rid,0),'mechanism':record.get('narrative_mechanism'),'analysis':record.get('literary_analysis'),
                         'themes':record.get('theme_keywords',[]),'techniques':record.get('literary_techniques',[]),
                         'guidance':record.get('prompt_refinement'),'limits':record.get('references',{}).get('version_notes') or record.get('notes'),
                         'retrieval_hits':hits.get(rid,[]),'requested_scopes':refs,'selection':'explicit_reference' if refs else 'ranked_match'})
        if len(selected)>=max(3,min(6,len(requested)+2)):break
    chunks=guide_chunks((ROOT/'data/MASTER_GUIDE.md').read_text())
    craft={}
    all_terms=set(terms(' '.join(q['text'] for q in facets)))
    preferred={'humanizer':[19,20],'rhetoric_quality':[19,20],'writer':[9,20],'story_quality':[3,5],'scene_designer':[9,26],'architect':[8,9],'refiner':[2,5]}
    for role,chapters in ROLE_CHAPTERS.items():
        candidates=[c for c in chunks if c['chapter'] in chapters]
        wanted=all_terms|set(terms(ROLE_TERMS[role]))
        candidates.sort(key=lambda c:(-len(set(terms(c['heading']+' '+c['content'][:1800]))&wanted),c['id']))
        # Diversify by chapter so a generic introduction cannot consume the whole packet.
        chosen=[];seen_chapters=set()
        for chapter in preferred[role]:
            best=next((c for c in candidates if c['chapter']==chapter),None)
            if best:
                chosen.append({**best,'content':best['content'][:1100]});seen_chapters.add(chapter)
        for c in candidates:
            if len(chosen)>=2:break
            if c['chapter'] in seen_chapters:continue
            chosen.append({**c,'content':c['content'][:1100]});seen_chapters.add(c['chapter'])
            if len(chosen)==2:break
        craft[role]=chosen
    return {'query':' | '.join(q['text'] for q in facets),'queries':facets,'sources':selected,
            'craft_by_role':craft,'guide_sections':[c['content'] for c in craft['refiner']],
            'corpus_sha256':hashlib.sha256(corpus.read_bytes()).hexdigest(),'index_version':INDEX_VERSION,
            'stale_embedding_records':stale,'mode':req['retrieval_mode'],
            'adaptation_policy':req.get('adaptation',{}),'retrieval_weights':explicit_weights,'scoring_policy':'Weighted normalized reciprocal ranks (41/(40+rank)) plus mechanism-label overlap, summed over weighted query facets; explicit references pinned separately.' if explicit_weights else 'Legacy rank fusion',
            'warning':'Model-authored analyses with source limits. Retrieval selects reference material; it does not establish historical influence, originality, or successful application.'}


def application_packet(req,retrieval,role,scene_id=None):
    selected=[]
    for source in retrieval['sources']:
        scopes=source.get('requested_scopes',[])
        relevant=[s for s in scopes if s['scope']=='story' or (scene_id and (s.get('target')==scene_id or (s['scope']=='chapter' and scene_id.startswith(s.get('target','invalid')))))]
        if scopes and not relevant and scene_id:continue
        selected.append({k:source.get(k) for k in ['id','title','mechanism','guidance','limits'] }|{'purposes':[s['purpose'] for s in relevant],'do_not_borrow':[x for s in relevant for x in s.get('do_not_borrow',[])]})
    limit=req.get('adaptation',{}).get('max_active_sources_per_scene',2)
    if req.get('adaptation',{}).get('strength')==0:selected=[]
    return {'references':selected[:limit] if scene_id else selected,
            'craft':retrieval.get('craft_by_role',{}).get(role,[]),
            'adaptation':req.get('adaptation',{}),
            'instruction':'Use only what serves the scene. Cite source IDs in planning/review metadata, never device labels in story prose. Preserve user choices and explicit spinoff continuity. Do not transplant plots unless requested or force every reference into every scene.'}
