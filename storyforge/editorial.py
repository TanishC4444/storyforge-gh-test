"""Evidence-backed editorial contracts. Format compliance is not literary quality."""
from __future__ import annotations
import re
from .contracts import require, review, ContractError
from .evidence import EvidenceError, bind, payload

STORY_CHECKS=['scene_change','character_agency','character_depth','causal_alternatives','dialogue_tactics','continuity_clock','pov_knowledge','subplot_function','reference_application']
RHETORIC_CHECKS=['redundant_explanation','viewpoint_specificity','emotional_labeling','figurative_coherence','gesture_function','rhythm_repetition','instruction_leakage','style_fidelity']
DESIGN_CHECKS=['medium_length','themes_tensions','scene_design','world_rules','character_depth','plot_subplots','genre','tone_mood','references_adaptation','figurative_language','causal_alternatives','information_order']


def checks(value, required, resolve):
    require(isinstance(value,list),'Review requires a checks array')
    require(all(isinstance(x,dict) for x in value),'Each check must be an object')
    require(len(value)==len(required) and {x.get('id') for x in value}==set(required),'Review must assess every required check exactly once')
    for check in value:
        require(check.get('verdict') in {'pass','fail','not_applicable'},'Invalid check verdict')
        require(isinstance(check.get('reason'),str) and len(check['reason'].strip())>=20,'Check needs a specific reason')
        try:
            resolve(check)
        except EvidenceError as exc:
            raise ContractError('Review check has unsupported source evidence: '+str(exc)) from exc
    return value


def editorial_review(value,prose,required):
    require(isinstance(value,dict),'Editorial review must be an object')
    require(isinstance(value.get('issues'),list) and all(isinstance(x,dict) for x in value['issues']),'Editorial issues must be objects')
    value={**value,'issues':[dict(x) for x in value['issues']]}
    require(isinstance(value.get('checks'),list),'Bare pass/fail is not an editorial assessment')
    def resolve(check):
        require(check['verdict']!='not_applicable' or check['id'] in {'subplot_function','reference_application'},'This editorial check cannot be skipped')
        if check['verdict']!='not_applicable':
            bound=bind({'evidence_ids':check.get('evidence_ids')},prose)
            check['source_spans']=bound['evidence_spans']
    checks(value['checks'],required,resolve)
    for issue in value['issues']:
        require(issue.get('category') in required,'Issue category must be a requested editorial dimension')
        if 'evidence_ids' in issue:
            try:
                issue['quote']=bind(issue,prose)['evidence']
            except EvidenceError as exc:
                raise ContractError('Editorial issue has unsupported evidence: '+str(exc)) from exc
    value=review(value,prose)
    for check in value['checks']:
        require(check['verdict']!='fail' or any(i['category']==check['id'] for i in value['issues']),'A failed check needs an actionable matching issue')
    failed=any(c['verdict']=='fail' for c in value['checks'])
    require(not (value['pass'] and failed),'A failed editorial check cannot pass the gate')
    return value


def _path(document,path):
    require(isinstance(path,str) and bool(path),'Design check needs a source path')
    current=document
    for part in path.split('.'):
        if isinstance(current,list) and part.isdigit():
            require(int(part)<len(current),'Design path list index is absent');current=current[int(part)]
        else:
            require(isinstance(current,dict) and part in current,'Design path is absent: '+path);current=current[part]
    return current


def design_review(value,document,required=DESIGN_CHECKS):
    require(isinstance(value,dict) and type(value.get('pass')) is bool,'Invalid design review')
    checks(value.get('checks'),required,lambda c:_path(document,c.get('path')))
    require(all(c['verdict']!='not_applicable' for c in value['checks']),'Creative categories must be assessed, not skipped')
    require(isinstance(value.get('issues'),list),'Design review needs issues')
    for issue in value['issues']:
        require(isinstance(issue,dict) and issue.get('severity') in {'blocking','advisory'},'Invalid design issue')
        _path(document,issue.get('path'))
        for key in ['problem','fix','category']:
            require(isinstance(issue.get(key),str) and len(issue[key].strip())>0,'Design issue needs '+key)
    failed=any(c['verdict']=='fail' for c in value['checks']) or any(i['severity']=='blocking' for i in value['issues'])
    require(not (value['pass'] and failed),'Failed design checks cannot pass')
    return value


def rhetoric_signals(prose):
    patterns=[('instruction_leakage',r'(?i)\b(?:her|his|their) voice[^.!?\n]{0,80}\bconcrete observation\b','blocking'),
              ('redundant_explanation',r"(?i)\bIt wasn['’]t a question\.",'advisory'),
              ('automatic_significance',r'(?i)\b(?:everything changed|changed everything|she had to decide what was more valuable)\b','advisory'),
              ('stock_gesture',r'(?i)\b(?:breath hitch(?:ing)?|jaw tighten(?:ed|ing)?|heart hammering)\b','advisory')]
    return [{'category':category,'severity':severity,'quote':m.group(),'problem':'Concrete editorial signal requiring contextual assessment; not an authorship test.','fix':'Replace instruction leakage or redundant explanation with character-specific action or remove it.'}
            for category,pattern,severity in patterns for m in re.finditer(pattern,prose)]


def apply_signals(verdict,signals):
    result={**verdict,'issues':list(verdict['issues']),'signals':signals}
    for signal in signals:
        if signal['severity']=='blocking':
            result['issues'].append(signal)
            result['pass']=False
    return result


def merge_reviews(story,rhetoric):
    return {'pass':story['pass'] and rhetoric['pass'],
            'issues':story['issues']+rhetoric['issues'],
            'story_checks':story.get('checks',[]),'rhetoric_checks':rhetoric.get('checks',[])}


class ReviewBriefError(ContractError):
    """The assessment requires substantive reevaluation under the author brief."""


def validate_review_brief(value,req):
    form=req.get('pov','').lower()
    if 'no dialogue' not in form and 'no direct dialogue' not in form:return value
    for issue in value.get('issues',[]):
        fix=issue.get('fix','')
        if re.search(r'(?i)(?:^|[.!?]\s*)(?:add|insert|include|introduce)\b[^.!?]{0,50}\b(?:direct speech|quoted (?:speech|dialogue)|spoken dialogue)\b',fix):
            raise ReviewBriefError('Review contradicts the author form: direct dialogue is prohibited. Reassess the original prose for narrated offers, commitments, resistance and consequences; do not demand quoted speech or automatically approve the scene.')
    return value
