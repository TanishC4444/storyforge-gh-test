"""A separate hosted-only experiment; the full Living graph stays available."""
from pathlib import Path
import yaml


def build():
    graph={'name':'Deep planning / simultaneous scenes','run-name':'Planned parallel | ${{ inputs.request_file }} | ${{ inputs.queue_tag || github.run_number }}','on':{'workflow_dispatch':{'inputs':{'request_file':{'type':'string','default':'hard-chronology'},'backend':{'type':'choice','options':['fixture','live'],'default':'live'},'queue_tag':{'type':'string','default':''}}}},'permissions':{'contents':'read','actions':'read'},'concurrency':{'group':'planned-parallel-experiment','cancel-in-progress':False},'env':{'PYTHONUNBUFFERED':'1','GEMINI_DISTINCT_PROJECTS':'true','STORY_HOSTED_ONLY':'true','STORY_REVIEW_TIMEOUT_SECONDS':'180','STORY_BATCH_TIMEOUT_SECONDS':'300'},'jobs':{}}
    jobs=graph['jobs']
    def job(key,task,needs,downloads=(),matrix=False,outputs=False):
        steps=[{'uses':'actions/checkout@v4'},{'uses':'./.github/actions/setup-worker','with':{'backend':'${{ inputs.backend }}','hosted-only':'true'}}]
        steps += [{'uses':'actions/download-artifact@v4','with':{'name':name,'path':'inputs/'+alias}} for name,alias in downloads]
        if key in {'lock','audit','publish'}:
            pattern={'lock':'planned-description-*','audit':'planned-check-*','publish':'planned-patch-*'}[key]
            steps.append({'uses':'actions/download-artifact@v4','with':{'pattern':pattern,'path':'inputs/'+('descriptions' if key=='lock' else 'scenes')}})
        steps.append({'name':task,'id':'task','env':{'GEMINI_API_KEY':'${{ secrets.GEMINI_API_KEY }}','GEMINI_API_KEYS':'${{ secrets.GEMINI_API_KEYS }}','STORY_REQUEST':'${{ inputs.request_file }}','BACKEND':'${{ inputs.backend }}','SCENE_ID':'${{ matrix.scene }}' if matrix else ''},'run':'backend=fixture\nif [ "$BACKEND" = live ]; then backend=worker; fi\npython -m storyforge.planned_parallel '+task+' --backend "$backend" --request-file "$STORY_REQUEST"'+(' --scene-id "$SCENE_ID"' if matrix else '')})
        steps.append({'uses':'actions/upload-artifact@v4','if':'always()','with':{'name':'planned-'+key+('-${{ matrix.scene }}' if matrix else ''),'path':'out/','retention-days':30,'overwrite':True}})
        value={'runs-on':'ubuntu-latest','timeout-minutes':20,'steps':steps}
        if needs:value['needs']=needs
        if matrix:value['strategy']={'fail-fast':False,'max-parallel':4,'matrix':{'scene':'${{ fromJSON(needs.prepare.outputs.scenes) }}'}}
        if outputs:value['outputs']={'scenes':'${{ steps.task.outputs.scenes }}'}
        jobs[key]=value
    job('prepare','prepare',[],outputs=True)
    job('outline','outline',['prepare'],[('planned-prepare','state')])
    job('description','refine',['prepare','outline'],[('planned-outline','state')],True)
    job('lock','lock',['description','outline'],[('planned-outline','state')])
    job('write','write',['prepare','lock'],[('planned-lock','state')],True)
    job('check','check',['prepare','lock','write'],[('planned-lock','state'),('planned-write-${{ matrix.scene }}','draft')],True)
    job('audit','audit',['lock','check'],[('planned-lock','state')])
    job('patch','patch',['prepare','lock','check','audit'],[('planned-lock','state'),('planned-check-${{ matrix.scene }}','draft'),('planned-audit','audit')],True)
    job('publish','publish',['lock','patch'],[('planned-lock','state')])
    jobs['results']={'runs-on':'ubuntu-latest','needs':list(jobs),'if':'always()','steps':[{'uses':'actions/checkout@v4'},{'uses':'actions/download-artifact@v4','with':{'pattern':'planned-*','path':'results'}},{'name':'Collect all readable scenes and their real approval state','run':'''python - <<'PY'
import json
from pathlib import Path
source=Path('results');out=Path('reading');out.mkdir(exist_ok=True)
scenes={}
for phase in ['write','check','patch']:
 for p in source.glob('planned-'+phase+'-*/scene.json'):
  s=json.loads(p.read_text());scenes[s['scene_id']]=s
(out/'STORY-DRAFT.txt').write_text('\\n\\n* * *\\n\\n'.join(scenes[k]['prose'] for k in sorted(scenes))+'\\n')
report=source/'planned-publish/report.json'
if report.exists():(out/'report.json').write_text(report.read_text())
else:(out/'report.json').write_text(json.dumps({'pass':False,'status':'incomplete','saved_scenes':len(scenes)}))
PY'''},{'uses':'actions/upload-artifact@v4','if':'always()','with':{'name':'parallel-readable-story','path':'reading/','retention-days':30,'overwrite':True}}]}
    return yaml.safe_dump(graph,sort_keys=False,width=120)


if __name__=='__main__':(Path(__file__).resolve().parents[1]/'.github/workflows/planned-parallel.yml').write_text(build())
