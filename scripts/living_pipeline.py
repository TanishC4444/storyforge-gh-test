"""Separate-runner Living graph with fewer deterministic artifact barriers."""
import copy,json
from scripts.build_expansion_workflow import build_living,dump_workflow
import yaml


def build():
    graph=json.loads(json.dumps(yaml.safe_load(build_living())));old=graph['jobs'];jobs={k:old[k] for k in ['prepare','quickstart']}
    graph['name']='Living universe / verified-memory pipeline'
    graph['run-name']='Living | ${{ inputs.request_file }} | ${{ inputs.queue_tag || github.run_number }}'
    graph['on']['workflow_dispatch']['inputs']['queue_tag']={'type':'string','default':'','description':'Optional correlation ID for a sequential benchmark queue'}
    inputs=graph['on']['workflow_dispatch']['inputs'];inputs['request_file']['default']='living-scale-practice';inputs['scene_limit']['default']='2'
    inputs['saved_draft_run']={'type':'string','default':'','description':'Optional prior run: import its complete first-scene draft under the same brief/canon; recheck quality and memory'}
    inputs['recovery_probe']={'type':'boolean','default':False,'description':'Benchmark only: interrupt scene 2 once to verify checkpoint recovery'}
    graph['env']['STORY_LIVING_PIPELINE']='true'
    def add(key,template,title,task,needs,files,index,*,module='living_stages',matrix=None,outputs=(),condition=None):
        job=copy.deepcopy(old[template]);job['name']='Scene '+str(index+1)+' / '+title;job['needs']=list(dict.fromkeys(needs));job.pop('strategy',None);job.pop('outputs',None)
        job['if']=condition or '${{ always() && !cancelled() && '+str(index)+' < fromJSON(inputs.scene_limit)'+''.join(' && needs.'+name+".result == 'success'" for name in job['needs'])+' }}'
        if condition and 'always()' not in condition:
            body=condition[4:-3]
            job['if']='${{ always() && !cancelled() && ('+body+')'+''.join(' && needs.'+name+".result == 'success'" for name in job['needs'])+' }}'
        if matrix is not None:job['strategy']={'fail-fast':False,'max-parallel':6 if 'memory' in key else 4 if key.endswith('_characters') else 2,'matrix':{'character' if key.endswith('_characters') else 'batch':matrix}}
        if outputs:job['outputs']={name:'${{ steps.task.outputs.'+name+' }}' for name in outputs}
        steps=[]
        for step in job['steps']:
            if step.get('uses')=='actions/download-artifact@v4' or step.get('name')=='Show generated prose before final acceptance':continue
            if step.get('id')=='task':
                manifest=[{'name':spec[0],'path':spec[1],'pattern':bool(len(spec)>2 and spec[2]),'condition':spec[3].replace('${{','').replace('}}','').strip() if len(spec)>3 else None} for spec in files]
                patterns=list(dict.fromkeys(spec[0] for spec in files))
                steps.append({'name':'Fetch upstream artifacts in one parallel transfer','uses':'actions/download-artifact@v4','with':{'pattern':patterns[0] if len(patterns)==1 else '{'+','.join(patterns)+'}','path':'incoming'}})
                steps.append({'name':'Bind downloaded artifacts to explicit source aliases','env':{'STORY_ARTIFACT_MANIFEST':json.dumps(manifest,separators=(',',':')),'STORY_UPSTREAM_NEEDS':'${{ toJSON(needs) }}'},'run':'python -m storyforge.living_stages arrange'})
                step['name']=title;env=step['env'];env.pop('STORY_BATCH',None);env.pop('STORY_CHARACTER',None)
                command='python -m storyforge.'+module+' '+task+' --backend "$backend" --index '+str(index)
                if matrix is not None:
                    if key.endswith('_characters'):env['STORY_CHARACTER']='${{ matrix.character }}';command+=' --character "$STORY_CHARACTER"'
                    else:env['STORY_BATCH']='${{ matrix.batch }}';command+=(' --group "$STORY_BATCH"' if task=='review_batch' else ' --batch "$STORY_BATCH"')
                if task=='review_batch':command+=' --kind '+('rhetoric' if 'rhetoric' in key else 'story')
                step['run']='backend=fixture\nif [ "$STORY_BACKEND" = live ]; then backend=worker; fi\n'+command
            if step.get('uses')=='actions/upload-artifact@v4':step['with']['name']=key+('-${{ matrix.character }}' if key.endswith('_characters') else '-${{ matrix.batch }}' if matrix is not None else '')
            steps.append(step)
        job['steps']=steps;jobs[key]=job
    for i in range(4):
        p=f's{i+1:02}';prior='quickstart' if i==0 else f's{i:02}_accept';state=[(p+'_design','state')]
        add(p+'_design',p+'_design','Reconcile scene '+str(i+1)+' with verified prior memory','scene_design',[prior],[(prior,'state')],i,module='dag',outputs=['characters'])
        if i==1:
            steps=jobs[p+'_design']['steps'];position=next(j for j,s in enumerate(steps) if s.get('id')=='task')
            steps.insert(position,{'name':'Controlled recovery probe: interrupt before scene 2 once','if':"${{ inputs.recovery_probe && github.run_attempt == 1 }}",'run':"echo 'Intentional interruption; scene 1 checkpoint remains saved.'\nexit 75"})
        add(p+'_characters',p+'_characters','Independent character ${{ matrix.character }} / scene '+str(i+1),'character',[p+'_design'],state,i,module='dag',matrix='${{ fromJSON(needs.'+p+'_design.outputs.characters) }}')
        add(p+'_direction',p+'_direction','Compile character direction and writing plan','direction_plan',[p+'_design',p+'_characters'],state+[(p+'_characters-*','characters',True)],i,outputs=['characters'])
        add(p+'_write_batches',p+'_write_batches','Write coherent scene / batch ${{ matrix.batch }}','write_batch',[p+'_design',p+'_direction'],state+[(p+'_direction','plan')],i,module='batch_pipeline',matrix='${{ fromJSON(needs.'+p+'_direction.outputs.characters) }}')
        if i==0:
            steps=jobs[p+'_write_batches']['steps'];position=next(j for j,s in enumerate(steps) if s.get('id')=='task')
            steps.insert(position,{'name':'Recover saved first-scene prose without inheriting approval','if':"${{ inputs.saved_draft_run != '' }}",'uses':'actions/download-artifact@v4','with':{'pattern':'{s01_design,s01_write_batches-0}','run-id':'${{ inputs.saved_draft_run }}','github-token':'${{ github.token }}','path':'inputs/reused'}})
        add(p+'_draft',p+'_draft','Compile readable draft and source extraction plan','draft_extract_plan',[p+'_design',p+'_direction',p+'_write_batches'],state+[(p+'_direction','plan'),(p+'_write_batches-*','batches',True)],i,outputs=['characters'])
        edited=[(p+'_draft','edited')]
        for kind in ['story','rhetoric']:
            add(p+'_'+kind+'_batches',p+'_'+kind+'_batches','Full-scene '+kind+' checks / batch ${{ matrix.batch }}','review_batch',[p+'_design',p+'_draft'],state+edited,i,module='batch_pipeline',matrix=[0])
        add(p+'_memory_extract_batches',p+'_memory_extract_batches','Extract source-supported facts / batch ${{ matrix.batch }}','memory_extract_batch',[p+'_design',p+'_draft'],state+edited+[(p+'_draft','plan')],i,module='batch_pipeline',matrix='${{ fromJSON(needs.'+p+'_draft.outputs.characters) }}')
        add(p+'_memory',p+'_memory','Compile full memory and allocate exhaustive checks','memory_compile_plan',[p+'_design',p+'_draft',p+'_memory_extract_batches'],state+edited+[(p+'_draft','plan'),(p+'_memory_extract_batches-*','batches',True)],i,outputs=['characters'])
        add(p+'_memory_preflight_batches',p+'_memory_preflight_batches','Check every fact/history/source partition / ${{ matrix.batch }}','memory_check_batch',[p+'_design',p+'_draft',p+'_memory'],state+edited+[(p+'_memory','memory'),(p+'_memory','plan')],i,module='batch_pipeline',matrix='${{ fromJSON(needs.'+p+'_memory.outputs.characters) }}')
        add(p+'_memory_preflight',p+'_memory_preflight','Join independently verified factual findings','memory_check_join',[p+'_design',p+'_draft',p+'_memory',p+'_memory_preflight_batches'],state+edited+[(p+'_memory','memory'),(p+'_memory','plan'),(p+'_memory_preflight_batches-*','batches',True)],i,module='batch_pipeline')
        add(p+'_repair_plan',p+'_repair_plan','Compile literary findings and allocate targeted edits','repair_plan',[p+'_design',p+'_draft',p+'_story_batches',p+'_rhetoric_batches',p+'_memory_preflight'],state+edited+[(p+'_story_batches-*','story-batches',True),(p+'_rhetoric_batches-*','rhetoric-batches',True),(p+'_memory_preflight','memory-review')],i,outputs=['characters'])
        add(p+'_repair_batches',p+'_repair_batches','Repair only source-owned disputed passages / ${{ matrix.batch }}','repair_batch',[p+'_design',p+'_repair_plan'],state+[(p+'_repair_plan','plan')],i,module='batch_pipeline',matrix='${{ fromJSON(needs.'+p+'_repair_plan.outputs.characters) }}')
        add(p+'_repair',p+'_repair','Merge edits and plan changed-evidence refresh','repair_refresh_plan',[p+'_design',p+'_draft',p+'_repair_plan',p+'_repair_batches',p+'_memory',p+'_memory_preflight'],state+edited+[(p+'_repair_plan','plan'),(p+'_repair_batches-*','batches',True),(p+'_memory','initial-memory'),(p+'_memory_preflight','preflight-memory')],i,outputs=['characters','refresh_required'])
        candidate=[(p+'_repair','edited')]
        add(p+'_final_check',p+'_final_check','One final strict judgment; reuse only exact passing evidence','finalize',[p+'_design',p+'_repair',p+'_draft',p+'_repair_plan',p+'_memory'],state+candidate+[(p+'_draft','original'),(p+'_repair_plan','findings'),(p+'_memory','initial-memory')],i)
        refresh_condition='${{ '+str(i)+' < fromJSON(inputs.scene_limit) && needs.'+p+'_repair.outputs.refresh_required == \'true\' }}'
        add(p+'_memory_refresh_batches',p+'_memory_refresh_batches','Refresh only changed source facts / ${{ matrix.batch }}','memory_extract_batch',[p+'_design',p+'_repair'],state+candidate+[(p+'_repair','plan')],i,module='batch_pipeline',matrix='${{ fromJSON(needs.'+p+'_repair.outputs.characters) }}',condition=refresh_condition)
        allow='${{ always() && !cancelled() && '+str(i)+' < fromJSON(inputs.scene_limit) && needs.'+p+'_repair.result == \'success\' && (needs.'+p+'_memory_refresh_batches.result == \'success\' || needs.'+p+'_memory_refresh_batches.result == \'skipped\') }}'
        add(p+'_final_memory',p+'_final_memory','Compile complete final memory and reuse exact factual proof','final_memory_plan',[p+'_design',p+'_repair',p+'_memory_preflight',p+'_memory_refresh_batches'],state+candidate+[(p+'_repair','plan'),(p+'_memory_preflight','preflight-memory'),(p+'_memory_refresh_batches-*','batches',True,'${{ needs.'+p+'_repair.outputs.refresh_required == \'true\' }}')],i,outputs=['characters','checks_required'],condition=allow)
        needs_checks='${{ '+str(i)+' < fromJSON(inputs.scene_limit) && needs.'+p+'_final_memory.outputs.checks_required == \'true\' }}'
        add(p+'_memory_final_batches',p+'_memory_final_batches','Verify changed final memory / partition ${{ matrix.batch }}','memory_check_batch',[p+'_design',p+'_repair',p+'_final_memory'],state+candidate+[(p+'_final_memory','memory'),(p+'_final_memory','plan')],i,module='batch_pipeline',matrix='${{ fromJSON(needs.'+p+'_final_memory.outputs.characters) }}',condition=needs_checks)
        allow='${{ always() && !cancelled() && '+str(i)+' < fromJSON(inputs.scene_limit) && needs.'+p+'_final_memory.result == \'success\' && (needs.'+p+'_memory_final_batches.result == \'success\' || needs.'+p+'_memory_final_batches.result == \'skipped\') }}'
        add(p+'_memory_review',p+'_memory_review','Bind final factual proof to exact text and state','memory_final_join',[p+'_design',p+'_repair',p+'_final_memory',p+'_memory_final_batches'],state+candidate+[(p+'_final_memory','memory'),(p+'_final_memory','plan'),(p+'_memory_final_batches-*','batches',True,'${{ needs.'+p+'_final_memory.outputs.checks_required == \'true\' }}')],i,outputs=['repair_required'],condition=allow)
        recovery='${{ '+str(i)+' < fromJSON(inputs.scene_limit) && needs.'+p+'_memory_review.outputs.repair_required == \'true\' }}'
        add(p+'_memory_recovery_plan',p+'_memory_review','Allocate one targeted final-memory correction','memory_recovery_plan',[p+'_design',p+'_repair',p+'_memory_review'],state+candidate+[(p+'_memory_review','memory'),(p+'_memory_review','memory-review')],i,outputs=['characters'],condition=recovery)
        add(p+'_memory_recovery_batches',p+'_memory_refresh_batches','Correct only flagged memory source / ${{ matrix.batch }}','memory_extract_batch',[p+'_design',p+'_repair',p+'_memory_recovery_plan'],state+candidate+[(p+'_memory_recovery_plan','plan')],i,module='batch_pipeline',matrix='${{ fromJSON(needs.'+p+'_memory_recovery_plan.outputs.characters) }}')
        add(p+'_memory_recovered',p+'_final_memory','Compile corrected facts for independent verification','memory_recovered_plan',[p+'_design',p+'_repair',p+'_memory_recovery_plan',p+'_memory_recovery_batches'],state+candidate+[(p+'_memory_recovery_plan','plan'),(p+'_memory_recovery_batches-*','batches',True)],i,outputs=['characters'])
        add(p+'_memory_recovery_checks',p+'_memory_final_batches','Verify corrected memory once / ${{ matrix.batch }}','memory_check_batch',[p+'_design',p+'_repair',p+'_memory_recovered'],state+candidate+[(p+'_memory_recovered','memory'),(p+'_memory_recovered','plan')],i,module='batch_pipeline',matrix='${{ fromJSON(needs.'+p+'_memory_recovered.outputs.characters) }}')
        add(p+'_memory_recovery_join',p+'_memory_review','Bind recovered proof without another repair loop','memory_recovery_join',[p+'_design',p+'_repair',p+'_memory_recovered',p+'_memory_recovery_checks'],state+candidate+[(p+'_memory_recovered','memory'),(p+'_memory_recovered','plan'),(p+'_memory_recovery_checks-*','batches',True)],i)
        allow='${{ always() && !cancelled() && '+str(i)+' < fromJSON(inputs.scene_limit) && needs.'+p+'_design.result == \'success\' && needs.'+p+'_final_check.result == \'success\' && needs.'+p+'_memory_review.result == \'success\' && (needs.'+p+'_memory_recovery_join.result == \'success\' || (needs.'+p+'_memory_review.outputs.repair_required != \'true\' && needs.'+p+'_memory_recovery_join.result == \'skipped\')) }}'
        add(p+'_accept',p+'_accept','Commit scene '+str(i+1)+' only after literary and factual gates','accept',[p+'_design',p+'_final_check',p+'_memory_review',p+'_memory_recovery_join'],state+[(p+'_final_check','edited'),(p+'_memory_review','memory'),(p+'_memory_review','memory-review'),(p+'_memory_recovery_join','recovered-memory',False,'${{ needs.'+p+'_memory_review.outputs.repair_required == \'true\' }}')],i,condition=allow)
    jobs['results']=old['results'];jobs['results']['needs']=list(jobs)[:-1] if list(jobs)[-1]=='results' else [k for k in jobs if k!='results']
    jobs['results']['steps'] += [
        {'name':'Save restart checkpoint and all scene drafts even after failure','if':'always()','run':'python -m storyforge.story_checkpoint --source results --out recovery --expected "${{ inputs.scene_limit }}"'},
        {'uses':'actions/upload-artifact@v4','if':'always()','with':{'name':'story-recovery','path':'recovery/','retention-days':30,'overwrite':True}},
        {'name':'Require actual scene approvals and complete source-bound memory','if':'always()','env':{'EXPECTED_SCENES':'${{ inputs.scene_limit }}'},'run':'python -m storyforge.episode_audit --source results --out audit --expected "$EXPECTED_SCENES"'},
        {'uses':'actions/upload-artifact@v4','if':'always()','with':{'name':'episode-audit','path':'audit/','retention-days':30}}]
    for job in jobs.values():
        for step in job['steps']:
            if step.get('uses')=='actions/upload-artifact@v4':step['with']['overwrite']=True
    graph['jobs']=jobs
    return dump_workflow(graph)

if __name__=='__main__':
    from pathlib import Path
    (Path(__file__).resolve().parents[1]/'.github/workflows/living-universe-pipeline.yml').write_text(build())
