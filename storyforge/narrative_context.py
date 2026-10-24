"""Reading order and source-grounded thread evidence, without another model pass."""
from .patching import digest
from .evidence import passages
from .continuation import history

TEMPORAL_POLICY='''Reading order is not event chronology. Use the authored time and setting, explicitly orient the reader at temporal transitions, and preserve the intended POV. Earlier-present scenes can be read before a flashback without giving past characters future knowledge. A historical resource, location or life state does not reset the present; keep its historical time explicit in extracted text and do not supersede a later state with it. Present-day initial conditions are not automatically conditions of a flashback. Distinguish reader knowledge from what each character knew at that event time; require an enacted observation, disclosure or supported prior memory for knowledge use. If timing is unspecified, preserve uncertainty instead of inventing a chronology.'''

FORESHADOW_POLICY='''Foreshadowing must be an observable clue, action, cost or promise on the page. Track it with a stable thread identity. A payoff must follow actual earlier setup in reading order and change a choice, interpretation or consequence; an author plan is not evidence that setup happened. Reinterpret the earlier evidence without contradicting it. Do not repeat the discovery merely to remind the reader. Unresolved threads may remain open when the brief permits; do not demand every future payoff in an opening scene.'''

POLICY=TEMPORAL_POLICY+'\n'+FORESHADOW_POLICY


def context(state,card,*,include_policy=True):
    designs=state['request'].get('scene_designs',[])
    source_scenes={s['id']:s for s in state.get('universe_history',[])+state.get('accepted',[])}
    ordered=[{'scene_id':s['id'],'authored_time':s.get('time','unspecified'),'setting':s.get('setting',s.get('location',''))} for s in designs]
    threads=[];catalogs={}
    for fact in history(state):
        if fact.get('kind')!='thread':continue
        row={k:fact[k] for k in ('id','thread_id','thread_state','text','known_by','source','supersedes') if k in fact}
        source=source_scenes.get(fact.get('source'))
        # Resolve only existing setup anchors against the exact approved/verified
        # source. Never present a plan or stale quotation as an enacted clue.
        if source and fact.get('evidence_prose_sha256')==digest(source['prose']):
            sid=source['id']
            if sid not in catalogs:catalogs[sid]={p['id']:p for p in passages(source['prose'])}
            row['source_sha256']=digest(source['prose'])
            row['source_evidence']=[{'id':pid,'text':catalogs[sid][pid]['text']} for pid in fact.get('evidence_ids',[]) if pid in catalogs[sid]]
        threads.append(row)
    result={'current_scene_id':card['id'],'reading_order':ordered,'established_threads':threads,
            'scope':'An author navigation aid alongside full canon. The scene descriptions are plans; only source-bound memories establish events. No memory is discarded.'}
    if include_policy:result['policy']=POLICY
    return result
