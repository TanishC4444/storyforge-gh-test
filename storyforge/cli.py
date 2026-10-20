from __future__ import annotations
import argparse
import json
from pathlib import Path
from .contracts import request
from .coordinator import run
from .storage import load


def main():
    parser = argparse.ArgumentParser(description='One coordinator, fresh GH-AI jobs, file-backed state')
    parser.add_argument('--request', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--backend', choices=['fixture', 'github'], default='fixture')
    parser.add_argument('--approve-plan', action='store_true')
    parser.add_argument('--stop-after', type=int)
    args = parser.parse_args()
    if args.stop_after is not None and args.stop_after < 1:
        parser.error('--stop-after must be positive')
    source = args.out / 'request.json' if args.resume else args.request
    if source is None:
        parser.error('--request required for a new run')
    try:
        req = request(load(source))
        state = run(req, args.out, args.backend, stop_after=args.stop_after, approve_plan=args.approve_plan)
        print(json.dumps({'backend': state['backend'], 'accepted_scenes': len(state['accepted']), 'complete': state.get('complete', False), 'output': str(args.out.resolve())}))
    except (ValueError, RuntimeError, OSError) as exc:
        parser.exit(1, f'Stopped: {exc}\nAccepted state remains resumable.\n')

if __name__ == '__main__':
    main()
