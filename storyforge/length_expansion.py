"""Expand a short scene by inserting source-owned detail, preserving existing prose."""
import math,re
from pathlib import Path
from .contracts import require
from .evidence import passages,payload
from .patching import apply,digest
from .craft import validate_prose
from .storage import save


def expand(executor,req,prose,data,out):
    catalog=passages(prose);by_id={p['id']:p for p in catalog}
    require(len(catalog)>1,'Targeted expansion requires separate scene paragraphs')
    owned={p['id'] for p in catalog[:-1]}  # Keep the exact final exit last.
    count=len(prose.split());target=req['words_per_scene']
    minimum=max(1,math.ceil(target*req.get('min_words_ratio',.75))-count)
    desired=max(minimum,target-count)
    maximum=math.floor(target*req.get('max_words_ratio',1.3))-count
    require(0<minimum<=maximum,'No valid expansion word budget')
    def validate(raw):
        require(isinstance(raw,str),'Expansion requires insertion blocks')
        matches=list(re.finditer(r'(?ms)^\s*INSERT_AFTER\s+(p\d+)\s*\n(.*?)^\s*END_INSERT\s*$',raw))
        remainder=raw
        for match in reversed(matches):remainder=remainder[:match.start()]+remainder[match.end():]
        require(1<=len(matches)<=3 and not remainder.strip(),'Return only 1–3 complete INSERT_AFTER blocks')
        additions={}
        for match in matches:
            pid,text=match.groups();text=text.strip()
            require(pid in owned and pid not in additions,'Duplicate or unowned expansion anchor')
            require(bool(text),'Empty scene expansion')
            additions[pid]=text
        added=sum(len(text.split()) for text in additions.values())
        require(added>=minimum and (req.get('length_policy',{}).get('overflow')=='advisory' or added<=maximum),f'Expansion added {added} words; must add at least {minimum} words'+('' if req.get('length_policy',{}).get('overflow')=='advisory' else f' and at most {maximum} words'))
        revised=apply(prose,{pid:by_id[pid]['text']+'\n\n'+text for pid,text in additions.items()},digest(prose))
        validate_prose(revised,req,check_length=True)
        return {'prose':revised,'additions':additions,'added_words':added}
    result=executor.call('repair',{**data,**payload(prose),'allowed_insertion_anchors':sorted(owned),
        'length_repair':{'current_words':count,'target_total_words':target,'minimum_new_words':minimum,'target_new_words':desired,'maximum_new_words':maximum},
        'preservation_policy':'All supplied scene paragraphs are immutable; additions are inserted between them. The final paragraph must remain the exact final exit.'},
        f'The existing scene is too short. Add {minimum}–{maximum} NEW words of dramatized detail between its existing paragraphs, aiming for {desired} new words. Return only 1–3 blocks: INSERT_AFTER p001, then the NEW prose on following lines, then END_INSERT. Use only allowed anchor IDs. Do not reproduce or rewrite existing prose. Develop already attempted actions, sensory particulars, competing motives, resistance or consequences at that precise moment; no recaps, padding, extra resources, new witnesses, changed outcomes or new plot events. Preserve individual knowledge, POV, style and chronology. Do not extend beyond the existing final exit. The application counts added words and rejects insufficient additions.',
        tokens=min(4200,max(1600,desired*3+400)),output_format='text',response_schema=False,validator=validate)
    save(Path(out)/'length-expansion.json',{'source_sha256':digest(prose),'candidate_sha256':digest(result['prose']),
        'original_words':count,'final_words':len(result['prose'].split()),'added_words':result['added_words'],
        'anchors':list(result['additions']),'existing_prose_preserved':True})
    return result['prose']
