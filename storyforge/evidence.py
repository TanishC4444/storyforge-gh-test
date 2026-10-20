"""Source-bound references: no fuzzy matching, paraphrase repair, or invented evidence."""
from __future__ import annotations
import hashlib
import re


class EvidenceError(ValueError):
    pass


def passages(prose):
    return [{'id': f'p{i:03}', 'text': match.group(), 'start': match.start(), 'end': match.end()}
            for i, match in enumerate(re.finditer(r'\S(?:.*?\S)?(?=\n\s*\n|\Z)', prose, re.S), 1)]


def payload(prose):
    return {'prose_sha256': hashlib.sha256(prose.encode()).hexdigest(),
            'evidence_passages': [{'id': p['id'], 'text': p['text']} for p in passages(prose)]}


def _normalized(text):
    chars, offsets = [], []
    replacements = {'“':'"', '”':'"', '‘':"'", '’':"'"}
    for i, ch in enumerate(text):
        if ch.isspace():
            if chars and chars[-1] == ' ':
                offsets[-1] = (offsets[-1][0], i + 1)
                continue
            mapped = ' '
        else:
            mapped = replacements.get(ch, ch)
        chars.append(mapped)
        offsets.append((i, i + 1))
    return ''.join(chars), offsets


def quote_span(quote, prose):
    if not isinstance(quote, str) or not quote.strip():
        raise EvidenceError('Evidence quotation is empty or not text')
    if quote in prose:
        start = prose.index(quote)
        return start, start + len(quote), 'exact'
    normalized, offsets = _normalized(prose)
    target, _ = _normalized(quote.strip())
    candidates = [(target, 'typography_or_whitespace')]
    if len(target) > 2 and target[0] == target[-1] and target[0] in {'"', "'"}:
        candidates.append((target[1:-1].strip(), 'outer_quote_wrapper'))
    for candidate, method in candidates:
        if not candidate:
            continue
        first = normalized.find(candidate)
        if first >= 0 and normalized.find(candidate, first + 1) < 0:
            return offsets[first][0], offsets[first + len(candidate) - 1][1], method
    raise EvidenceError('Quotation does not identify an exact source span; paraphrases and ambiguous normalized matches are rejected')


def bind(memory, prose):
    result = dict(memory)
    source_hash = hashlib.sha256(prose.encode()).hexdigest()
    if result.get('evidence_prose_sha256') not in (None, source_hash):
        raise EvidenceError('Evidence belongs to a different prose version')
    ids = result.get('evidence_ids')
    if ids is not None:
        if not isinstance(ids, list) or not 1 <= len(ids) <= 3 or not all(isinstance(x, str) for x in ids) or len(ids) != len(set(ids)):
            raise EvidenceError('evidence_ids must contain 1–3 distinct passage IDs')
        catalog = {p['id']: p for p in passages(prose)}
        if any(x not in catalog for x in ids):
            raise EvidenceError('Unknown evidence passage ID')
        selected = sorted((catalog[x] for x in ids), key=lambda p: p['start'])
        start, end = selected[0]['start'], selected[-1]['end']
        result['evidence_spans'] = [{'id': p['id'], 'start': p['start'], 'end': p['end']} for p in selected]
        method = 'passage_ids'
    else:
        quote = result.get('evidence')
        if not isinstance(quote, str) or len(quote.strip()) < 12:
            raise EvidenceError('Legacy quotation needs at least 12 characters; prefer evidence_ids')
        start, end, method = quote_span(quote, prose)
        result['evidence_spans'] = [{'start': start, 'end': end}]
    result['evidence'] = prose[start:end]
    result['evidence_match'] = method
    result['evidence_prose_sha256'] = source_hash
    return result
