"""Explicit synthetic transport responses. Never a literary-quality demonstration."""
import json


def respond(role, packet, req):
    if role == 'architect':
        ids = [c['id'] for c in req['characters']]
        scenes = []
        for ch in range(1, req['chapters'] + 1):
            for sc in range(1, req['scenes_per_chapter'] + 1):
                scenes.append({'id': f'ch{ch:02}-sc{sc:02}', 'chapter': ch, 'pov': ids[0], 'participants': ids[:2],
                               'location': 'bell tower', 'time': f'day {ch}, interval {sc}', 'goal': 'inspect the bell mechanism',
                               'obstacle': 'access requires cooperation', 'intended_change': 'a practical decision changes the inspection'})
        return json.dumps({'title': req.get('title'), 'threads': ['bell repair', 'trust'], 'technique_stack': ['consequential choice'], 'scenes': scenes})
    if role in {'story_quality', 'memory_quality', 'chapter_quality'}:
        return json.dumps({'pass': True, 'issues': []})
    if role == 'memory':
        return json.dumps({'memories': [{'kind': 'event', 'text': 'Mara checked the tower latch.', 'evidence': 'Mara checked the tower latch.', 'known_by': ['mara']} ]})
    if role == 'character':
        return packet['character'].get('name', packet['character']['id']) + ' checks the nearest fastening.'
    if role == 'director':
        return 'Inspect the latch; ask for access; cooperate on a practical check.'
    if role == 'humanizer':
        return packet['prose']
    if role == 'writer':
        card = packet.get('scene', packet.get('context', {}).get('scene', {}))
        return (f'[FIXTURE {card.get("id", "repair")}: transport test only.]\n\nMara checked the tower latch. '
                'The hinge caught halfway. She put the lamp down before trying again.\n\n'
                '“Hold this,” she said.\n\nOren kept his hand on the rail. “Tell me what you are checking.”\n\n'
                '“Whether it opens from inside.”\n\nHe took the lamp. She eased the pin free, keeping it in her palm '
                'so it could not fall between the boards. Neither moved toward the stairs until she had replaced it.')
    return 'FIXTURE AUDIT: deterministic test responses establish file coordination only. No model or literary quality was tested.'
