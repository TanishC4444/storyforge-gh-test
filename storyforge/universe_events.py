"""Creative proposals are distinct from evidence-backed character/thread state."""
import copy,re
from .contracts import require


def freedom(req):
    raw=req.get('creative_freedom',{})
    if not isinstance(raw,dict):return {'enabled':False}
    return {'enabled':False,'intensity':.8,'new_characters':True,'character_deaths':True,
            'resurrection':False,'protected_characters':[],'max_new_per_scene':1,'cast_limit':32,**raw}


def validate_config(req):
    f=freedom(req)
    require(type(f['enabled']) is bool,'Invalid creative freedom enabled')
    if not f['enabled']:return
    for key in ['enabled','new_characters','character_deaths','resurrection']:require(type(f[key]) is bool,'Invalid creative freedom '+key)
    require(type(f['intensity']) in {int,float} and 0<=f['intensity']<=1,'Creative intensity must be 0–1')
    require(type(f['max_new_per_scene']) is int and 0<=f['max_new_per_scene']<=3,'New cast budget must be 0–3')
    require(type(f['cast_limit']) is int and 1<=f['cast_limit']<=32,'Cast limit must be 1–32')
    require(type(f.get('flexible_pov',False)) is bool,'Invalid flexible POV policy')
    characters=req.get('characters',[])
    ids={c.get('id') for c in characters if isinstance(c,dict)} if isinstance(characters,list) else set()
    require(isinstance(f['protected_characters'],list) and all(isinstance(cid,str) for cid in f['protected_characters']) and set(f['protected_characters'])<=ids,'Unknown protected character')


def normalize_existing_cast(req,scene):
    """Lossless normalization: an exact existing ID/name is not a new identity."""
    value=copy.deepcopy(scene);known={c['id']:c['name'].casefold() for c in req['characters']}
    additions=value.get('new_characters',[])
    if isinstance(additions,list):
        value['new_characters']=[c for c in additions if not (isinstance(c,dict) and isinstance(c.get('name'),str) and known.get(c.get('id'))==c['name'].casefold())]
    return value


def extended_request(req,scene):
    f=freedom(req);v=copy.deepcopy(req);additions=scene.get('new_characters',[])
    require(isinstance(additions,list),'New characters must be a list')
    require(not additions or f['enabled'] and f['new_characters'],'New characters not authorized')
    if additions:
        require(len(additions)<=f['max_new_per_scene'] and len(req['characters'])+len(additions)<=f['cast_limit'],'New cast budget exceeded')
        ids={c['id'] for c in req['characters']};names={c['name'].casefold() for c in req['characters']}
        for c in additions:
            require(isinstance(c,dict) and isinstance(c.get('id'),str) and re.fullmatch(r'[a-zA-Z0-9_-]{1,40}',c['id']) and c['id'] not in ids,'Invalid new character identity')
            require(all(isinstance(c.get(k),str) and c[k].strip() for k in ['name','goal','voice','introduction_cause']),'New character needs name, goal, voice and introduction_cause')
            require(c['name'].casefold() not in names,'Duplicate new character name')
            require(c['id'].casefold() not in {x.casefold() for x in ids},'Duplicate character identity')
            ids.add(c['id']);names.add(c['name'].casefold());v['characters'].append({**c,'cast_status':'proposed','profile_origin':'scene_director'})
    return v


def current_life(memories):
    from .canon import index
    return {m['subject']:m['life_state'] for m in index(memories)['current'] if m.get('subject') and m.get('life_state')}


def validate_lifecycle(state,updates):
    from .continuation import history
    f=freedom(state.get('request',{}));life=current_life(history(state))
    for m in updates:
        if not m.get('life_state'):continue
        subject=m['subject'];previous=life.get(subject)
        if f['enabled']:
            require(m['life_state']!='dead' or f['character_deaths'] and subject not in f['protected_characters'],'Unauthorized character death')
        require(previous!='dead' or m['life_state']=='dead' or f.get('resurrection',False) and m['life_state']=='alive','Unauthorized resurrection')
        life[subject]=m['life_state']


DIRECTOR_POLICY='''CREATIVE DEVELOPMENT: Random draws are invitations, never facts. Choose causally compatible shocks with escalating consequences: betrayal, divided loyalty, catastrophic success, faction fracture, costly death or a revelation that reinterprets earlier evidence. A large twist needs planted observable clues before payoff; record unresolved promises and who knows each clue. Do not repeat completed events, pile unrelated disasters onto the same scene, or reset losses. Leave room for quiet tension and fallout. When creative_freedom.enabled permits it, new_characters may contain at most the configured number of {id,name,goal,voice,introduction_cause}; introduce each through a current conflict. Existing IDs stay immutable. Deaths must be earned in actual prose, respect protected characters, remain consequential, and never be silently reversed. Never stage a known dead character as currently alive. Use threats/uncertain claims rather than inventing offstage canon. Scene plans are not accepted history.'''


def resume_cast(req,old):
    """Carry generated identities across manual resumes, without replacing author cast."""
    existing={c['id']:c for c in req['characters']}
    for c in old['request']['characters']:
        if c['id'] not in existing and c.get('profile_origin')=='scene_director':req['characters'].append(copy.deepcopy(c))
    old_cast={c['id']:c['name'] for c in old['request']['characters']};new_cast={c['id']:c['name'] for c in req['characters']}
    require(all(new_cast.get(cid)==name for cid,name in old_cast.items()),'Existing character identities must remain stable')
