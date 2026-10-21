"""One source read, two complete review rubrics; no quality checks are dropped."""
from pathlib import Path
from . import contracts
from .editorial import STORY_CHECKS,RHETORIC_CHECKS,editorial_review,apply_signals,rhetoric_signals
from .evidence import payload
from .coordinator import compact
from .brief import controls
from .inference import ROOT
from .storage import save
from .retrieval import application_packet


def review(executor,req,state,card,prose,out):
    required=STORY_CHECKS+RHETORIC_CHECKS
    from .canon import working
    packet={**payload(prose),'required_checks':required,'scene':card,
            'creative_controls':controls(req),'world_rules':req['world_rules'],
            'required_form':{'pov':req.get('pov'),'must_avoid':req['must_avoid']},
            'characters':[{k:c.get(k) for k in ['id','goal','arc','contradiction']} for c in req['characters'] if c['id'] in card['participants']],
            'current_author_state':working(state,query=str(card)),
            'prior_scene':state['accepted'][-1]['prose'][-2000:] if state['accepted'] else '',
            'reference_uses':card.get('reference_uses',[]),
            'reference_mechanisms':application_packet(req,state['retrieval'],'story_quality',card['id'])}
    def validate(value):return editorial_review(value,prose,required)
    result=executor.call('story_quality',packet,
        'Assess all story and rhetoric checks against this exact prose. Each check needs one specific sentence (20–110 characters) and source IDs. Narrated negotiation satisfies dialogue_tactics when dialogue is prohibited. Report concrete faults without an issue quota. Do not repeat the brief or summarize the plot.',
        tokens=2800,validator=validate,
        skill=(ROOT/'skills/story_quality.md').read_text()+'\n'+(ROOT/'skills/rhetoric_quality.md').read_text())
    for name,checks in [('story',STORY_CHECKS),('rhetoric',RHETORIC_CHECKS)]:
        if result.get('unverified'):verdict=result
        else:
            verdict={'checks':[c for c in result['checks'] if c['id'] in checks],
                     'issues':[i for i in result['issues'] if i['category'] in checks]}
            verdict['pass']=not any(c['verdict']=='fail' for c in verdict['checks']) and not any(i['severity']=='blocking' for i in verdict['issues'])
            verdict=editorial_review(verdict,prose,checks)
            if name=='rhetoric':verdict=apply_signals(verdict,rhetoric_signals(prose))
        save(Path(out)/name/'review.json',verdict)
    return result
