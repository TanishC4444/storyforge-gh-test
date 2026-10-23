"""Readable model output contracts; source validation remains application-owned."""
import copy,json,re
from pathlib import Path
from .contracts import require,review
from .editorial import editorial_review
from .inference import Executor,parse_json

REVIEW_FORMAT='''Return compact lines, without JSON or a preamble:
CHECK <check_id> | pass/fail/not_applicable | p001,p002 | one specific reason
ISSUE blocking/advisory | <check_id> | p001,p002 | demonstrated problem | actionable fix
Assess every requested check exactly once. Emit ISSUE only for actual faults. A failed check requires a matching ISSUE. Passage IDs must come from supplied source evidence. Never invent a quote.'''


def editorial(value,prose,checks):
    if isinstance(value,str):
        try:value=parse_json(value)
        except Exception:
            rows=[];issues=[]
            for line in value.splitlines():
                line=line.strip().lstrip('- ').strip()
                if line.startswith('CHECK '):
                    fields=[v.strip() for v in line[6:].split('|',3)];require(len(fields)==4,'Malformed CHECK line')
                    key,verdict,ids,reason=fields;rows.append({'id':key,'verdict':verdict.lower(),'evidence_ids':re.findall(r'p\d+',ids),'reason':reason})
                elif line.startswith('ISSUE '):
                    fields=[v.strip() for v in line[6:].split('|',4)];require(len(fields)==5,'Malformed ISSUE line')
                    severity,key,ids,problem,fix=fields;issues.append({'severity':severity.lower(),'category':key,'evidence_ids':re.findall(r'p\d+',ids),'problem':problem,'fix':fix})
            value={'checks':rows,'issues':issues}
    require(isinstance(value,dict),'Missing editorial assessment');value=copy.deepcopy(value)
    if isinstance(value.get('checks'),dict):value['checks']=[dict(v,id=k) for k,v in value['checks'].items()]
    # Aggregate status is derived from the model's actual judgments, never used
    # to erase a blocking finding because an inconsistent header said "pass".
    value['pass']=bool(value.get('checks')) and not any(c.get('verdict')=='fail' for c in value['checks']) and not any(i.get('severity')=='blocking' for i in value.get('issues',[]))
    return editorial_review(value,prose,checks)


def patches(value,batch):
    from .fast_edit import validate
    if isinstance(value,str):
        try:value=parse_json(value)
        except Exception:
            replacements={}
            for match in re.finditer(r'(?ms)^\s*REPLACE\s+(p\d+)\s*\n(.*?)^\s*END_REPLACE\s*$',value):
                key,text=match.groups();require(key not in replacements,'Duplicate replacement');replacements[key]=text.strip()
            for key in re.findall(r'(?m)^\s*DELETE\s+(p\d+)\s*$',value):
                require(key not in replacements,'Duplicate deletion');replacements[key]=''
            require(bool(replacements) or value.strip()=='NO_CHANGES','No valid edit blocks')
            value={'replacements':replacements}
    return validate(value,batch)


def factual(value,prose):
    if isinstance(value,str):
        try:value=parse_json(value)
        except Exception:
            issues=[];status=None
            for line in value.splitlines():
                line=line.strip()
                if line in {'PASS','FAIL'}:status=line=='PASS'
                elif line.startswith('ISSUE '):
                    fields=[v.strip() for v in line[6:].split('|',5)];require(len(fields)==6,'Malformed fact ISSUE')
                    severity,target,category,quote,problem,fix=fields
                    issues.append(dict(severity=severity.lower(),target=target,category=category,quote=quote,problem=problem,fix=fix))
            require(status is not None,'Missing fact verdict');value={'pass':status,'issues':issues}
    require(isinstance(value,dict),'Missing fact assessment');value=copy.deepcopy(value)
    value['pass']=not any(i.get('severity')=='blocking' for i in value.get('issues',[])) and value.get('pass',False)
    return review(value,prose)


def call_editorial(executor,role,data,instruction,prose,checks,tokens=1100):
    from .output_schema import editorial_schema
    if not executor.req.get('performance',{}).get('readable_editorial'):
        return executor.call(role,data,instruction,tokens=tokens,response_schema=editorial_schema(data),validator=lambda v:editorial_review(v,prose,checks))
    def validate(value):
        from .editorial import validate_review_brief
        return validate_review_brief(editorial(value,prose,checks),executor.req)
    if executor.backend=='fixture':
        return executor.call(role,data,instruction,tokens=tokens,response_schema=editorial_schema(data),validator=validate)
    return executor.call(role,data,instruction+'\n'+REVIEW_FORMAT,tokens=tokens,response_schema=False,output_format='text',
                         skill='Judge actual source against the immutable author contract and source-bound canon. Keep reasons concise. Literary judgment remains yours.',validator=validate)
