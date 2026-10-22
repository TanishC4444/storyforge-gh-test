"""Expose writing, review and exact paragraph repairs as independent Actions matrices."""
import copy

def enable(x,total):
    jobs=x['jobs'];result_job=jobs['results']
    def download(name,path,pattern=False):return {'uses':'actions/download-artifact@v4','with':{'pattern' if pattern else 'name':name,'path':'inputs/'+path}}
    def make(template,key,title,task,needs,files,index,infer=True,matrix=None,kind=None,phase=None):
        j=copy.deepcopy(template);j['name']=title;j['needs']=needs
        j.pop('strategy',None);j.pop('outputs',None)
        if matrix:
            j['strategy']={'fail-fast':False,'max-parallel':6,'matrix':{'batch':matrix}}
        if task in {'draft_plan','repair_plan','memory_check_plan'}:j['outputs']={'characters':'${{ steps.task.outputs.characters }}'}
        kept=[]
        for s in j['steps']:
            if s.get('uses')=='actions/download-artifact@v4':continue
            if s.get('name')=='Show generated prose before final acceptance':continue
            if s.get('uses')=='./.github/actions/setup-worker':s['with']['backend']='${{ inputs.backend }}' if infer else 'fixture'
            if s.get('id')=='task':
                s['name']=title
                env=s['env'];env.pop('STORY_CHARACTER',None)
                env.update(GEMINI_API_KEY='${{ secrets.GEMINI_API_KEY }}',GEMINI_API_KEYS='${{ secrets.GEMINI_API_KEYS }}',GEMINI_DISTINCT_PROJECTS='true')
                if matrix:env['STORY_BATCH']='${{ matrix.batch }}'
                cmd='python -m storyforge.batch_pipeline '+task+' --backend "$backend" --index '+str(index)
                if kind:cmd+=' --kind '+kind
                if phase:cmd+=' --phase '+phase
                if matrix:cmd+=(' --group "$STORY_BATCH"' if task=='review_batch' else ' --batch "$STORY_BATCH"')
                s['run']='backend=fixture\nif [ "$STORY_BACKEND" = live ]; then backend=worker; fi\n'+cmd
                kept.extend([download(*f) for f in files])
            if s.get('uses')=='actions/upload-artifact@v4':s['with']['name']=key+('-${{ matrix.batch }}' if matrix else '')
            kept.append(s)
        j['steps']=kept
        if task in {'merge_draft','forward','merge_repairs','finalize'}:
            pos=next(i for i,s in enumerate(kept) if s.get('uses')=='actions/upload-artifact@v4')
            kept.insert(pos,{'name':'Show generated prose before final acceptance','if':'always()','run':'python -m storyforge.expansion preview --source out --label "'+title+'"'})
        jobs[key]=j;return j
    for i in range(total):
        p=f's{i+1:02}';state=[(p+'_design','state')]
        old={suffix:copy.deepcopy(jobs[p+'_'+suffix]) for suffix in ['draft','edit','story','rhetoric','repair','verify','verify_rhetoric','final_memory','memory','memory_review','accept']}
        jobs.pop(p+'_edit_plan',None);jobs.pop(p+'_edit_batches',None)
        make(old['draft'],p+'_draft_plan','Allocate contiguous scene-writing batches','draft_plan',[p+'_design',p+'_direction'],state+[(p+'_direction','direction')],i,False)
        make(old['draft'],p+'_write_batches','Write scene batch ${{ matrix.batch }} with Gemini-first routing','write_batch',[p+'_design',p+'_draft_plan'],state+[(p+'_draft_plan','plan')],i,True,'${{ fromJSON(needs.'+p+'_draft_plan.outputs.characters) }}')
        make(old['draft'],p+'_draft','Compile writing batches without rewriting','merge_draft',[p+'_design',p+'_draft_plan',p+'_write_batches'],state+[(p+'_draft_plan','plan'),(p+'_write_batches-*','batches',True)],i,False)
        make(old['edit'],p+'_edit','Forward prose unchanged for source-bound reviews','forward',[p+'_design',p+'_draft'],state+[(p+'_draft','draft')],i,False)
        for kind in ['story','rhetoric']:
            make(old[kind],p+'_'+kind+'_batches',kind+' review checks batch ${{ matrix.batch }}','review_batch',[p+'_design',p+'_edit'],state+[(p+'_edit','edited')],i,True,[0,1,2],kind)
            make(old[kind],p+'_'+kind,'Compile '+kind+' review findings','join_reviews',[p+'_design',p+'_edit',p+'_'+kind+'_batches'],state+[(p+'_edit','edited'),(p+'_'+kind+'_batches-*','batches',True)],i,False,kind=kind)
        def memory_graph(prefix,edited,memory,phase,joined):
            files=state+[(edited,'edited'),(memory,'memory')]
            make(old['memory_review'],prefix+'_plan','Allocate '+phase+' memory checks','memory_check_plan',[p+'_design',edited,memory],files,i,False,phase=phase)
            make(old['memory_review'],prefix+'_batches',phase+' memory / continuity batch ${{ matrix.batch }}','memory_check_batch',[p+'_design',edited,memory,prefix+'_plan'],files+[(prefix+'_plan','plan')],i,True,'${{ fromJSON(needs.'+prefix+'_plan.outputs.characters) }}')
            make(old['memory_review'],joined,'Compile '+phase+' memory findings','memory_check_join',[p+'_design',edited,memory,prefix+'_plan',prefix+'_batches'],files+[(prefix+'_plan','plan'),(prefix+'_batches-*','batches',True)],i,False)
        memory_graph(p+'_memory_preflight',p+'_edit',p+'_memory','preflight',p+'_memory_preflight')
        findings=state+[(p+'_edit','edited'),(p+'_story','story-review'),(p+'_rhetoric','rhetoric-review'),(p+'_memory_preflight','memory-review')]
        make(old['repair'],p+'_repair_plan','Group exact disputed paragraphs into repair batches','repair_plan',[p+'_design',p+'_edit',p+'_story',p+'_rhetoric',p+'_memory_preflight'],findings,i,False)
        make(old['repair'],p+'_repair_batches','Fix ONLY cited paragraphs / batch ${{ matrix.batch }}','repair_batch',[p+'_design',p+'_repair_plan'],state+[(p+'_repair_plan','plan')],i,True,'${{ fromJSON(needs.'+p+'_repair_plan.outputs.characters) }}')
        make(old['repair'],p+'_repair','Merge targeted fixes; preserve untouched paragraphs','merge_repairs',[p+'_design',p+'_edit',p+'_repair_plan',p+'_repair_batches'],state+[(p+'_edit','edited'),(p+'_repair_plan','plan'),(p+'_repair_batches-*','batches',True)],i,False)
        make(old['repair'],p+'_final_check','ONE final strict prompt check; no rewrite loop','finalize',[p+'_design',p+'_repair',p+'_story',p+'_rhetoric',p+'_memory_preflight'],state+[(p+'_repair','edited'),(p+'_story','story-review'),(p+'_rhetoric','rhetoric-review'),(p+'_memory_preflight','memory-review')],i,True)
        make(old['verify'],p+'_verify','Reuse final story verdict','verdict_view',[p+'_design',p+'_final_check'],state+[(p+'_final_check','edited')],i,False,kind='story')
        make(old['verify_rhetoric'],p+'_verify_rhetoric','Reuse final rhetoric verdict','verdict_view',[p+'_design',p+'_final_check'],state+[(p+'_final_check','edited')],i,False,kind='rhetoric')
        make(old['memory'],p+'_memory','Extract evidence-bound initial facts','extract_initial',[p+'_design',p+'_edit'],state+[(p+'_edit','edited')],i)
        make(old['final_memory'],p+'_final_memory','Refresh facts ONLY where prose changed','refresh_memory',[p+'_design',p+'_edit',p+'_final_check',p+'_memory'],state+[(p+'_edit','original'),(p+'_final_check','edited'),(p+'_memory','initial-memory')],i)
        memory_graph(p+'_memory_final',p+'_final_check',p+'_final_memory','final',p+'_memory_review')
        # Acceptance stays on the existing gate, consuming the one final judgment.
        accept=jobs[p+'_accept']
        accept['needs']=[p+'_design',p+'_final_check',p+'_verify',p+'_verify_rhetoric',p+'_final_memory',p+'_memory_review']
        for s in accept['steps']:
            if s.get('uses')=='actions/download-artifact@v4' and s.get('with',{}).get('name')==p+'_repair':s['with']['name']=p+'_final_check'
    for key,j in jobs.items():
        j['env']={'STORY_REVIEW_TIMEOUT_SECONDS':'600','STORY_BATCH_TIMEOUT_SECONDS':'600'}
        for s in j.get('steps',[]):
            if s.get('id')=='task':s.setdefault('env',{}).update(GEMINI_DISTINCT_PROJECTS='true',GEMINI_API_KEY='${{ secrets.GEMINI_API_KEY }}',GEMINI_API_KEYS='${{ secrets.GEMINI_API_KEYS }}')
    result_job['needs']=[key for key in jobs if key!='results']
    return x
