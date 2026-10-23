"""Restore the proven Living stage shape while retaining exhaustive memory checks."""
import copy


def enable(workflow,total=4):
    jobs=workflow['jobs']
    def configure(key,title,task,needs,files,index,kind=None,matrix=False):
        job=jobs[key];job['name']=title;job['needs']=needs
        if matrix:job['strategy']['matrix']['batch']=[0]
        steps=[]
        for step in job['steps']:
            if step.get('uses')=='actions/download-artifact@v4':continue
            if step.get('id')=='task':
                for name,path,pattern in files:
                    steps.append({'uses':'actions/download-artifact@v4','with':{'pattern' if pattern else 'name':name,'path':'inputs/'+path}})
                command='python -m storyforge.batch_pipeline '+task+' --backend "$backend" --index '+str(index)
                if kind:command+=' --kind '+kind
                if matrix:command+=' --group "$STORY_BATCH"'
                step['name']=title;step['run']='backend=fixture\nif [ "$STORY_BACKEND" = live ]; then backend=worker; fi\n'+command
            steps.append(step)
        job['steps']=steps
    for i in range(total):
        p=f's{i+1:02}';state=[(p+'_design','state',False)]
        for suffix in ['section_plan','summaries','summary_join','final_sections','final_summaries','final_summary_join','final_batches']:
            jobs.pop(p+'_'+suffix)
        for kind in ['story','rhetoric']:
            configure(p+'_'+kind+'_batches','Whole-scene '+kind+' checks / batch ${{ matrix.batch }}','review_batch',[p+'_design',p+'_edit'],state+[(p+'_edit','edited',False)],i,kind,True)
            configure(p+'_'+kind,'Compile '+kind+' findings without another model call','join_reviews',[p+'_design',p+'_edit',p+'_'+kind+'_batches'],state+[(p+'_edit','edited',False),(p+'_'+kind+'_batches-*','batches',True)],i,kind)
        configure(p+'_final_check','Reuse unchanged passing checks or make ONE strict final judgment','finalize',
            [p+'_design',p+'_repair',p+'_edit',p+'_story',p+'_rhetoric',p+'_memory',p+'_memory_preflight'],
            state+[(p+'_repair','edited',False),(p+'_edit','original',False),(p+'_story','story-review',False),(p+'_rhetoric','rhetoric-review',False),(p+'_memory','initial-memory',False),(p+'_memory_preflight','memory-review',False)],i)
    jobs['results']['needs']=[key for key in jobs if key!='results']
    # Hosted practices do not install CPU inference runtimes on every runner.
    workflow.setdefault('env',{}).update(STORY_HOSTED_ONLY='true',STORY_LEAN_LIVING='true')
    for key,job in jobs.items():
        job.setdefault('env',{}).update(STORY_REVIEW_TIMEOUT_SECONDS='120',STORY_BATCH_TIMEOUT_SECONDS='180')
        for step in job.get('steps',[]):
            if step.get('uses')=='./.github/actions/setup-worker':step['with']['hosted-only']='true'
            if step.get('name')=='Check inference contracts before benchmark':
                step['run']="python -m pip install -e '.[test]' -q\npython -m unittest discover -s tests -p test_preflight.py -q\n"
    return workflow
