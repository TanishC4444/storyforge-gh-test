"""Reuse the existing worker runtime, or the same library's GitHub runner off-host."""
import importlib.util,os
from dataclasses import asdict

def execute(model,system,prompt,tokens,n_ctx,role,response_schema=None):
    if importlib.util.find_spec('llama_cpp') is not None:
        from .local_worker import execute as local
        return local(model,system,prompt,tokens,n_ctx,role,response_schema)
    if not os.getenv('GH_AI_TOKEN'):raise RuntimeError('CPU fallback requires the workflow runtime or GH_AI_TOKEN for the existing runner library')
    from gh_ai_runner import Agent,GitHubAIRunner
    from gh_ai_runner.limits import Limits
    from .runtime import JOB_TIMEOUT_MINUTES,JOB_TIMEOUT_SECONDS,DOWNLOAD_TIMEOUT_SECONDS
    runner=GitHubAIRunner(os.environ['GH_AI_TOKEN'],repo_name='storyforge-inference-runner',private=False,runner_ram_gb=16,metadata_path=None,verbose=False,completion_timeout=JOB_TIMEOUT_SECONDS,limits=Limits(job_timeout_minutes=JOB_TIMEOUT_MINUTES,provider_timeout_seconds=JOB_TIMEOUT_SECONDS,download_timeout_seconds=DOWNLOAD_TIMEOUT_SECONDS))
    agent=Agent(runner=runner,model=model,instructions=system,remember=False,refine_prompt=False,n_ctx=n_ctx,max_tokens=tokens,temperature=.7 if role in {'writer','humanizer'} else .25)
    result=agent.run(prompt,timeout=JOB_TIMEOUT_SECONDS)
    return result,{**asdict(agent.last_result),'fallback':'existing_github_cpu_runner'}
