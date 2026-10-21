"""Mechanical defects are blocking; these checks do not pretend to judge literary merit."""
import re
from difflib import SequenceMatcher
from .evidence import passages

def defects(prose,previous=''):
    issues=[];seen={}
    for p in passages(prose):
        normalized=' '.join(p['text'].lower().split())
        if normalized=='* * *':continue
        if normalized in seen:issues.append('Duplicate paragraph '+p['id']+' repeats '+seen[normalized])
        seen[normalized]=p['id']
    for pattern,label in [(r'[“”"]','Quoted speech or quotation violates no-dialogue brief'),(r'(?m)^\s*#{1,6}\s','Markdown heading in prose'),(r'\}\s*\}\s*,|\{"(?:prose|text|replacements)"','Serialization leaked into prose'),(r'(?i)\b(?:sing,? muse|dear reader|opening a larger epic|the local climax|the scene demonstrates)\b','Narratorial instruction or structural summary'),(r'\b(?:I|we|our|you|your)\b','First/second person violates third-person-only brief')]:
        if re.search(pattern,prose):issues.append(label)
    if re.search(r'(?i)\b(the|a|an|of|to|his|her)\s+\1\b',prose):issues.append('Accidentally repeated function word')
    if re.search(r'(?i)\bThestor,? (?:the |a )?(?:blind|sightless|hearth-priest)',prose):issues.append('Cast identity corruption: Thestor is the mortal smith, not the blind priest')
    sentences=re.split(r'(?<=[.!?])\s+',prose);seen_sentences=set()
    for sentence in sentences:
        normalized=' '.join(sentence.lower().split())
        if len(normalized)>70 and normalized in seen_sentences:issues.append('Repeated sentence: '+sentence[:100])
        seen_sentences.add(normalized)
    if previous:
        for p in passages(prose):
            if len(p['text'])>100 and p['text'] in previous:issues.append('Passage copied from previous scene')
    if len(prose.split())<550:issues.append('Scene is underdeveloped: fewer than 550 words')
    return list(dict.fromkeys(issues))

def change_metrics(before,after):
    return {'before_words':len(before.split()),'after_words':len(after.split()),'changed_fraction':round(1-SequenceMatcher(None,before,after,autojunk=False).ratio(),4)}


def rhetorical_signals(prose):
    """Contextual editing leads, never authorship tests or automatic word bans."""
    patterns={
        'explained_gesture':r'(?i)\b(?:the gesture was|his gaze was|her gaze was|a gesture of|invitation that felt)\b',
        'abstract_emotion':r'(?i)\b(?:mixture of|hope and dread|felt the trap|heart remained|weight of the bargain|heart aching|heart pounding)\b',
        'automatic_gesture':r'(?i)\b(?:eyes narrowing|expression softening|knuckles white|voice measured|gaze remained resolute)\b',
        'declared_significance':r'(?i)\b(?:not a mere curiosity|heart of the conflict|everything changed|the trial demonstrated|brought a costly local victory)\b',
        'possible_modern_register':r'(?i)\b(?:administrative|technical labor|casting method|campaigning season|psychological|leverage)\b',
    }
    return [{'kind':kind,'quote':m.group(),'start':m.start(),'guidance':'Assess in context: replace explanatory or generic language with its actual observation or consequence; retain literal or earned use.'} for kind,pattern in patterns.items() for m in re.finditer(pattern,prose)]
