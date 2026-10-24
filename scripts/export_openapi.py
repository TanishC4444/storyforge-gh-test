"""Write the API's OpenAPI schema to web/openapi.json for frontend client generation.

    python -m scripts.export_openapi
"""
import json
from pathlib import Path

from storyforge.api.app import app

OUT = Path(__file__).resolve().parents[1] / 'web' / 'openapi.json'


def main():
    OUT.write_text(json.dumps(app.openapi(), indent=2) + '\n')
    print(f'Wrote {OUT}')


if __name__ == '__main__':
    main()
