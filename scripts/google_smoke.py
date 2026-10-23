"""Small live schema smoke test; output contains public model names only."""
import json,tempfile
from storyforge.hosted import GoogleHosted,HostedError,MODELS

def main():
    passed=[];unavailable=[]
    with tempfile.TemporaryDirectory() as folder:
        client=GoogleHosted(folder)
        budget={'remaining':3};client.request_budget=budget
        for child in client.project_children:child.request_budget=budget
        if not client.keys:raise SystemExit('No Google credentials configured')
        for kind in ['lite','flash36','flash']:
            try:
                text,meta=client.complete(kind,'Return only the requested JSON.','Return {"ok":true}.',512,
                    structured=True,response_schema={'type':'object','properties':{'ok':{'type':'boolean'}},'required':['ok'],'additionalProperties':False},
                    role='provider_smoke',policy={'timeout':12,'thinking':'low','quality_routing':True,'estimate_small_calls':True,'route_budget':12,'max_project_attempts':1,'request_attempt_limit':3})
                if json.loads(text)!={'ok':True}:raise SystemExit('Unexpected smoke result for '+MODELS[kind])
                passed.append(meta['model'])
            except HostedError as exc:unavailable.append({'model':MODELS[kind],'reason':str(exc)})
    print(json.dumps({'passed':passed,'unavailable':unavailable}))
    if unavailable:raise SystemExit('One or more configured model routes are unavailable')

if __name__=='__main__':main()
