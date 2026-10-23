"""Source-verified draft continuity remains separate from approved universe canon."""
import copy
from .contracts import require


def history(state):
    return state['memories']+state.get('draft_memories',[])


def append_verified_branch(state,memory,scene_id,prose,memory_review,*,expected_state_sha256=None):
    from .canon import append
    from .patching import digest
    require(memory_review.get('pass') and not memory_review.get('unverified'),'Draft continuation requires verified memory')
    require(memory_review.get('source_sha256')==digest(prose),'Draft memory review targets stale prose')
    from .batch_pipeline import bind_state
    require(memory_review.get('state_sha256')==(expected_state_sha256 or bind_state(state)),'Draft memory review targets a different input state')
    require(memory_review.get('memory_sha256')==bind_state(memory) and not memory.get('unverified'),'Draft memory review targets stale facts')
    updates=memory['memories']
    combined=copy.deepcopy(state);combined['memories']=copy.deepcopy(history(state));combined['draft_memories']=[]
    for fact in updates:
        require(fact.get('evidence_prose_sha256')==digest(prose),'Draft fact targets stale prose')
    records=[{**m,'continuity_scope':'draft_branch','literary_status':'provisional'} for m in updates]
    append(combined,records,scene_id)
    state.setdefault('draft_continuity_receipts',[]).append({'scene':scene_id,'source_sha256':digest(prose),'memory_sha256':memory_review['memory_sha256'],'memory_verified':True,'literary_approved':False})
    state['draft_memories']=combined['memories'][len(state['memories']):]
    return state['draft_memories']
