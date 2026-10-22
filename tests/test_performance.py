import tempfile,unittest,json
from pathlib import Path
from unittest.mock import patch
from storyforge.performance import summarize,percentile
from storyforge.hosted import GoogleHosted
from storyforge.storage import save

class PerformanceTests(unittest.TestCase):
    def test_critical_path_uses_parallel_max_not_sum(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for key,seconds in [('a',4),('b',8),('c',7)]:save(root/key/'status.json',{'elapsed_seconds':seconds,'task':'writer'})
            (root/'graph.yml').write_text('  a:\n  b:\n    needs: [a]\n  c:\n    needs: [a]\n')
            result=summarize(root,root/'out',root/'graph.yml')
            self.assertEqual(result['worker_critical_path_seconds'],12)
            self.assertIsNone(result['verify_pass_rate'])
    def test_small_call_saves_count_request_only_when_enabled(self):
        answer={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'OK'}]}}]}
        for flag,count in [(True,1),(False,2)]:
            with tempfile.TemporaryDirectory() as d:
                hosted=GoogleHosted(d,'placeholder');calls=[]
                def reply(path,*args,**kwargs):
                    calls.append(path);return {'totalTokens':2} if path.endswith('countTokens') else answer
                with patch.object(hosted,'request',side_effect=reply),patch.object(hosted,'reserve'):
                    hosted.complete('gemma','s','p',20,policy={'timeout':10,'estimate_small_calls':flag})
                self.assertEqual(len(calls),count)
    def test_percentile_known_sample(self):
        self.assertEqual(percentile([1,3,2],.95),3)
        self.assertIsNone(percentile([],.5))
