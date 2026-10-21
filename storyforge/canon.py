"""Append-only, evidence-bound history with explicit, validated state transitions."""
from .contracts import require


def index(memories):
    records=[];by_id={}
    for position,memory in enumerate(memories):
        record={**memory,'id':memory.get('id',f'm{position:05}')}
        require(record['id'] not in by_id,'Duplicate canonical memory ID')
        records.append(record);by_id[record['id']]=record
    positions={record['id']:position for position,record in enumerate(records)}
    superseded=set()
    for record in records:
        for old_id in record.get('supersedes',[]):
            old=by_id.get(old_id)
            require(old is not None and positions[old_id]<positions[record['id']],'Memory transition must cite an earlier fact')
            require(bool(record.get('fact_key')) and record['fact_key']==old.get('fact_key'),'Memory transition changed its fact key')
            require(record['kind']==old['kind'],'Memory transition changed fact kind')
            superseded.add(old_id)
    return {'history':records,'current':[r for r in records if r['id'] not in superseded]}


def append(state,updates,scene_id):
    existing=index(state['memories'])['history']
    new=[]
    for item in updates:
        item={**item,'id':f'm{len(existing)+len(new):05}','source':scene_id,
              'state_version':state['version']}
        new.append(item)
    # Validation is atomic: no partial update if a transition is unsupported.
    result=index(existing+new)
    state['memories']=result['history'];state['canon']=result
    return result


def working(state,character=None,query='',budget=6500):
    """Project after visibility filtering: an uninformed actor retains their old belief."""
    from .coordinator import visible
    import json,re
    records=index(state['memories'])['history']
    if character is not None:
        records=visible(records,character,{s['id']:s['participants'] for s in state['accepted']})
    visible_ids={m['id'] for m in records}
    hidden={old for m in records for old in m.get('supersedes',[]) if old in visible_ids}
    active=[m for m in records if m['id'] not in hidden]
    words=set(re.findall(r'\w+',query.lower()))
    ranked=sorted(enumerate(active),key=lambda pair:(
        pair[1].get('kind') in {'resource','relationship','thread'},
        len(words & set(re.findall(r'\w+',pair[1]['text'].lower()))),pair[0]),reverse=True)
    selected=[];used=0
    for _,memory in ranked:
        compact={k:v for k,v in memory.items() if k not in {'evidence','evidence_spans','evidence_match'}}
        size=len(json.dumps(compact,ensure_ascii=False))
        if used+size<=budget:selected.append(compact);used+=size
    ids={m['id'] for m in selected}
    return {'facts':selected,'omitted_ids':[m['id'] for m in active if m['id'] not in ids],
            'history_count':len(records),'policy':'Current supported facts only; superseded history remains in canon.json. Author knowledge is not actor knowledge.'}


def cards(memories):
    """Prompt projections retain identity/provenance; full evidence stays in history."""
    keys={'id','kind','text','known_by','holder','claim_source','source','state_version',
          'fact_key','supersedes','evidence_prose_sha256'}
    return [{k:v for k,v in m.items() if k in keys} for m in index(memories)['current']]


def recording_context(state,card):
    view=working(state,query=str(card),budget=8000)
    return {'prior_canon':view['facts'],'omitted_prior_ids':view['omitted_ids']}
