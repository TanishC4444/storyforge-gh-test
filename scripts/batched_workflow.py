"""Expose writing, review and exact paragraph repairs as independent Actions matrices."""
import copy

def enable(x,total):
    jobs=x['jobs'];result_job=jobs['results']
    def download(name,path,pattern=False):return {'uses':'actions/download-artifact@v4','with':{'pattern' if pattern else 'name':name,'path':'inputs/'+path}}
    def make(template,key,title,task,needs,files,index,infer=True,matrix=None,kind=None,phase=None):
        j=copy.deepcopy(template);j['name']=title;j['needs']=needs
        j.pop('strategy',None);j.pop('outputs',None)
        if matrix:
            j['strategy']={'fail-fast':False,'max-parallel':3 if task in {'memory_check_batch','memory_extract_batch'} else 2,'matrix':{'batch':matrix}}
        if task in {'draft_plan','repair_plan','memory_check_plan','section_plan','memory_extract_plan','memory_refresh_plan'}:j['outputs']={'characters':'${{ steps.task.outputs.characters }}'}
        if task=='section_plan':j['outputs'].update(reviews='${{ steps.task.outputs.reviews }}',final_reviews='${{ steps.task.outputs.final_reviews }}',story_reviews='${{ steps.task.outputs.story_reviews }}')
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
        make(old['story'],p+'_section_plan','Allocate source sections for summaries and prose review','section_plan',[p+'_design',p+'_edit'],state+[(p+'_edit','edited')],i,False)
        make(old['story'],p+'_summaries','Summarize actual section ${{ matrix.batch }}; source-linked only','section_summary',[p+'_design',p+'_edit',p+'_section_plan'],state+[(p+'_edit','edited'),(p+'_section_plan','plan')],i,True,'${{ fromJSON(needs.'+p+'_section_plan.outputs.characters) }}')
        make(old['story'],p+'_summary_join','Consolidate short summaries; retain source links','section_summaries_join',[p+'_design',p+'_edit',p+'_section_plan',p+'_summaries'],state+[(p+'_edit','edited'),(p+'_section_plan','plan'),(p+'_summaries-*','batches',True)],i,False)
        make(old['story'],p+'_story_batches','Causal story review / checks batch ${{ matrix.batch }}','review_batch',[p+'_design',p+'_edit',p+'_section_plan',p+'_summary_join'],state+[(p+'_edit','edited'),(p+'_summary_join','summaries')],i,True,'${{ fromJSON(needs.'+p+'_section_plan.outputs.story_reviews) }}','story')
        make(old['story'],p+'_story','Compile causal findings; preserve partial results','join_reviews',[p+'_design',p+'_edit',p+'_story_batches'],state+[(p+'_edit','edited'),(p+'_story_batches-*','batches',True)],i,False,kind='story')
        make(old['rhetoric'],p+'_rhetoric_batches','Exact prose section review ${{ matrix.batch }}','section_review',[p+'_design',p+'_edit',p+'_section_plan',p+'_summary_join'],state+[(p+'_edit','edited'),(p+'_section_plan','plan'),(p+'_summary_join','summaries')],i,True,'${{ fromJSON(needs.'+p+'_section_plan.outputs.reviews) }}')
        make(old['rhetoric'],p+'_rhetoric','Compile prose findings; preserve partial results','section_reviews_join',[p+'_design',p+'_edit',p+'_section_plan',p+'_rhetoric_batches'],state+[(p+'_edit','edited'),(p+'_section_plan','plan'),(p+'_rhetoric_batches-*','batches',True)],i,False)
        def memory_graph(prefix,edited,memory,phase,joined):
            files=state+[(edited,'edited'),(memory,'memory')]
            extra=[p+'_memory_preflight'] if phase=='final' else []
            if extra:files.append((p+'_memory_preflight','preflight-memory'))
            make(old['memory_review'],prefix+'_plan','Allocate '+phase+' memory checks','memory_check_plan',[p+'_design',edited,memory]+extra,files,i,False,phase=phase)
            make(old['memory_review'],prefix+'_batches',phase+' memory / continuity batch ${{ matrix.batch }}','memory_check_batch',[p+'_design',edited,memory,prefix+'_plan']+extra,files+[(prefix+'_plan','plan')],i,True,'${{ fromJSON(needs.'+prefix+'_plan.outputs.characters) }}')
            make(old['memory_review'],joined,'Compile '+phase+' memory findings','memory_check_join',[p+'_design',edited,memory,prefix+'_plan',prefix+'_batches']+extra,files+[(prefix+'_plan','plan'),(prefix+'_batches-*','batches',True)],i,False)
        memory_graph(p+'_memory_preflight',p+'_edit',p+'_memory','preflight',p+'_memory_preflight')
        findings=state+[(p+'_edit','edited'),(p+'_story','story-review'),(p+'_rhetoric','rhetoric-review'),(p+'_memory_preflight','memory-review')]
        make(old['repair'],p+'_repair_plan','Group exact disputed paragraphs into repair batches','repair_plan',[p+'_design',p+'_edit',p+'_story',p+'_rhetoric',p+'_memory_preflight'],findings,i,False)
        make(old['repair'],p+'_repair_batches','Fix ONLY cited paragraphs / batch ${{ matrix.batch }}','repair_batch',[p+'_design',p+'_repair_plan'],state+[(p+'_repair_plan','plan')],i,True,'${{ fromJSON(needs.'+p+'_repair_plan.outputs.characters) }}')
        make(old['repair'],p+'_repair','Merge targeted fixes; preserve untouched paragraphs','merge_repairs',[p+'_design',p+'_edit',p+'_repair_plan',p+'_repair_batches'],state+[(p+'_edit','edited'),(p+'_repair_plan','plan'),(p+'_repair_batches-*','batches',True)],i,False)
        make(old['story'],p+'_final_sections','Allocate final passage checks','section_plan',[p+'_design',p+'_repair'],state+[(p+'_repair','edited')],i,False)
        make(old['story'],p+'_final_summaries','Summarize repaired section ${{ matrix.batch }}','section_summary',[p+'_design',p+'_repair',p+'_edit',p+'_summary_join',p+'_final_sections'],state+[(p+'_repair','edited'),(p+'_edit','original'),(p+'_summary_join','previous-summaries'),(p+'_final_sections','plan')],i,True,'${{ fromJSON(needs.'+p+'_final_sections.outputs.characters) }}')
        make(old['story'],p+'_final_summary_join','Join fresh final summaries','section_summaries_join',[p+'_design',p+'_repair',p+'_final_sections',p+'_final_summaries'],state+[(p+'_repair','edited'),(p+'_final_sections','plan'),(p+'_final_summaries-*','batches',True)],i,False)
        make(old['repair'],p+'_final_batches','Final passage/cohesion check ${{ matrix.batch }}','section_final_review',[p+'_design',p+'_repair',p+'_edit',p+'_story',p+'_rhetoric',p+'_memory_preflight',p+'_final_sections',p+'_final_summary_join',p+'_final_memory'],state+[(p+'_repair','edited'),(p+'_edit','original'),(p+'_story','story-review'),(p+'_rhetoric','rhetoric-review'),(p+'_memory_preflight','preflight-memory'),(p+'_final_sections','plan'),(p+'_final_summary_join','summaries'),(p+'_final_memory','memory')],i,True,'${{ fromJSON(needs.'+p+'_final_sections.outputs.final_reviews) }}')
        make(old['repair'],p+'_final_check','Compile ONE strict final judgment round','finalize',[p+'_design',p+'_repair',p+'_final_sections',p+'_final_summary_join',p+'_story',p+'_rhetoric',p+'_memory_preflight',p+'_final_batches'],state+[(p+'_repair','edited'),(p+'_final_sections','plan'),(p+'_final_summary_join','summaries'),(p+'_story','story-review'),(p+'_rhetoric','rhetoric-review'),(p+'_memory_preflight','memory-review'),(p+'_final_batches-*','final-batches',True)],i,False)
        make(old['verify'],p+'_verify','Reuse final story verdict','verdict_view',[p+'_design',p+'_final_check'],state+[(p+'_final_check','edited')],i,False,kind='story')
        make(old['verify_rhetoric'],p+'_verify_rhetoric','Reuse final rhetoric verdict','verdict_view',[p+'_design',p+'_final_check'],state+[(p+'_final_check','edited')],i,False,kind='rhetoric')
        make(old['memory'],p+'_memory_extract_plan','Allocate complete source coverage for memory extraction','memory_extract_plan',[p+'_design',p+'_edit'],state+[(p+'_edit','edited')],i,False)
        make(old['memory'],p+'_memory_extract_batches','Extract all source-supported facts / batch ${{ matrix.batch }}','memory_extract_batch',[p+'_design',p+'_edit',p+'_memory_extract_plan'],state+[(p+'_edit','edited'),(p+'_memory_extract_plan','plan')],i,True,'${{ fromJSON(needs.'+p+'_memory_extract_plan.outputs.characters) }}')
        make(old['memory'],p+'_memory','Compile complete source-bound memory; no summary substitution','memory_extract_join',[p+'_design',p+'_edit',p+'_memory_extract_plan',p+'_memory_extract_batches'],state+[(p+'_edit','edited'),(p+'_memory_extract_plan','plan'),(p+'_memory_extract_batches-*','batches',True)],i,False)
        make(old['final_memory'],p+'_memory_refresh_plan','Retain unchanged facts; allocate changed evidence batches','memory_refresh_plan',[p+'_design',p+'_edit',p+'_repair',p+'_memory',p+'_memory_preflight'],state+[(p+'_edit','original'),(p+'_repair','edited'),(p+'_memory','initial-memory'),(p+'_memory_preflight','preflight-memory')],i,False)
        make(old['final_memory'],p+'_memory_refresh_batches','Refresh changed evidence / batch ${{ matrix.batch }}','memory_extract_batch',[p+'_design',p+'_repair',p+'_memory_refresh_plan'],state+[(p+'_repair','edited'),(p+'_memory_refresh_plan','plan')],i,True,'${{ fromJSON(needs.'+p+'_memory_refresh_plan.outputs.characters) }}')
        make(old['final_memory'],p+'_final_memory','Compile retained and refreshed facts without omission','memory_extract_join',[p+'_design',p+'_repair',p+'_memory_refresh_plan',p+'_memory_refresh_batches'],state+[(p+'_repair','edited'),(p+'_memory_refresh_plan','plan'),(p+'_memory_refresh_batches-*','batches',True)],i,False)
        memory_graph(p+'_memory_final',p+'_repair',p+'_final_memory','final',p+'_memory_review')
        # Acceptance stays on the existing gate, consuming the one final judgment.
        accept=jobs[p+'_accept']
        accept['needs']=[p+'_design',p+'_final_check',p+'_verify',p+'_verify_rhetoric',p+'_final_memory',p+'_memory_review']
        for s in accept['steps']:
            if s.get('uses')=='actions/download-artifact@v4' and s.get('with',{}).get('name')==p+'_repair':s['with']['name']=p+'_final_check'
    shared={'PYTHONUNBUFFERED':1,'STORY_BACKEND':'${{ inputs.backend }}','STORY_PROFILE':'${{ inputs.profile }}','STORY_REQUEST':'${{ inputs.request_file }}','GEMINI_DISTINCT_PROJECTS':'true'}
    x['env']={**shared,'STORY_REVIEW_TIMEOUT_SECONDS':'600','STORY_BATCH_TIMEOUT_SECONDS':'600'}
    for key,j in jobs.items():
        j.pop('env',None)
        for s in j.get('steps',[]):
            if s.get('id')=='task':
                env=s.setdefault('env',{});env.update(GEMINI_API_KEY='${{ secrets.GEMINI_API_KEY }}',GEMINI_API_KEYS='${{ secrets.GEMINI_API_KEYS }}')
                for name in shared:env.pop(name,None)
    result_job['needs']=[key for key in jobs if key!='results']
    return x
