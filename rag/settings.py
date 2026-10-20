from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

@dataclass(frozen=True)
class Settings:
    database_path: str
    embedding_model: str
    embedding_dimensions: int
    @classmethod
    def from_environment(cls) -> "Settings":
        load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
        root = Path(__file__).resolve().parents[1]
        database_path = Path(os.getenv("DATABASE_PATH", "data/literary_rag.db"))
        if not database_path.is_absolute():
            database_path = root / database_path
        database_path.parent.mkdir(parents=True, exist_ok=True)
        from rag.embeddings import MODEL_NAME
        return cls(str(database_path), MODEL_NAME, 384)
