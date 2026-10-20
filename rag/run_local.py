"""Compatibility entrypoint for the runner previously copied into rag/."""
import runpy
from pathlib import Path

if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).resolve().parents[1] / "run_local.py"), run_name="__main__")
