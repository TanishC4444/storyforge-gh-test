"""Expand main-line corpus records with Gemini-drafted story detail.

Fills summary, genre, key ideas, characters, plot, subplots, tone, sensory cues
and adaptability on top-level works. Resumable: records already enriched are
skipped, and progress is saved after every batch. Output stays marked as a
model draft in provenance, like the rest of the corpus.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from rag.embeddings import api_key
from storyforge.hosted import BASE, MODELS

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / 'data/literary-corpus.json'
MODEL = MODELS['flash']
ENRICHMENT_VERSION = 'story-detail-v1'
LIMITS = {'summary': 900, 'plot_context': 700, 'tone_mood': 200, 'adaptability': 400}

SYSTEM = """You are a literary reference editor expanding a retrieval corpus of classical stories.
For each record, describe the best-known, most widely read version of that story (name the version
when several exist, e.g. Grimm vs Perrault). Stay faithful to the source: never invent events,
characters or endings. If a detail is uncertain or varies between versions, say so briefly instead
of guessing. Write plain, specific English for a writer looking for story material. Keep each
summary to 3-5 sentences that cover beginning, turn and ending."""

ITEM = {
    'type': 'object',
    'properties': {
        'id': {'type': 'string'},
        'summary': {'type': 'string', 'description': '3-5 sentence synopsis of the main plot, including the ending.'},
        'genre': {'type': 'array', 'items': {'type': 'string'}, 'description': '1-4 genre labels.'},
        'key_ideas': {'type': 'array', 'items': {'type': 'string'}, 'description': '3-5 central ideas or morals, one short sentence each.'},
        'main_characters': {'type': 'array', 'items': {'type': 'string'}, 'description': 'Up to 6 entries, "Name: role".'},
        'plot_context': {'type': 'string', 'description': 'Setting, situation and stakes at the start.'},
        'subplot_threads': {'type': 'array', 'items': {'type': 'string'}, 'description': '0-5 secondary threads or embedded episodes.'},
        'tone_mood': {'type': 'string'},
        'sensory_cues': {'type': 'array', 'items': {'type': 'string'}, 'description': 'Up to 5 concrete images or sensory details that appear in the source.'},
        'adaptability': {'type': 'string', 'description': 'How the story mechanism transfers to new settings or genres.'},
        'version_note': {'type': 'string', 'description': 'Which version this follows and any major variants; empty if single version.'},
    },
    'required': ['id', 'summary', 'genre', 'key_ideas', 'main_characters', 'plot_context',
                 'subplot_threads', 'tone_mood', 'sensory_cues', 'adaptability', 'version_note'],
}
SCHEMA = {'type': 'object', 'properties': {'records': {'type': 'array', 'items': ITEM}}, 'required': ['records']}


def prompt_for(batch: list[dict]) -> str:
    brief = [{k: r.get(k) for k in ['id', 'title', 'collection', 'attribution', 'literary_analysis', 'notes']} for r in batch]
    return 'Expand each record. Return exactly one result per id, in the same order.\n' + json.dumps(brief, ensure_ascii=False, indent=1)


def generate(batch: list[dict], key: str, attempts: int = 6) -> list[dict]:
    body = {
        'systemInstruction': {'parts': [{'text': SYSTEM}]},
        'contents': [{'role': 'user', 'parts': [{'text': prompt_for(batch)}]}],
        'generationConfig': {'responseMimeType': 'application/json', 'responseJsonSchema': SCHEMA,
                             'temperature': 0.2, 'maxOutputTokens': 16384,
                             'thinkingConfig': {'thinkingLevel': 'low'}},
    }
    request = urllib.request.Request(BASE + MODEL + ':generateContent', data=json.dumps(body).encode(),
                                     headers={'x-goog-api-key': key, 'Content-Type': 'application/json'})
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                result = json.load(response)
            candidate = result['candidates'][0]
            if candidate.get('finishReason') != 'STOP':
                raise ValueError(f"Generation stopped early: {candidate.get('finishReason')}")
            return json.loads(candidate['content']['parts'][0]['text'])['records']
        except urllib.error.HTTPError as exc:
            # Never surface provider messages; they can echo request details.
            if exc.code not in {429, 500, 502, 503, 504} or attempt == attempts - 1:
                raise RuntimeError(f'Gemini generation failed: HTTP {exc.code}') from None
            time.sleep(min(90, 10 * 2 ** attempt))
    raise RuntimeError('Gemini generation failed.')


def clean_list(value, limit: int) -> list[str]:
    return [str(v).strip() for v in (value or []) if str(v).strip()][:limit]


def apply(record: dict, item: dict) -> None:
    for field, limit in LIMITS.items():
        if len(item[field]) > limit:
            item[field] = item[field][:limit].rsplit(' ', 1)[0] + '…'
    if len(item['summary'].split()) < 25:
        raise ValueError(f"{record['id']}: summary too short")
    record['summary'] = item['summary'].strip()
    record['genre'] = clean_list(item['genre'], 4)
    record['key_ideas'] = clean_list(item['key_ideas'], 5)
    record['main_characters'] = clean_list(item['main_characters'], 6)
    record['plot'] = {'context': item['plot_context'].strip()}
    record['subplots'] = {'threads': clean_list(item['subplot_threads'], 5)}
    record['tone_mood'] = item['tone_mood'].strip()
    record['detail_and_sensory'] = {
        'documented_cues': clean_list(item['sensory_cues'], 5),
        'coverage': 'Model-drafted from general knowledge of the best-known version; verify before quoting.',
    }
    record['adaptability'] = item['adaptability'].strip()
    if item['version_note'].strip():
        record.setdefault('references', {})['version_notes'] = item['version_note'].strip()
    record['provenance']['enrichment'] = {
        'version': ENRICHMENT_VERSION, 'model': MODEL, 'verification_status': 'model_knowledge_draft',
        'date': datetime.date.today().isoformat(),
    }


def save(corpus: dict) -> None:
    CORPUS.write_text(json.dumps(corpus, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=0, help='Enrich at most this many records (0 = all).')
    parser.add_argument('--batch', type=int, default=5)
    parser.add_argument('--pause', type=float, default=float(os.getenv('ENRICH_PAUSE_SECONDS', '15')))
    args = parser.parse_args()
    corpus = json.loads(CORPUS.read_text(encoding='utf-8'))
    corpus['record_field_notes'].update({
        'summary': 'Model-drafted synopsis of the best-known version, including the ending.',
        'genre': 'Short genre labels.',
        'key_ideas': 'Central ideas or morals, one sentence each.',
        'main_characters': 'Principal characters as "Name: role".',
        'plot.context': 'Setting, situation and stakes at the start.',
        'subplots.threads': 'Secondary threads or embedded episodes.',
        'tone_mood': 'Overall tone and mood.',
        'detail_and_sensory': 'Concrete images from the source plus a coverage caveat.',
        'adaptability': 'How the mechanism transfers to new settings.',
        'references.version_notes': 'Which version the enrichment follows and notable variants.',
        'provenance.enrichment': 'Records which model and enrichment version drafted the fields above.',
    })
    pending =[r for r in corpus['records'] if r['parent_id'] is None
               and r['provenance'].get('enrichment', {}).get('version') != ENRICHMENT_VERSION]
    if args.limit:
        pending = pending[:args.limit]
    print(f'{len(pending)} main-line records to enrich with {MODEL}.', flush=True)
    key = api_key()
    done = 0
    for start in range(0, len(pending), args.batch):
        batch = pending[start:start + args.batch]
        items = {item['id']: item for item in generate(batch, key)}
        for record in batch:
            if record['id'] not in items:
                raise ValueError(f"{record['id']}: missing from model output")
            apply(record, items[record['id']])
        save(corpus)
        done += len(batch)
        print(f'Enriched {done}/{len(pending)}: ' + ', '.join(r['title'] for r in batch), flush=True)
        if start + args.batch < len(pending):
            time.sleep(args.pause)
    print(f'Done: {done} records enriched.', flush=True)


if __name__ == '__main__':
    main()
