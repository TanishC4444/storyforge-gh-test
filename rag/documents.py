from __future__ import annotations
from typing import Any


def flatten(value: Any) -> str:
    if value is None: return ""
    if isinstance(value, (str, int, float, bool)): return str(value)
    if isinstance(value, list): return ", ".join(flatten(v) for v in value if v is not None)
    if isinstance(value, dict): return "; ".join(f"{k}: {flatten(v)}" for k, v in value.items())
    return ""


def location_text(location: Any) -> str | None:
    return flatten(location).strip() or None


def document_text(record: dict[str, Any]) -> str:
    """Build one standalone retrieval document; both ingestion entry points use this.

    Keep summaries and natural-language keywords in semantic and full-text content.
    Store the complete record separately as metadata, including scoped references.
    Avoid repeating the synopsis through story, plot, and summary fields.
    """
    prompt = record.get("prompt_refinement") or {}
    plot = record.get("plot") or {}
    subplots = record.get("subplots") or {}
    sensory = record.get("detail_and_sensory") or {}
    references = record.get("references") or {}
    fields = {
        "Title": record.get("title"),
        "Source work": references.get("work_title"),
        "Attribution": record.get("attribution"),
        "Collection": record.get("collection"),
        "Location": location_text(record.get("location")),
        "Summary": record.get("summary"),
        "Keywords": record.get("keywords"),
        "Tags": record.get("tags"),
        "Genre": record.get("genre"),
        "Key ideas": record.get("key_ideas"),
        "Main characters": record.get("main_characters"),
        "Plot context": plot.get("context"),
        "Subplots and selected constituent threads": subplots.get("threads"),
        "Tone and mood": record.get("tone_mood"),
        "Themes": record.get("themes"),
        "Theme keywords": record.get("theme_keywords"),
        "Literary techniques": record.get("literary_techniques"),
        "Narrative mechanism": record.get("narrative_mechanism"),
        "Literary analysis": record.get("literary_analysis"),
        "Documented sensory cues": sensory.get("documented_cues"),
        "Sensory detail limits": sensory.get("coverage"),
        "Adaptability": record.get("adaptability"),
        "Cross-story comparisons (not asserted historical influence)": record.get("cross_story_references"),
        "Version and source limits": references.get("version_notes"),
        "Refinement guidance": prompt.get("instruction") if isinstance(prompt, dict) else prompt,
    }
    return "\n".join(f"{k}: {flatten(v)}" for k, v in fields.items() if flatten(v))
