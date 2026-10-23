"""Fast application-owned medium selection; no prompt-refinement model call."""
import re

PROFILES={
 'book':{'label':'novel','script':False,'format':'Developed prose with viewpoint, interiority, sensory detail and chapter progression. Dialogue follows the author brief.'},
 'short_story':{'label':'short story','script':False,'format':'Concentrated prose scenes with a consequential arc; avoid padding and novel-scale exposition.'},
 'stage_play':{'label':'stage play','script':True,'format':'A performable theatre script: ACT/SCENE heading at the scene opening, concise stage directions, character names as speaker cues and playable dialogue. Show thoughts through speech, silence and physical behavior; no novel-style omniscient interiority. Respect staging and entrances/exits.'},
 'screenplay':{'label':'screenplay','script':True,'format':'Screenplay format: INT./EXT. scene heading, present-tense visible action, uppercase character cues and dialogue. No unfilmable internal narration or unsolicited camera-shot list.'},
 'audio_drama':{'label':'audio drama','script':True,'format':'Audio script: scene label, character cues, dialogue and purposeful SOUND/MUSIC cues. Establish space and action audibly; do not rely on unseen gestures or prose narration unless an authorized narrator exists.'},
 'comic_script':{'label':'comic script','script':True,'format':'Comic script: numbered PAGE/PANEL blocks, concise drawable action, character dialogue and captions where appropriate. Maintain panel order, visual continuity and readable speech volume.'}
}
ALIASES={'novel':'book','novella':'book','prose':'short_story','prose fiction':'short_story','short story':'short_story','shortstory':'short_story','play':'stage_play','theater':'stage_play','theatre':'stage_play','theater play':'stage_play','theatre play':'stage_play','stage play':'stage_play','script':'stage_play','film':'screenplay','film script':'screenplay','movie script':'screenplay','audio drama':'audio_drama','radio play':'audio_drama','comic':'comic_script','comic script':'comic_script','graphic novel':'comic_script'}


def choose(req,require):
    supplied=req.get('medium','auto');raw=str(supplied).strip().lower();canonical=ALIASES.get(raw,raw)
    method='explicit_medium'
    if raw in {'auto',''}:
        prompt=req.get('premise','').lower();method='prompt_medium_detection'
        rules=[('screenplay',r'\b(screenplay|film script|movie script)\b'),('audio_drama',r'\b(audio drama|radio play|audio script)\b'),('comic_script',r'\b(comic script|graphic novel|comic book)\b'),('stage_play',r'\b(stage play|theat(?:er|re)(?: play| script)?|play script)\b'),('book',r'\b(novel|novella)\b')]
        canonical=next((name for name,pattern in rules if re.search(pattern,prompt)),'short_story')
    require(canonical in PROFILES,'Unsupported medium; use book, short_story, stage_play, screenplay, audio_drama or comic_script')
    req['medium']=canonical
    req.setdefault('medium_decision',{'method':method,'selected':canonical,'model_calls':0})
    return req


def contract(req):
    medium=ALIASES.get(str(req.get('medium','short_story')).lower(),req.get('medium','short_story'))
    profile=PROFILES.get(medium,PROFILES['short_story'])
    return {'medium':medium,**profile,'precedence':'The chosen medium governs presentation. Explicit author constraints still govern content; a deliberately silent script remains a script.'}


def instructions(req):
    spec=contract(req)
    return 'MEDIUM CONTRACT: '+spec['label']+'. '+spec['format']+' Only the first writing batch supplies the scene heading; later batches continue without repeating headings or earlier action. Use the requested scene/act/chapter numbering.'
