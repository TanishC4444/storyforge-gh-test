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
    if os.name=='nt':
        # The default Windows network stack stalled and reset connections under
        # concurrent load. Use the tested selector/h11 combination; jobs stay in
        # thread pool and do not require asyncio subprocess support.
        import asyncio
        config=uvicorn.Config('storyforge.api.app:app',host='127.0.0.1',port=args.port,http='h11',access_log=False)
        with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
            runner.run(uvicorn.Server(config).serve())
    else:
        uvicorn.run('storyforge.api.app:app',host='127.0.0.1',port=args.port,access_log=False)

if __name__=='__main__':main()
