"""Small independent development proposals; immutable author requirements stay authoritative."""
import copy,json,hashlib
from pathlib import Path
from .contracts import require
from .craft import compile_brief
from .inference import Executor
from .storage import save,load
from .worker_policy import parallel

GROUPS={
 'plot':['plot_design','chapter_arcs','chapter_contract','ending_tendency'],
 'characters':['characters'],
 'world':['world_design','world_rules','initial_facts'],
 'scenes':['scene_designs','chapters','scenes_per_chapter','words_per_scene'],
 'style':['genre','tone_mood','sensory_detail','style','keywords','references','adaptation'],
}
SCHEMA={'type':'object','properties':{key:{'type':'array','items':{'type':'string'},'maxItems':limit}
        for key,limit in [('guidance',5),('assumptions',2),('open_decisions',2)]},
        'required':['guidance','assumptions','open_decisions'],'additionalProperties':False}


def validate_part(value):
    require(isinstance(value,dict) and set(value)==set(SCHEMA['properties']),'Refinement part needs guidance, assumptions and open_decisions')
    for key,rule in SCHEMA['properties'].items():
        require(isinstance(value[key],list) and len(value[key])<=rule['maxItems'] and
                all(isinstance(s,str) and s.strip() and len(s)<=600 for s in value[key]),'Invalid or oversized refinement '+key)
    require(bool(value['guidance']),'Refinement part needs practical guidance')
    return value


def scene_layout(req):
    return [{'id':s['id'],'pov':s.get('pov'),'participants':s.get('participants',[]),
             'location':s['location'],'what_happens':s.get('development',s['dramatic_function']),
             'choice_and_consequence':s.get('choice_and_consequence','Develop the planned choice and its material cost.'),
             'restrictions':s.get('restrictions','')} for s in req['scene_designs']]


def develop_part(req,retrieval,name,out,backend,budget_folder=None):
    require(name in GROUPS,'Unknown refinement category')
    fields=GROUPS[name];out=Path(out)
    executor=Executor(copy.deepcopy(req),out,backend)
    if executor.hosted and budget_folder is not None:
        from .hosted import GoogleHosted
        executor.hosted=GoogleHosted(budget_folder)
    result=executor.call('refiner_part',{
        'category':name,'premise':req['premise'],'nonnegotiable_form':req['pov'],
        'author_requirements':{k:req.get(k) for k in fields},
        'source_references':[{'id':s['id'],'mechanism':s.get('mechanism'),'limits':s.get('limits')} for s in retrieval['sources']] if name in {'plot','style'} else []},
        'Develop ONLY this category in at most five short practical guidance items. Preserve every explicit choice. Treat other categories as fixed external constraints; do not invent their events. Suggestions are proposals, never accepted canon. Mark assumptions and unresolved decisions separately. For scenes specify action, resistance, choice and consequence; for plot twists require prior setup and a fair information boundary; for characters use conflicting duties, specific behavior and costs; for style preserve POV, register and imagery. Never require a twist in every scene. Return only the supplied JSON schema.',
        tokens=850,validator=validate_part,response_schema=SCHEMA)
    save(out/'refinement.json',result)
    return result


def assemble(req,parts,out):
    require(set(parts)==set(GROUPS),'Missing or duplicate refinement category')
    parts={name:validate_part(parts[name]) for name in GROUPS}
    out=Path(out)
    result=compile_brief(req)
    result['expanded_story_elements']=[f'Proposed {name}: '+line for name,part in parts.items() for line in part['guidance']]
    result['assumptions']=[f'{name}: '+line for name,part in parts.items() for line in part['assumptions']]
    result['open_decisions']=[f'{name}: '+line for name,part in parts.items() for line in part['open_decisions']]
    save(out/'refinement-parts.json',parts);save(out/'scene-layout.json',scene_layout(req))
    return result


def base_hash(req,retrieval):
    return hashlib.sha256(json.dumps([req,retrieval],sort_keys=True).encode()).hexdigest()


def run_part(state,name,out,backend):
    value={'category':name,'base_sha256':base_hash(state['request'],state['retrieval']),
           'result':develop_part(state['request'],state['retrieval'],name,Path(out)/'development',backend)}
    save(Path(out)/'refinement-part.json',value)
    return value


def join_parts(state,source,out):
    values=[load(p) for p in sorted(Path(source).rglob('refinement-part.json'))]
    require(sorted(v['category'] for v in values)==sorted(GROUPS),'Missing or duplicate refinement category')
    require(all(v['base_sha256']==base_hash(state['request'],state['retrieval']) for v in values),'Refinement category uses a stale brief or retrieval snapshot')
    state['refinement']=assemble(state['request'],{v['category']:v['result'] for v in values},out)
    state['refinement_method']='parallel_scoped_proposals_immutable_author_brief'
    state['scene_layout']=scene_layout(state['request'])
    save(Path(out)/'refinement.json',state['refinement']);save(Path(out)/'snapshot.json',state)
    return state


def refine(req,retrieval,out,backend):
    out=Path(out)
    def develop(item):
        name,_=item
        return name,develop_part(req,retrieval,name,out/'parts'/name,backend,out/'provider-budget')
    return assemble(req,dict(parallel(req,'refinement',list(GROUPS.items()),develop)),out)
