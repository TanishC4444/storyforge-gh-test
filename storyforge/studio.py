"""Start the complete local FastAPI studio with one command."""
import argparse
import os
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8000)
    parser.add_argument('--workspace',type=Path,help='Repository/workspace containing outputs and story projects')
    args=parser.parse_args()
    if not 1<=args.port<=65535:parser.error('Port must be 1–65535')
    if args.workspace:os.environ['STORYFORGE_WORKSPACE']=str(args.workspace.resolve())
    import uvicorn
    print(f'StoryForge Studio: http://127.0.0.1:{args.port}',flush=True)
    uvicorn.run('storyforge.api.app:app',host='127.0.0.1',port=args.port,access_log=False)

if __name__=='__main__':main()
