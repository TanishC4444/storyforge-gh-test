"""Small independent development proposals; immutable author requirements stay authoritative."""
import copy
from pathlib import Path
from .contracts import require
from .craft import compile_brief
from .inference import Executor
from .storage import save
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


def refine(req,retrieval,out,backend):
    out=Path(out)
    def develop(item):
        name,fields=item
        local=copy.deepcopy(req)
        # A small CPU fallback and one shared on-disk provider budget per runner.
        executor=Executor(local,out/'parts'/name,backend)
        if executor.hosted:
            from .hosted import GoogleHosted
            executor.hosted=GoogleHosted(out/'provider-budget')
        result=executor.call('refiner_part',{
            'category':name,'premise':req['premise'],'nonnegotiable_form':req['pov'],
            'author_requirements':{k:req.get(k) for k in fields},
            'source_references':[{'id':s['id'],'mechanism':s.get('mechanism'),'limits':s.get('limits')} for s in retrieval['sources']] if name in {'plot','style'} else []},
            'Develop ONLY this category in at most five short practical guidance items. Preserve every explicit choice. Treat other categories as fixed external constraints; do not invent their events. Suggestions are proposals, never accepted canon. Mark assumptions and unresolved decisions separately. For scenes specify action, resistance, choice and consequence; for plot twists require prior setup and a fair information boundary; for characters use conflicting duties, specific behavior and costs; for style preserve POV, register and imagery. Never require a twist in every scene. Return only the supplied JSON schema.',
            tokens=850,validator=validate_part,response_schema=SCHEMA)
        save(out/'parts'/name/'refinement.json',result)
        return name,result
    parts=dict(parallel(req,'refinement',list(GROUPS.items()),develop))
    result=compile_brief(req)
    result['expanded_story_elements']=[f'Proposed {name}: '+line for name,part in parts.items() for line in part['guidance']]
    result['assumptions']=[f'{name}: '+line for name,part in parts.items() for line in part['assumptions']]
    result['open_decisions']=[f'{name}: '+line for name,part in parts.items() for line in part['open_decisions']]
    save(out/'refinement-parts.json',parts);save(out/'scene-layout.json',scene_layout(req))
    return result
