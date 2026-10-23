"""Runner startup must work independently of developer-installed packages/settings."""
import os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch

class PreflightTests(unittest.TestCase):
    def test_every_contract_gate_installs_its_declared_test_extra_first(self):
        import yaml
        from scripts.build_expansion_workflow import build_expansion,build_living
        from scripts.build_workflow import build,build_experimental
        documents=[(str(p),p.read_text()) for p in Path('.github/workflows').glob('*.yml')]
        documents += [(name,text) for name,text in [('generated cinematic',build_expansion()),('generated living',build_living()),('generated full api',build(troy=True,full_api=True)),('generated experiment',build_experimental())]]
        gates=0
        for name,text in documents:
            graph=yaml.safe_load(text)
            for job in graph['jobs'].values():
                installed=False
                for step in job.get('steps',[]):
                    command=step.get('run','')
                    if "pip install -e '.[test]'" in command:installed=True
                    if 'python -m unittest discover' in command:
                        gates+=1;self.assertTrue(installed,name+' runs contract tests without dependencies')
                        if 'pip install' in command:self.assertLess(command.index('pip install'),command.index('python -m unittest'))
        self.assertGreaterEqual(gates,8)
    def test_legacy_provider_test_mode_is_isolated_from_runner_project_pool(self):
        from storyforge.hosted import GoogleHosted,HostedError
        with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'GEMINI_DISTINCT_PROJECTS':'true','GEMINI_API_KEYS':'["test-backup"]'}):
            hosted=GoogleHosted(d,'test-primary',distinct_projects=False)
            self.assertFalse(hosted.project_children)
            with patch.object(hosted,'request',side_effect=HostedError('Google HTTP 429')) as call:
                with self.assertRaises(HostedError):hosted.complete('lite','s','p',20)
                self.assertEqual(call.call_count,1)
