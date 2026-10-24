"""Reproducible chronology, ensemble, adaptation and recovery benchmarks."""
import copy,json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE='''At 18:00 Mara and Ivo Venn waited on the ferry quay. They were siblings. Mara held two single-use crossing tokens. Ivo's radio could send two more transmissions. Sera Holt arrived on foot from the archive after a ten-minute walk. She alone knew that the relief ledger's date had been erased.

Sera showed the ledger to both siblings and pointed at the erased date. Ivo transmitted its page number to the archive desk. One outbound transmission remained. Mara surrendered one token and took Sera across the harbor. Ivo remained on the quay. Mara had one token left.

At 18:20 Mara and Sera reached the council landing. Sera kept the ledger. She refused to accuse anyone until they could compare the original receipt. The erased date was evidence of alteration, not proof of who altered it. Ivo had not seen the council landing or heard this refusal.'''


def configure(req,slug,medium,words,count):
    r=copy.deepcopy(req);r.update(project_id='hard-'+slug,universe_id='hard-'+slug,title='Hard situation: '+slug,medium=medium,words_per_scene=words,chapters=count,scenes_per_chapter=1)
    r['scene_designs']=r['scene_designs'][:count]
    r['length_policy']['overflow']='advisory'
    r['length_policy']['policy']=f'{count} connected scenes, target {words} words each; at least {int(words*.8)}. Longer natural scenes are advisory. No filler or repeated discoveries.'
    r['pov']='Close third-person past tense, one focal character per scene.' if medium in {'book','short_story'} else 'Present-tense representable action and dialogue in the selected script medium.'
    r['execution_intent']['authorized']='User requested harder chronology, ensemble, same-canon adaptation and interruption/recovery tests.'
    r['execution_intent']['workflow']='Full separate-runner graph, full memory, strict approval; save incomplete work and use one bounded checkpoint retry.'
    r['performance']['stress_benchmark']=True
    return r


def build():
    screen=json.loads((ROOT/'examples/stress-screenplay.json').read_text())
    ensemble=json.loads((ROOT/'examples/stress-ensemble.json').read_text())
    cases=[]
    def write(slug,r,**extra):
        filename='hard-'+slug
        (ROOT/'examples'/f'{filename}.json').write_text(json.dumps(r,indent=2,ensure_ascii=False)+'\n')
        cases.append(dict(id=slug,request_file=filename,medium=r['medium'],words_per_scene=r['words_per_scene'],scenes=r['chapters'],cast=len(r['characters']),resume_case=None,**extra))

    r=configure(screen,'chronology','short_story',450,4)
    # Keep eight characters and 38 authored facts; distribute viewpoints rather
    # than pretending a narrator's knowledge belongs to everyone in the world.
    r['scene_designs']=copy.deepcopy(ensemble['scene_designs'])
    r['premise']='A harbor relief-fund mystery told out of chronological order: scene 1 at 18:00 today, scene 2 a flashback to yesterday at 16:00, scene 3 today at 18:20, scene 4 today at 18:40. Do not repeat a discovery. The past may reveal a cause to the reader without teaching absent characters. Resource counts in a flashback are historical, never a refill of the present. Invent an earned reversal from witnessed evidence.'
    times=['Today 18:00','Yesterday 16:00 — explicitly signal a flashback','Today 18:20 — explicitly return to the present','Today 18:40']
    povs=['c01','c03','c02','c01']
    for i,s in enumerate(r['scene_designs']):
        s['pov']=povs[i];s['participants']=list(dict.fromkeys([povs[i],*s['participants']]))
        s['participants']=[x for x in s['participants'] if x in {c['id'] for c in r['characters']}]
        s['time']=times[i];s['restrictions']+=' Reader knowledge does not become character knowledge. Yesterday events do not supersede today state.'
    r['scene_designs'][1].update(location='Public archive',setting='Public archive yesterday, before the present-day opening.',participants=['c03','c07'],dramatic_function='Reveal a concrete earlier action that changes the reader interpretation while remaining unknown to Mara and Ivo.',development='Sera and the clerk encounter an ambiguous alteration. This is an earlier event, not a later state update.',choice_and_consequence='Sera preserves evidence at a personal cost. Do not solve the whole episode in the flashback.')
    r['scene_designs'][2]['participants']=['c02','c05','c06']
    r['scene_designs'][3]['participants']=['c01','c02','c03','c07','c08']
    r['quality_contract']+=['Clearly distinguish story order from event chronology. Preserve present resource and lifecycle state across flashbacks.','No POV leakage: a reader-visible flashback grants no new knowledge to absent characters.']
    write('chronology',r,fresh_on_failure=True)

    r=configure(ensemble,'ensemble','book',750,4)
    r['quality_contract'].append('All sixteen characters retain stable identities and independent goals; only established participants act. Not every character needs dialogue in every scene.')
    write('ensemble',r,retry_timeout_minutes=30)

    # An authored immutable source is shared by both media. This tests adaptation
    # of the SAME events, not two independent stories with similar premises.
    for medium,words,slug in [('screenplay',400,'adapt-screenplay'),('comic_script',300,'adapt-comic')]:
        r=configure(screen,slug,medium,words,2)
        r['characters']=r['characters'][:6]
        ids={c['id'] for c in r['characters']}
        r['initial_facts']=[f for f in r['initial_facts'] if set(f['known_by'])<=ids|{'public'} and f.get('subject','c01') in ids]
        for f in r['initial_facts']:
            if f.get('fact_key')=='location:c02':f['text']='Ivo Venn begins at the Ferry quay.'
        for c in r['characters']:c['goal']='Enact this character’s role in the supplied source without adding new events or offstage knowledge.'
        r['premise']='Adapt the exact source episode below into TWO scenes in the selected medium. This is a retelling, NOT a continuation after its ending. Preserve events, causal order, token and transmission expenditure, sibling identity, witness knowledge and the unresolved culprit. Invent only performable/drawable connective texture. Scene 1 ends with departure; scene 2 ends at the council landing. No new climax that changes source events.\n\nAUTHOR SOURCE (authoritative):\n'+SOURCE
        r['adaptation'].update(strength=1,relationship='Exact adaptation of supplied author-owned source',preserve=['All source events, knowledge, resource costs, custody and chronology'],divergence='Presentation, dialogue texture and scene/panel division only.')
        r['chapter_contract'].update(arc='Preserve the supplied source causal arc.',ending='End with the unresolved receipt comparison at the council landing.')
        r['chapter_arcs']=['Disclose evidence and depart at a counted cost.','Arrive with persistent costs and unresolved attribution.']
        r['plot_design']={'central_question':'Can an alteration be pursued without turning suspicion into an unsupported accusation?','causal_dependencies':['Disclosure precedes Ivo transmission.','One token is spent before arrival.','The culprit remains unknown.'],'subplots':[{'id':'restraint','owner':'c03','question':'Will Sera distinguish evidence from accusation?','intersection':'She refuses to name a culprit without the receipt.','removal_cost':'The source ending loses its uncertainty.'}],'alternatives_and_costs':['Keep source costs and uncertainty.']}
        r['quality_contract']=['Follow selected medium formatting.','Preserve every explicit source event and character knowledge boundary; no invented culprit or new event to manufacture a climax.','Source events determine the ending; source fidelity takes precedence over generic climax and reversal preferences.','Two tokens become one; two outbound radio transmissions become one; Sera keeps the ledger; Ivo remains on the quay.']
        r['ending_tendency']='Faithfully preserve the source ending, including its uncertainty; do not resolve the culprit.'
        r['creative_freedom'].update(new_characters=False,character_deaths=False,flexible_pov=False)
        for i,s in enumerate(r['scene_designs']):
            s.update(pov='c01',participants=['c01','c02','c03'] if i==0 else ['c01','c03'],location='Ferry quay' if i==0 else 'Council landing',setting='The exact source setting.',time='Today 18:00' if i==0 else 'Today 18:20',dramatic_function=r['chapter_arcs'][i],development='Adapt only this part of the authoritative source; no extra mystery resolution.',restrictions='Keep source event order and resource counts. No unobserved knowledge, extra crossing or transmission.',choice_and_consequence=r['chapter_arcs'][i])
        r['world_rules'].append('The supplied AUTHOR SOURCE is the exact event contract; preserve its ending and uncertainty.')
        write(slug,r)

    r=configure(screen,'interruption','short_story',350,2)
    r['premise']='A small harbor heist: establish a contested relief-fund recovery plan in scene 1, then enact an earned costly reversal in scene 2. Preserve sibling identity, counted tokens and radio transmissions, custody, travel and private knowledge. Each scene progresses beyond the previous one.'
    write('interruption',r,recovery_probe=True)
    suite=dict(version=1,per_run_timeout_minutes=45,retry_timeout_minutes=20,poll_seconds=30,max_scene_retries=1,continue_on_unapproved=True,cases=cases,assessment=['source-bound full-memory verification','flashback chronology and POV isolation','sixteen-character ensemble','same-source adaptation across screenplay and comic','controlled interruption and unchanged approved-prefix recovery'],literary_assessment='Benchmark completion is separate from quality approval. Unresolved drafts remain needs_revision; they are never silently approved.')
    (ROOT/'examples/harder-suite.json').write_text(json.dumps(suite,indent=2)+'\n')
    return suite


if __name__=='__main__':print('Built',len(build()['cases']),'hard-situation cases.')
