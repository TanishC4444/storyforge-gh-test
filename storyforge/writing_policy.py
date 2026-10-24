"""The requested literary standard follows the input, for hosted and CPU writers."""
import json

PROSE_ROLES={'writer','writer_beat','humanizer','structural_editor','global_repair','seam','repair'}


def instructions(req,role):
    if role not in PROSE_ROLES:return ''
    brief={key:req.get(key) for key in ['pov','style','tone_mood','reader_experience','quality_contract','chapter_contract','adaptation','references','length_policy','words_per_scene']}
    from .media import instructions as medium_instructions,contract as medium_contract
    presentation=('Return only the requested script blocks; use headings, speaker cues and directions required by the medium.' if medium_contract(req)['script'] else 'Return the requested artifact only; scene prose has no title, preface, heading, craft commentary or analysis.')
    return medium_instructions(req)+'\n'+'''The application-owned writing brief below governs the prose on every provider and local model. Develop actual action, resistance, a consequential choice and its aftermath; do not paraphrase the outline into plot summary. Specific things done, exchanged, withheld or lost must bear the emotional burden. Do not announce a 'new development', repeat the price of a decision in successive paragraphs, or append the central question as an explanatory moral.
Realize the requested stylistic influence through narrative technique, syntax, rhythm, imagery and social imagination, rather than borrowing recognizable translation wording or adding generic ornate vocabulary. In an ancient epic brief, honor, supplication, reciprocal obligation, labor, mortal vulnerability and earned extended comparison may shape action only as the supplied input requests. Other briefs retain their own register. Do not impose epic language on unrelated inputs.
Maintain canon, chronology, custody, focal viewpoint and private knowledge. For scarce resources, preserve the exact named pool and custodian through acquisition, transfer and expenditure; do not invent an extra reserve to escape an established constraint. Continue consequences rather than repeating a completed confrontation or revelation. Keep narrative tense stable outside dialogue. Unless the author explicitly requests metafiction, do not describe an event as a planted clue, plot twist or narrative beat in the story voice. Do not convert a planned revelation into an event or knowledge already acquired. Obey no-dialogue and other form restrictions exactly. '''+presentation+''' Before returning, revise the most redundant explanation and most interchangeable image without padding or inventing facts.
Application-owned literary brief: '''+json.dumps(brief,ensure_ascii=False,separators=(',',':'))
