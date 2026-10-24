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
    if executor.req.get('performance',{}).get('adaptive_batches'):
        from .editorial import validate_review_brief
        from .storage import load,save
        def validate(v):return validate_review_brief(editorial(v,prose,checks),executor.req)
        try:
            result=executor.call(role,data,instruction+' Return the native editorial schema. Assess every dimension once. Each failing check needs a matching, source-supported issue; issue categories are check IDs, never scene IDs. Reasons must identify actual evidence. No issue quota.',tokens=tokens,response_schema=editorial_schema(data),validator=validate)
            require(not result.get('unverified'),result.get('error','Editorial response unavailable'))
            return result
        except Exception as error:
            # Retry only a returned malformed verdict; transport outages do not generate another round.
            raw=[load(p).get('output') for p in (executor.folder/'calls').glob(role+'-*.json')]
            if executor.backend=='fixture' or not raw:raise
            try:previous=parse_json(raw[-1])
            except ValueError:raise error
            rows=previous.get('checks',{})
            frozen={k:v.get('verdict') for k,v in rows.items()} if isinstance(rows,dict) else {c['id']:c.get('verdict') for c in rows if isinstance(c,dict) and 'id' in c}
            def repaired(v):
                verdict=validate(v)
                require(all(c['verdict']==frozen[c['id']] for c in verdict['checks'] if c['id'] in frozen),'Clarification changed an existing verdict')
                for issue in previous.get('issues',[]):
                    if issue.get('severity')=='blocking':require(any(i.get('severity')=='blocking' and i.get('category')==issue.get('category') and i.get('problem')==issue.get('problem') for i in verdict['issues']),'Clarification erased a blocking finding')
                return verdict
            request=copy.deepcopy(executor.req);request['max_stage_retries']=0
            repair=Executor(request,executor.folder/'verdict-clarification',executor.backend)
            packet={**data,'returned_assessment':previous,'validation_failure':str(error),'immutable_existing_verdicts':frozen}
            result=repair.call('director',packet,'Clarify this returned assessment once. Preserve every existing check verdict. Supply missing dimensions and exact evidence-supported issues for failing checks, matching the required schema. Never invent a fault, erase a blocking issue or turn failure into approval. If evidence cannot support the assessment, do not fabricate it.',tokens=tokens,response_schema=editorial_schema(data),validator=repaired,allow_cpu_fallback=False)
            save(executor.folder/'clarification.json',{'original_validation_error':str(error),'changed_existing_verdicts':False})
            return result
    if not executor.req.get('performance',{}).get('readable_editorial'):
        return executor.call(role,data,instruction,tokens=tokens,response_schema=editorial_schema(data),validator=lambda v:editorial_review(v,prose,checks))
    def validate(value):
        from .editorial import validate_review_brief
        return validate_review_brief(editorial(value,prose,checks),executor.req)
    if executor.backend=='fixture':
        return executor.call(role,data,instruction,tokens=tokens,response_schema=editorial_schema(data),validator=validate)
    return executor.call(role,data,instruction+'\n'+REVIEW_FORMAT,tokens=tokens,response_schema=False,output_format='text',
                         skill='Judge actual source against the immutable author contract and source-bound canon. Keep reasons concise. Literary judgment remains yours.',validator=validate)


def factual_ids(value,prose,allowed):
    """Resolve source quotes ourselves; never accept a paraphrased model citation."""
    from .evidence import passages
    if not isinstance(value,str):return factual(value,prose)
    try:parsed=parse_json(value)
    except (ValueError,TypeError):parsed=None
    if parsed is not None:return factual(parsed,prose)
    catalog={p['id']:p for p in passages(prose)};lines=[]
    for line in value.splitlines():
        if line.strip().startswith('ISSUE '):
            fields=[x.strip() for x in line.strip()[6:].split('|',5)]
            # A complete advisory sometimes omits its nonblocking suggestion.
            # Preserve its source and judgment without spending another API call.
            if len(fields)==5 and fields[0]=='advisory' and fields[1] in {'memory','prose'} and fields[2] and fields[4]:
                fields.append('Retain this advisory for editorial attention; no blocking correction was requested.')
            require(len(fields)==6,'Malformed memory issue')
            ids=re.findall(r'p\d+',fields[3]);require(bool(ids) and set(ids)<=set(allowed),'Memory issue cites unsupplied source')
            require(len(ids)==len(set(ids)) and set(ids)<=set(catalog),'Invalid memory evidence IDs')
            ids=sorted(ids,key=lambda pid:catalog[pid]['start'])
            # A continuity finding can compare distant passages. Keep every exact
            # span, with one contiguous anchor for consumers requiring a quote;
            # never fabricate a quotation by joining nonadjacent paragraphs.
            ordered=list(catalog);anchor=[ids[0]]
            for pid in ids[1:]:
                if ordered.index(pid)!=ordered.index(anchor[-1])+1:break
                anchor.append(pid)
            fields[3]=prose[catalog[anchor[0]]['start']:catalog[anchor[-1]]['end']]
            issue={**dict(zip(['severity','target','category','quote','problem','fix'],fields)),
                   'evidence_ids':ids,'evidence_spans':[dict(catalog[pid]) for pid in ids]}
            lines.append(issue)
        elif line.strip() in {'PASS','FAIL'}:status=line.strip()=='PASS'
    require('status' in locals(),'Missing memory verdict')
    return factual({'pass':status,'issues':lines},prose)
