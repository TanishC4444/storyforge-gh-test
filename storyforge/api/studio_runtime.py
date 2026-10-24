"""Persistent local projects and bounded background jobs for the unified FastAPI UI."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import threading
from ..soundtracks import discover_stories
from ..storage import load, save


def now():return datetime.now(timezone.utc).isoformat()


class StudioRuntime:
    def __init__(self, root):
        self.root=Path(root).resolve();self.token=secrets.token_urlsafe(32)
        self.pool=ThreadPoolExecutor(max_workers=2);self.guard=threading.RLock();self.jobs={};self.projects={};self.oauth={}
        from ..production_exports import GoogleCalendar
        self.google=GoogleCalendar()
        self.job_dir=self.root/'runs'/'studio-jobs';self.job_dir.mkdir(parents=True,exist_ok=True)
        for file in sorted(self.job_dir.glob('*.json'))[-200:]:
            try:
                item=load(file)
                if item['status'] in ('queued','running'):
                    item.update(status='interrupted',message='Server restarted. Check outputs/provider usage before retrying.');save(file,item)
                self.jobs[item['id']]=item
            except (ValueError,OSError,KeyError):pass
        self.refresh_projects()
        if not self.projects:self.create_project('New story','Start your story or paste an existing scene here.')

    def refresh_projects(self):
        for path in discover_stories(self.root):
            if any(part in ('api-cache','demo_data') for part in path.parts):continue
            ident=hashlib.sha256(str(path).encode()).hexdigest()[:16]
            self.projects[ident]=path

    def project_list(self):
        self.refresh_projects();items=[]
        for ident,path in self.projects.items():
            title=path.name
            if (path/'request.json').is_file():
                try:title=load(path/'request.json').get('title',title)
                except (ValueError,OSError,AttributeError):pass
            elif (path/'story.txt').is_file():title=(path/'story.txt').read_text(encoding='utf-8-sig').splitlines()[0][:100] or title
            items.append({'id':ident,'title':title,'folder':str(path.relative_to(self.root))})
        return items

    def folder(self, ident=None):
        self.refresh_projects()
        if ident:
            if ident not in self.projects:raise ValueError('Project not found')
            return self.projects[ident]
        return next(iter(self.projects.values()))

    def project_id(self,path):return next(k for k,v in self.projects.items() if v==Path(path))

    def create_project(self,title,text,brief=None):
        if not isinstance(text,str) or not 1<=len(text)<=200000:raise ValueError('Story text must contain 1–200,000 characters')
        if not isinstance(title,str) or not title.strip() or len(title)>150:raise ValueError('Project title must contain 1–150 characters')
        if brief is not None and not isinstance(brief,dict):raise ValueError('Brief must be a JSON object')
        path=self.root/'runs'/'studio-projects'/secrets.token_hex(10);path.mkdir(parents=True)
        save(path/'story.txt',title.strip()+'\n\n'+text)
        if brief is not None:
            if not isinstance(brief,dict):raise ValueError('Brief must be a JSON object')
            save(path/'request.json',brief)
        self.refresh_projects()
        return self.project_id(path)

    def submit(self,kind,folder,operation):
        with self.guard:
            if sum(j['status'] in ('queued','running') for j in self.jobs.values())>=4:raise ValueError('Four jobs are already active. Wait for one to finish.')
            ident=secrets.token_hex(12)
            self.jobs[ident]={'id':ident,'kind':kind,'project_id':self.project_id(folder),'status':'queued','created_at':now(),'message':'Queued'}
            self.persist(ident)
            self.pool.submit(self._work,ident,operation)
        return ident

    def persist(self,ident):save(self.job_dir/(ident+'.json'),self.jobs[ident])

    def _work(self,ident,operation):
        def progress(message):
            with self.guard:
                self.jobs[ident].update(status='running',message=message,updated_at=now());self.persist(ident)
        try:
            progress('Working')
            result=operation(progress)
            with self.guard:self.jobs[ident].update(status='complete',message='Complete',result=result,updated_at=now());self.persist(ident)
        except Exception as exc:
            message=str(exc)[:800] if isinstance(exc,(ValueError,OSError,KeyError,TypeError)) else 'Unexpected job failure. Inspect saved outputs before retrying.'
            with self.guard:self.jobs[ident].update(status='failed',message=message,updated_at=now());self.persist(ident)

    def job(self,ident):
        if ident not in self.jobs:raise ValueError('Job not found')
        return self.jobs[ident]

    def output_files(self,folder):
        allowed={'.txt','.json','.md','.csv','.ics','.png','.jpg','.jpeg','.webp','.mp3','.wav','.opus','.flac','.pdf','.docx','.zip'}
        rows=[]
        for path in sorted(Path(folder).rglob('*')):
            if len(rows)>=1000:break
            if not path.is_file() or path.suffix.lower() not in allowed or path.name.startswith('.') or path.is_symlink():continue
            if any(p in ('provider-budget','model_cache','node_modules','.git') for p in path.relative_to(folder).parts):continue
            relative=path.relative_to(folder).as_posix()
            rows.append({'path':relative,'bytes':path.stat().st_size,'modified':path.stat().st_mtime,'type':path.suffix.lower()})
        return rows

    def output_path(self,folder,relative):
        if relative not in {x['path'] for x in self.output_files(folder)}:raise ValueError('Output file not found')
        path=(Path(folder)/relative).resolve()
        if not path.is_relative_to(Path(folder).resolve()):raise ValueError('Invalid output path')
        return path
