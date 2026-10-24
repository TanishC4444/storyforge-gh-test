"""Server settings, read once from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DEFAULT_ORIGINS = (
    'http://localhost:5173',
    'http://localhost:8080',
    'http://127.0.0.1:8080',
    'https://tanishc4444.github.io',
)


@dataclass(frozen=True)
class Settings:
    # Repository whose workflows are dispatched and whose runs are read.
    repo: str = 'TanishC4444/storyforge-gh-test'
    # Git ref the workflows are dispatched on.
    ref: str = 'main'
    # When true, the bearer token "demo" serves bundled sample data instead of GitHub.
    allow_demo: bool = True
    cors_origins: tuple[str, ...] = DEFAULT_ORIGINS
    github_api: str = 'https://api.github.com'
    # Downloaded artifact zips, keyed by artifact ID. Artifacts are immutable once uploaded.
    cache_dir: Path = field(default_factory=lambda: ROOT / 'runs' / 'api-cache')
    examples_dir: Path = field(default_factory=lambda: ROOT / 'examples')
    # Seconds between GitHub polls in the run event stream.
    poll_seconds: float = 15.0
    # Event streams close after this long; clients reconnect.
    stream_seconds: float = 1800.0


def _flag(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}


@lru_cache
def get_settings() -> Settings:
    defaults = Settings()
    origins = os.environ.get('STORYFORGE_CORS_ORIGINS')
    return Settings(
        repo=os.environ.get('STORYFORGE_REPO', defaults.repo),
        ref=os.environ.get('STORYFORGE_REF', defaults.ref),
        allow_demo=_flag('STORYFORGE_ALLOW_DEMO', defaults.allow_demo),
        cors_origins=tuple(o.strip() for o in origins.split(',') if o.strip()) if origins else defaults.cors_origins,
        github_api=os.environ.get('STORYFORGE_GITHUB_API', defaults.github_api).rstrip('/'),
        cache_dir=Path(os.environ['STORYFORGE_CACHE_DIR']) if os.environ.get('STORYFORGE_CACHE_DIR') else defaults.cache_dir,
        poll_seconds=float(os.environ.get('STORYFORGE_POLL_SECONDS', defaults.poll_seconds)),
    )
