"""Story-aware soundtrack planning, local soundscapes and Vultr streaming."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import struct
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from .storage import save

BASE = 'https://api.vultrinference.com/v1'


def context(folder):
    """Read only narrative artifacts; never sweep logs, environment or credentials."""
    root = Path(folder)
    sources = []
    candidates = [root / name for name in ('request.json', 'state.json', 'story.txt', 'FINAL_STORY.txt', 'PROVISIONAL_STORY.txt', 'PARTIAL_DRAFT.txt', 'characters.json', 'world.json', 'memory.json', 'plan.json')]
    candidates += sorted((root / 'scenes').glob('*.txt'))
    for path in candidates:
        if path.is_file():
            value = path.read_text(encoding='utf-8')
            if path.suffix == '.json':
                obj = json.loads(value)
                # State contains accepted writing, canon and memories, not provider logs.
                if path.name == 'state.json':
                    obj = {k: obj[k] for k in ('accepted', 'memories', 'plan', 'canon') if k in obj}
                if path.name == 'request.json':
                    obj = {k: obj[k] for k in ('title', 'premise', 'genre', 'tone_mood', 'characters', 'world_rules', 'initial_facts', 'locations', 'scene_seeds', 'chapter_arcs', 'sensory_detail') if k in obj}
                value = json.dumps(obj, ensure_ascii=False)
            sources.append({'file': str(path.relative_to(root)), 'text': value})
    if not sources:
        raise ValueError('No story artifacts found. Select a story run folder containing request.json or story.txt.')
    return sources


def plan(folder, mode='ambience', direction=''):
    if mode not in ('ambience', 'score', 'song'):
        raise ValueError('Choose ambience, score or song')
    sources = context(folder)
    # Allocate room to every artifact rather than dropping characters behind prose.
    allowance = max(200, 4800 // len(sources))
    excerpts = '\n'.join(x['file'] + ': ' + x['text'][:allowance] for x in sources)[:4800]
    text = ' '.join(x['text'] for x in sources).lower() + ' ' + direction.lower()
    layers = [name for name, pattern in (
        ('water', r'harbou?r|ocean|sea\b|wave|river|ship|rain|storm'),
        ('wind', r'wind|storm|mountain|forest|desert|cold'),
        ('rumble', r'horror|fear|dread|dark|danger|battle|thunder|tension'),
        ('fire', r'fire|flame|hearth|camp|burn')) if re.search(pattern, text)] or ['wind']
    instruction = {'ambience': 'Environmental soundscape. No melody, singing, speech or musical instruments.',
                   'score': 'Instrumental dramatic underscore. No vocals or spoken narration.',
                   'song': 'A song inspired by this story and its characters.'}[mode]
    return {'mode': mode, 'layers': layers, 'sources': [x['file'] for x in sources],
            'prompt': (instruction + '\nAuthor direction: ' + direction[:400] + '\nStory, characters and world:\n' + excerpts)[:5900]}


def wav_stream(cue, seconds=60, rate=16000):
    """Finite PCM WAV streamed in small blocks; no full-track buffering."""
    count = rate * seconds
    yield b'RIFF' + struct.pack('<I', 36 + count * 2) + b'WAVEfmt ' + struct.pack('<IHHIIHH', 16, 1, 1, rate, rate * 2, 2, 16) + b'data' + struct.pack('<I', count * 2)
    rng = random.Random(hashlib.sha256(cue['prompt'].encode()).digest())
    low = 0.0
    layers = cue['layers']
    base = 55 + int(hashlib.sha256(cue['prompt'].encode()).hexdigest()[:2], 16) % 30
    for start in range(0, count, 2048):
        block = bytearray()
        for i in range(start, min(start + 2048, count)):
            t = i / rate
            noise = rng.uniform(-1, 1)
            low = .985 * low + .015 * noise
            value = 0.0
            if 'wind' in layers: value += low * (1.5 + math.sin(t * .31))
            if 'water' in layers: value += noise * (.05 + .07 * (1 + math.sin(t * .7)))
            if 'rumble' in layers: value += low * 2.5
            if 'fire' in layers: value += noise * (.5 if rng.random() < .012 else .025)
            if cue['mode'] == 'score':
                # A restrained evolving drone; the context chooses its tonal center.
                value += .12 * math.sin(2 * math.pi * base * t) + .07 * math.sin(2 * math.pi * base * 1.5 * t)
            fade = min(1, t / 2, (seconds - t) / 2)
            block.extend(struct.pack('<h', int(max(-1, min(1, value * fade)) * 20000)))
        yield bytes(block)


class Vultr:
    def __init__(self):
        self.key = os.environ.get('VULTR_INFERENCE_API_KEY')
        if not self.key:
            raise ValueError('Set VULTR_INFERENCE_API_KEY in the server environment for Vultr generation.')

    def open(self, path, payload=None):
        if not path.startswith('/music') or '..' in path:
            raise ValueError('Invalid music route')
        req = Request(BASE + path, data=json.dumps(payload).encode() if payload is not None else None,
                      headers={'Authorization': 'Bearer ' + self.key, 'Content-Type': 'application/json'})
        try:
            return urlopen(req, timeout=60)
        except HTTPError as exc:
            raise ValueError(f'Vultr returned HTTP {exc.code}; check inference key, model capabilities and account access.') from None
        except URLError:
            raise ValueError('Cannot reach Vultr inference.') from None

    def json(self, path, payload=None):
        with self.open(path, payload) as response:
            return json.load(response)

    def create(self, cue, model, seconds, lyrics=''):
        models = self.json('/music/models')['data']
        spec = next((m for m in models if m['id'] == model), None)
        if spec is None: raise ValueError('Select an available Vultr music model.')
        if cue['mode'] == 'ambience': raise ValueError('Use local ambience for environmental soundtracks.')
        if cue['mode'] == 'score':
            # Section tags satisfy the model's lyrics field without supplying sung words.
            lyrics = '[Instrumental]\n[Intro]\n[Instrumental]\n[Bridge]\n[Instrumental]\n[Outro]'
            cue = dict(cue, prompt='Cinematic orchestral film score. Instrumental throughout; no singing, choir, speech or vocals. Develop an emotional theme from sparse strings through dramatic percussion and brass into a restrained resolution.\n' + cue['prompt'])
        if spec.get('lyrics') == 'required' and not lyrics.strip():
            raise ValueError('This model requires lyrics. Supply lyrics or choose local ambience.')
        limits = spec.get('duration', {})
        if not limits.get('min', 1) <= seconds <= limits.get('max', 360):
            raise ValueError('Duration outside selected model limits.')
        return self.json('/music', {'model': model, 'prompt': cue['prompt'][:spec.get('prompt_max_length', 6000)], 'duration': seconds, 'lyrics': lyrics, 'response_format': 'mp3'})


PAGE = '''<!doctype html><meta charset="utf-8"><title>StoryForge soundtracks</title>
<style>body{font:18px system-ui;background:#101725;color:#e8edf5;max-width:850px;margin:50px auto;padding:20px}button,select,input,textarea{font:inherit;padding:10px;margin:8px 0;box-sizing:border-box}textarea{width:100%;height:100px}audio{width:100%}pre{white-space:pre-wrap;font-size:14px}button{cursor:pointer}</style>
<h1>StoryForge soundtracks</h1><p>Build sound from the story, characters and world in this run folder.</p>
<label>Soundtrack type <select id="mode"><option value="ambience">Ambient soundscape Â· local streaming</option><option value="score">Instrumental drone score Â· local streaming</option><option value="song">Song Â· Vultr</option></select></label>
<textarea id="direction" placeholder="Sound direction: distant surf, wind, mounting dreadâ€¦"></textarea>
<label>Duration in seconds <input id="seconds" type="number" min="5" max="360" value="60"></label>
<input id="model" value="minimax-music3" placeholder="Vultr model ID (for songs)"><textarea id="lyrics" placeholder="Lyrics (only for songs)"></textarea>
<button onclick="generate()">Generate soundtrack</button><p id="status" role="status"></p><audio id="player" controls></audio><pre id="details"></pre>
<script>
const $=id=>document.getElementById(id);let timer;
async function api(path,data){const r=await fetch(path,data?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)}:{});const v=await r.json();if(!r.ok)throw Error(v.error);return v}
async function poll(id){try{const j=await api('/job/'+id);$('status').textContent=j.status+' Â· '+(j.progress||0)+'%';if(j.stream_url&&!$('player').getAttribute('src'))$('player').src='/audio/'+id+'/stream';if(j.status==='completed'){if(!$('player').getAttribute('src'))$('player').src='/audio/'+id+'/content';return}if(['failed','cancelled','expired'].includes(j.status))throw Error(j.error||j.status);timer=setTimeout(()=>poll(id),3000)}catch(e){$('status').textContent=e.message}}
async function generate(){clearTimeout(timer);$('player').pause();$('player').removeAttribute('src');$('player').load();$('status').textContent='Preparingâ€¦';try{const v=await api('/generate',{mode:$('mode').value,direction:$('direction').value,seconds:Number($('seconds').value),model:$('model').value,lyrics:$('lyrics').value});$('details').textContent=v.cue.prompt+'\\nSources: '+v.cue.sources.join(', ');if(v.local){$('player').src='/ambience/'+v.local;$('status').textContent='Soundscape ready Â· play to stream'}else{poll(v.job.id)}}catch(e){$('status').textContent=e.message}}
</script>'''


def serve(folder, port=8765):
    root = Path(folder).resolve()
    context(root)  # Fail before opening a server if no story is available.
    cues = {}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def reply(self, value, code=200):
            raw = json.dumps(value).encode()
            self.send_response(code); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(raw))); self.end_headers(); self.wfile.write(raw)
        def do_POST(self):
            if self.path != '/generate': self.reply({'error': 'Not found'}, 404); return
            # Only same-origin browser requests may start billable jobs.
            if (self.headers.get('Host') != f'127.0.0.1:{self.server.server_port}'
                    or self.headers.get('Content-Type', '').split(';')[0] != 'application/json'
                    or self.headers.get('Origin') not in (None, f'http://127.0.0.1:{self.server.server_port}')):
                self.reply({'error': 'Origin rejected'}, 403); return
            try:
                length = int(self.headers.get('Content-Length', 0))
                if not 0 < length <= 32000: raise ValueError('Invalid request size')
                data = json.loads(self.rfile.read(length))
                seconds = data.get('seconds', 60)
                if type(seconds) is not int or not 5 <= seconds <= 360: raise ValueError('Duration must be 5â€“360 seconds')
                cue = plan(root, data.get('mode', 'ambience'), str(data.get('direction', '')))
                if cue['mode'] == 'ambience':
                    ident = hashlib.sha256(json.dumps([cue, seconds]).encode()).hexdigest()[:24]
                    cues[ident] = (cue, seconds)
                    save(root / 'soundtracks' / (ident + '.json'), {'cue': cue, 'seconds': seconds, 'engine': 'local-procedural'})
                    if len(cues) > 100: cues.pop(next(iter(cues)))
                    self.reply({'cue': cue, 'local': ident})
                else:
                    job = Vultr().create(cue, data.get('model'), seconds, data.get('lyrics', ''))
                    save(root / 'soundtracks' / (job['id'] + '.json'), {'cue': cue, 'job': job})
                    self.reply({'cue': cue, 'job': job})
            except (ValueError, OSError, KeyError, TypeError) as exc: self.reply({'error': str(exc)}, 400)
        def do_GET(self):
            if self.path == '/':
                raw = PAGE.encode(); self.send_response(200); self.send_header('Content-Type', 'text/html; charset=utf-8'); self.end_headers(); self.wfile.write(raw); return
            streaming_started = False
            try:
                if self.path.startswith('/ambience/'):
                    cue, seconds = cues[self.path.split('/')[-1]]
                    self.send_response(200); self.send_header('Content-Type', 'audio/wav'); self.send_header('Content-Length', str(44 + 32000 * seconds)); self.end_headers()
                    streaming_started = True
                    for block in wav_stream(cue, seconds): self.wfile.write(block)
                elif re.fullmatch(r'/job/music_[a-f0-9]{24}', self.path):
                    self.reply(Vultr().json('/music/' + self.path.split('/')[-1]))
                elif re.fullmatch(r'/audio/music_[a-f0-9]{24}/(stream|content)', self.path):
                    _, _, ident, action = self.path.split('/')
                    with Vultr().open('/music/' + ident + '/' + action) as response:
                        self.send_response(200); self.send_header('Content-Type', response.headers.get('Content-Type', 'audio/wav')); self.end_headers()
                        streaming_started = True
                        while block := response.read(8192): self.wfile.write(block)
                else: self.reply({'error': 'Not found'}, 404)
            except (BrokenPipeError, ConnectionResetError): pass
            except (ValueError, OSError, KeyError) as exc:
                if not self.wfile.closed:
                    # A streaming failure closes the connection; never append JSON to audio.
                    if not streaming_started: self.reply({'error': str(exc)}, 400)
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    print(f'StoryForge soundtracks: http://127.0.0.1:{server.server_port}', flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()


def discover_stories(root):
    """Find exported or active runs without selecting fixture/example data."""
    root = Path(root).resolve()
    markers = ('request.json', 'story.txt', 'FINAL_STORY.txt', 'PROVISIONAL_STORY.txt', 'PARTIAL_DRAFT.txt')
    found = set()
    if any((root / name).is_file() for name in markers):
        found.add(root)
    for parent in (root / 'outputs', root / 'runs'):
        if parent.is_dir():
            for name in markers:
                found.update(path.parent for path in parent.rglob(name))
    return sorted(found)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--story', type=Path, help='Story run folder; auto-selects when exactly one is available')
    parser.add_argument('--list-stories', action='store_true', help='List available story folders and exit')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    available = discover_stories(Path.cwd())
    if args.list_stories:
        print('\n'.join(str(path) for path in available) or 'No story folders found under outputs/ or runs/.')
        return
    story = args.story
    if story is None:
        if len(available) == 1:
            story = available[0]
        elif available:
            parser.error('Multiple stories found. Select one with --story:\n' + '\n'.join(str(path) for path in available))
        else:
            parser.error('No stories found. Use --story with a folder containing request.json or exported story text.')
    try:
        context(story)
        print(f'Using story: {story.resolve()}', flush=True)
        serve(story, args.port)
    except (ValueError, OSError) as exc:
        choices = '\nAvailable story folders:\n' + '\n'.join(str(path) for path in available) if available else ''
        parser.exit(1, f'Soundtracks: {exc}\nRequested folder: {story.resolve()}{choices}\n')

if __name__ == '__main__': main()
