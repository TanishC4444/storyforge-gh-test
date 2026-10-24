"""Small, cached SerpAPI search allowance with ordered credential failover."""
from __future__ import annotations
import hashlib
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
import time
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


class ProviderError(ValueError):
    pass


def safe_url(value):
    try:
        u = urlsplit(str(value))
        return str(value) if u.scheme in ('https', 'http') and u.hostname and not u.username else ''
    except ValueError:
        return ''


def request_json(url, payload=None, headers=None, timeout=60):
    """Never surface a request URL (SerpAPI puts credentials in its query)."""
    data = json.dumps(payload).encode() if payload is not None else None
    request = Request(url, data=data, headers=headers or {})
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except HTTPError as exc:
        raise ProviderError(f'Provider HTTP {exc.code}') from None
    except (URLError, TimeoutError, OSError, ValueError):
        raise ProviderError('Provider request failed or returned invalid JSON') from None


class Search:
    def __init__(self, folder, keys=None, daily_limit=10, plan_limit=2):
        self.keys = list(dict.fromkeys(keys if keys is not None else filter(None, [os.getenv('SERPAPI_API_KEY', ''), *os.getenv('SERPAPI_BACKUP_KEYS', '').split(',')])))
        self.keys = [k.strip() for k in self.keys if k.strip()]
        self.daily_limit = min(30, max(0, int(daily_limit)))
        self.plan_limit = min(3, max(0, int(plan_limit)))
        self.used = 0
        folder = Path(folder); folder.mkdir(parents=True, exist_ok=True)
        self.db = folder / 'search-cache.sqlite'
        with self.connect() as c:
            c.execute('CREATE TABLE IF NOT EXISTS cache (id TEXT PRIMARY KEY, expires REAL, body TEXT)')
            c.execute('CREATE TABLE IF NOT EXISTS attempts (at REAL, key_id TEXT)')
            c.execute('CREATE TABLE IF NOT EXISTS cooldown (key_id TEXT PRIMARY KEY, until REAL)')

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.db, timeout=20)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def reserve(self, key):
        fingerprint = hashlib.sha256(key.encode()).hexdigest()[:16]
        now = time.time()
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT until FROM cooldown WHERE key_id=?', (fingerprint,)).fetchone()
            if row and row[0] > now: return False
            used = c.execute('SELECT count(*) FROM attempts WHERE at>?', (now - 86400,)).fetchone()[0]
            if used >= self.daily_limit: raise ProviderError('Daily search allowance reached; cached research is still available')
            c.execute('INSERT INTO attempts VALUES (?,?)', (now, fingerprint))
        return True

    def search(self, query, purpose='location'):
        query = ' '.join(str(query).split())[:240]
        ident = hashlib.sha256(query.casefold().encode()).hexdigest()
        now = time.time()
        with self.connect() as c:
            row = c.execute('SELECT body FROM cache WHERE id=? AND expires>?', (ident, now)).fetchone()
        if row: return {**json.loads(row[0]), 'cached': True}
        if self.used >= self.plan_limit: raise ProviderError('Per-plan search allowance reached')
        if not self.keys: raise ProviderError('SerpAPI is not configured; add server-side search keys')
        self.used += 1
        for key in self.keys[:3]:
            if not self.reserve(key): continue
            params = {'engine':'google', 'q':query, 'api_key':key, 'hl':'en', 'num':5}
            try:
                body = request_json('https://serpapi.com/search.json?' + urlencode(params), timeout=35)
            except ProviderError as exc:
                if str(exc) in ('Provider HTTP 401', 'Provider HTTP 403', 'Provider HTTP 429'):
                    fingerprint = hashlib.sha256(key.encode()).hexdigest()[:16]
                    with self.connect() as c:
                        c.execute('INSERT OR REPLACE INTO cooldown VALUES (?,?)', (fingerprint, now + 3600))
                    continue
                raise
            if body.get('error'):
                error = str(body['error']).lower()
                if any(x in error for x in ('run out', 'limit', 'invalid api key', 'no searches')):
                    fingerprint = hashlib.sha256(key.encode()).hexdigest()[:16]
                    with self.connect() as c:
                        c.execute('INSERT OR REPLACE INTO cooldown VALUES (?,?)', (fingerprint, now + 3600))
                    continue
                # Empty results are a valid negative result: do not burn backup keys.
                if 'no results' not in error and 'hasn\'t returned any results' not in error:
                    raise ProviderError('Search provider could not complete this query')
            results = []
            for item in body.get('organic_results', [])[:5]:
                url = safe_url(item.get('link', ''))
                if url:
                    results.append({'title':str(item.get('title',''))[:300], 'url':url, 'snippet':str(item.get('snippet',''))[:1200]})
            result = {'query':query, 'purpose':purpose, 'results':results, 'retrieved_at':now, 'cached':False, 'evidence_level':'search_snippet_only'}
            with self.connect() as c:
                c.execute('INSERT OR REPLACE INTO cache VALUES (?,?,?)', (ident, now + (21600 if purpose == 'legal' else 86400), json.dumps(result)))
            return result
        raise ProviderError('Search keys unavailable or exhausted; cooldown is active. Use cached research or try later.')
