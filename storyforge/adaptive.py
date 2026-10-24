"""Coherent source windows reduce request count without removing any source facts."""
import math


def enabled(req):return bool(req.get('performance',{}).get('adaptive_batches'))


def writing_count(req):
    return max(1,min(6,math.ceil(req['words_per_scene']/(1500 if enabled(req) else 320))))


def windows(catalog,words=450):
    result=[];group=[];size=0
    for p in catalog:
        n=len(p['text'].split())
        if group and size+n>words:result.append(group);group=[];size=0
        group.append(p);size+=n
    if group:result.append(group)
    return result


def repetitions(prose):
    """Evidence candidates only; the reviewer decides whether repetition is intentional."""
    import re
    from .evidence import passages
    seen={}
    for p in passages(prose):
        for span in re.findall(r'["“]([^"”]{40,})["”]',p['text']):
            text=' '.join(span.lower().split())
            if len(text.split())>=8:seen.setdefault(text,[]).append(p['id'])
    return [{'repeated_dialogue':text,'evidence_ids':list(dict.fromkeys(ids))} for text,ids in seen.items() if len(ids)>1]
