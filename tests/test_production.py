from datetime import datetime, timedelta, timezone
import base64
import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from storyforge.production import normalize_config, validate_breakdown, schedule, budget, Muse, validate_recommendations
from storyforge.production_research import Search, ProviderError
from storyforge.production_exports import calendar_ics, csv_bytes, GoogleCalendar
from storyforge.production_web import ProductionServer


def scene(ident='s1', **overrides):
    return {'id':ident,'title':'Scene '+ident,'location':'shore','description':'Film action','cast':['Meles'],'minutes':60,'light':'day','dependencies':[],'props':[],'risks':[],**overrides}


def breakdown():
    return {'title':'Troy','scenes':[scene()], 'budget_items':[{'category':'crew','description':'Crew','quantity':3,'unit':'day','low_rate':100.1,'high_rate':150,'basis':'estimate'}], 'search_queries':[], 'assumptions':[], 'missing_info':[], 'visual_criteria':[]}


class ProductionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.cfg=normalize_config({'start_date':'2026-11-02','timezone':'America/Chicago'})

    def test_validation_cycles_and_rates(self):
        value=breakdown();validate_breakdown(value)
        value['scenes']=[scene('a',dependencies=['b']),scene('b',dependencies=['a'])]
        with self.assertRaisesRegex(ValueError,'cycle'):validate_breakdown(value)
        with self.assertRaises(ValueError):normalize_config({'contingency':float('nan')})
        value=breakdown();value['budget_items'][0]['low_rate']=-1
        with self.assertRaises(ValueError):validate_breakdown(value)
        with self.assertRaises(ValueError):validate_recommendations({'locations':[{'source_ids':['invented']}]},[])

    def test_schedule_constraints_and_dependencies(self):
        cfg={**self.cfg,'cast_unavailable':{'Meles':['2026-11-02']},'blackout_dates':['2026-11-04']}
        scenes=[scene('a',minutes=210),scene('b',minutes=210,location='forge',dependencies=['a']),scene('c',minutes=60,light='night',dependencies=['b'])]
        result=schedule(scenes,cfg);self.assertFalse(result['unscheduled'])
        events=result['events'];self.assertEqual([e['scene_id'] for e in events],['a','b','c'])
        for e in events:
            self.assertNotIn(e['start'][:10],['2026-11-02','2026-11-04'])
            self.assertLess(datetime.fromisoformat(e['start']),datetime.fromisoformat(e['end']))
        self.assertTrue(events[1]['meal_before'])
        self.assertEqual(events[1]['setup_move_minutes'],75)
        self.assertGreaterEqual(datetime.fromisoformat(events[2]['start'])-datetime.fromisoformat(events[1]['end']),timedelta(hours=12))

    def test_impossible_scene_reported_and_dst(self):
        cfg={**self.cfg,'day_hours':4,'skip_weekends':False,'start_date':'2026-10-31'}
        result=schedule([scene('long',minutes=600)],cfg)
        self.assertEqual(result['unscheduled'],['long'])
        events=schedule([scene('n',light='night',minutes=60),scene('d',dependencies=['n'])],cfg)['events']
        self.assertEqual(len(events),2)
        self.assertGreaterEqual(datetime.fromisoformat(events[1]['start']).astimezone(timezone.utc)-datetime.fromisoformat(events[0]['end']).astimezone(timezone.utc),timedelta(hours=12))

    def test_budget_exact_arithmetic_unknowns_and_csv(self):
        rows=breakdown()['budget_items']+[{'category':'permits','description':'Permit','quantity':1,'unit':'item','low_rate':0,'high_rate':0,'basis':'unknown'}]
        result=budget(rows,{**self.cfg,'budget_cap':500})
        self.assertEqual(result['subtotal_low'],300.3);self.assertEqual(result['total_low'],345.35)
        self.assertEqual(result['total_high'],517.5);self.assertTrue(result['over_cap'])
        self.assertEqual(result['unknown_costs'],['Permit'])
        output=csv_bytes([{'task':'=HYPERLINK("bad")'}],['task']).decode('utf-8-sig')
        self.assertIn("'=HYPERLINK",output)

    def test_search_cache_and_failover_conserve_calls(self):
        client=Search(self.root,keys=['primary','backup'],daily_limit=5,plan_limit=1)
        with patch('storyforge.production_research.request_json',side_effect=[ProviderError('Provider HTTP 429'),{'organic_results':[{'title':'Film office','link':'https://example.gov/film','snippet':'Check permits'}]}]) as call:
            first=client.search('film office','legal');self.assertFalse(first['cached']);self.assertEqual(call.call_count,2)
            cached=client.search('film   office','legal');self.assertTrue(cached['cached']);self.assertEqual(call.call_count,2)
            with self.assertRaisesRegex(ProviderError,'Per-plan'):client.search('other')
        stored=client.db.read_bytes();self.assertNotIn(b'primary',stored);self.assertNotIn(b'backup',stored)
        fresh=Search(self.root,keys=['primary','backup'],plan_limit=1)
        with patch('storyforge.production_research.request_json',return_value={'organic_results':[]}) as call:
            fresh.search('another query');self.assertEqual(call.call_count,1)
            self.assertIn('backup',call.call_args.args[0])

    def test_search_daily_budget_no_blind_retry(self):
        client=Search(self.root,keys=['a','b','c'],daily_limit=1,plan_limit=3)
        with patch('storyforge.production_research.request_json',return_value={'organic_results':[]}) as call:
            client.search('one')
            with self.assertRaisesRegex(ProviderError,'Daily'):client.search('two')
            self.assertEqual(call.call_count,1)
        other=Search(self.root/'other',keys=['a','b'],daily_limit=5,plan_limit=3)
        with patch('storyforge.production_research.request_json',side_effect=ProviderError('Provider HTTP 500')) as call:
            with self.assertRaises(ProviderError):other.search('failed')
            self.assertEqual(call.call_count,1)

    @patch.dict('os.environ',{'VULTR_INFERENCE_API_KEY':'test-key'})
    def test_vision_payload_and_bad_image(self):
        muse=Muse();image={'mime':'image/png','data':base64.b64encode(b'\x89PNG\r\n\x1a\nTEST').decode()}
        with patch('storyforge.production.request_json',return_value={'model':'muse-glimmer-30b','choices':[{'message':{'content':'{"ok":true}'}}]}) as call:
            self.assertTrue(muse.ask('test',{'story':'text'},[image])['ok'])
            payload=call.call_args.args[1]
            self.assertEqual(payload['model'],'muse-glimmer-30b')
            self.assertEqual(payload['messages'][1]['content'][1]['type'],'image_url')
        with self.assertRaises(ValueError):muse.ask('test',{},[{'mime':'image/png','data':'not-base64'}])

    def sample_plan(self):
        return {'id':'a'*24,'title':'Troy','created_at':'2026-10-24T12:00:00+00:00','config':self.cfg,'schedule':schedule([scene()],self.cfg)}

    def test_ics_escaping_folding_and_google_idempotence_conflict(self):
        plan=self.sample_plan();plan['schedule']['events'][0]['summary']='Troy, shore; '+('海'*60)+'\nEND:VEVENT'
        ics=calendar_ics(plan)
        self.assertTrue(all(len(line)<=75 for line in ics.split(b'\r\n')))
        self.assertIn(b'STATUS:TENTATIVE',ics)
        self.assertIn(b'\\nEND:VEVENT',ics)
        client=GoogleCalendar()
        with patch.object(client,'request',side_effect=[{'items':[]},{'id':'created'}]) as call:
            out=client.sync(plan);self.assertEqual(len(out['created']),1)
            payload=call.call_args.args[1]
            self.assertNotIn('attendees',payload);self.assertEqual(payload['visibility'],'private')
            event_id=payload['id']
        with patch.object(client,'request',return_value={'items':[{'id':event_id}]}) as call:
            self.assertEqual(client.sync(plan)['existing'],['s1']);self.assertEqual(call.call_count,1)
        event=plan['schedule']['events'][0]
        with patch.object(client,'request',return_value={'items':[{'id':'other','start':{'dateTime':event['start']},'end':{'dateTime':event['end']}}]}) as call:
            self.assertEqual(len(client.sync(plan)['conflicts']),1);self.assertEqual(call.call_count,1)

    def test_google_partial_sync_preserves_created_ids(self):
        plan=self.sample_plan();plan['schedule']=schedule([scene('a'),scene('b',dependencies=['a'])],self.cfg)
        client=GoogleCalendar()
        with patch.object(client,'request',side_effect=[{'items':[]},{'id':'first'},ProviderError('Provider HTTP 503')]):
            result=client.sync(plan)
        self.assertEqual(result['created'][0]['event_id'],'first')
        self.assertEqual(result['stopped_at'],'b')
        self.assertIn('503',result['error'])

    def test_http_auth_and_preview_no_external_write(self):
        (self.root/'story.txt').write_text('A Troy story')
        server=ProductionServer(('127.0.0.1',0),self.root)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(server.pool.shutdown);self.addCleanup(server.shutdown)
        base='http://127.0.0.1:'+str(server.server_port)
        with urlopen(base) as r:self.assertIn(b'From scene to shoot',r.read())
        with urlopen(base+'/api/config') as r:self.assertEqual(json.load(r)['story'],self.root.name)
        with self.assertRaises(HTTPError) as caught:urlopen(Request(base+'/api/calendar-sync',data=b'{}',headers={'Content-Type':'application/json'}))
        self.assertEqual(caught.exception.code,403);caught.exception.close()
        with self.assertRaises(HTTPError) as caught:urlopen(Request(base,headers={'Host':'evil.example'}))
        self.assertEqual(caught.exception.code,403);caught.exception.close()
        plan=self.sample_plan();plan.update({'breakdown':breakdown(),'warnings':[]})
        server.plans[plan['id']]=plan
        with urlopen(base+'/export/'+plan['id']+'/calendar.ics') as response:
            self.assertIn(b'BEGIN:VEVENT',response.read())
        request=Request(base+'/api/recalculate',data=json.dumps({'id':plan['id'],'config':self.cfg,'budget_items':breakdown()['budget_items']}).encode(),headers={'Content-Type':'application/json','X-Storyforge-Token':server.csrf})
        with urlopen(request) as response: updated=json.load(response)
        self.assertEqual(updated['budget']['total_low'],345.35)
        self.assertTrue((self.root/'production'/'plans'/(updated['id']+'.json')).is_file())

if __name__=='__main__':unittest.main()
