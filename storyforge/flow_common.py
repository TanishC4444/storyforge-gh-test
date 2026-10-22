"""Contracts and transport shared by opt-in experimental workflows."""
import copy,hashlib,json,re
from pathlib import Path
from .contracts import require
from .inference import Executor,ROOT
from .storage import save


def fingerprint(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
def example_path(name):
    require(isinstance(name,str) and bool(re.fullmatch(r'[a-zA-Z0-9_-]+',name)),'Unsafe example name')
    return ROOT/'examples'/(name+'.json')
def object_schema(properties):return {'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}
def strings(maximum=12):return {'type':'array','items':{'type':'string'},'maxItems':maximum}


def generated(req,out,backend,role,packet,instruction,schema,validate,fixture,tokens=1800,text=False):
    out=Path(out)
    if backend=='fixture':
        value=fixture() if callable(fixture) else copy.deepcopy(fixture)
        value=validate(value)
        save(out/'fixture-response.json',{'fixture':True,'role':role,'output':value})
        return value
    return Executor(req,out,backend).call(role,packet,instruction,tokens=tokens,response_schema=schema,validator=validate,output_format='text' if text else 'json')
