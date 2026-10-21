"""Source-anchored paragraph changes. Unchanged text is never regenerated."""
import hashlib
from .contracts import require
from .evidence import passages
from .tracking import event


def digest(text):return hashlib.sha256(text.encode()).hexdigest()


def apply(prose,replacements,source_hash):
    require(source_hash==digest(prose),'Patch targets stale prose')
    catalog={p['id']:p for p in passages(prose)}
    require(isinstance(replacements,dict) and all(k in catalog and isinstance(v,str) for k,v in replacements.items()),'Invalid paragraph patch')
    edits=[]
    for pid,text in replacements.items():
        original=catalog[pid]
        if text!=original['text']:edits.append((original['start'],original['end'],text))
    for start,end,text in sorted(edits,reverse=True):prose=prose[:start]+text+prose[end:]
    require(bool(prose.strip()),'Patch deleted entire scene')
    return prose


def targets(prose,reviews):
    catalog={p['id']:p for p in passages(prose)};selected={};direct={};conflicts=set()
    for review in reviews:
        for issue in review.get('issues',[]):
            # A review may cite several paragraphs, but changes remain individually addressed.
            ids=issue.get('evidence_ids') or [s.get('id') for s in issue.get('evidence_spans',[]) if s.get('id')]
            if not ids and issue.get('quote'):
                ids=[pid for pid,p in catalog.items() if issue['quote'] in p['text']]
            for pid in ids:
                if pid not in catalog:continue
                selected.setdefault(pid,{'id':pid,'original':catalog[pid]['text'],'issues':[]})['issues'].append({k:issue.get(k) for k in ['category','problem','fix']})
                if len(ids)==1 and isinstance(issue.get('replacement'),str):
                    if pid in direct and direct[pid]!=issue['replacement']:conflicts.add(pid)
                    direct[pid]=issue['replacement']
    return selected,{k:v for k,v in direct.items() if k not in conflicts}


def repair(executor,req,prose,reviews):
    selected,direct=targets(prose,reviews)
    if not selected:return prose,{'changed':False,'reason':'No source-bound issues available'}
    unresolved={k:v for k,v in selected.items() if k not in direct}
    replacements=dict(direct)
    if unresolved:
        schema={'type':'object','properties':{'replacements':{'type':'object','properties':{k:{'type':'string'} for k in unresolved},'required':list(unresolved),'additionalProperties':False}},'required':['replacements'],'additionalProperties':False}
        def validate(value):
            require(isinstance(value,dict) and isinstance(value.get('replacements'),dict),'Patch needs replacements object')
            require(set(value['replacements'])==set(unresolved),'Patch must address each selected paragraph exactly once')
            apply(prose,value['replacements'],digest(prose))
            return value
        event('targeted_edit','Generating only cited paragraph replacements',paragraphs=list(unresolved))
        result=executor.call('humanizer',{'paragraphs':list(unresolved.values()),'style':req['style'],'world_rules':req['world_rules'],'instruction':'Preserve events, private knowledge, deliberate epic diction and all unaffected facts. Fix the supplied issues. Empty replacement deletes only the selected paragraph.'},
            'Return only JSON replacements keyed by every supplied paragraph ID. Replace full cited paragraphs; never rewrite the whole scene.',tokens=min(1800,350*len(unresolved)+250),validator=validate,response_schema=schema)
        replacements.update(result['replacements'])
    revised=apply(prose,replacements,digest(prose))
    return revised,{'changed':revised!=prose,'source_sha256':digest(prose),'changed_paragraphs':list(replacements),'direct_editor_fixes':len(direct),'targeted_editor_fixes':len(unresolved)}
