"""Production exports and explicit Google Calendar sync."""
from __future__ import annotations
import csv
from datetime import datetime, timezone, timedelta
import hashlib
import io
import json
import os
from urllib.parse import urlencode, quote
from .production_research import request_json, ProviderError


def event_id(plan, event):
    return hashlib.sha256((plan['title']+'|'+event['scene_id']+'|'+event['start']).encode()).hexdigest()


def utc(value):
    return datetime.fromisoformat(value).astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def ics_escape(value):
    return str(value).replace('\\','\\\\').replace('\r','').replace('\n','\\n').replace(';','\\;').replace(',','\\,')


def calendar_ics(plan):
    lines=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//StoryForge//Production//EN','CALSCALE:GREGORIAN','METHOD:PUBLISH']
    for e in plan['schedule']['events']:
        lines += ['BEGIN:VEVENT','UID:'+event_id(plan,e)+'@storyforge.local','DTSTAMP:'+utc(plan['created_at']),
                  'DTSTART:'+utc(e['start']),'DTEND:'+utc(e['end']),'SUMMARY:'+ics_escape(e['summary']),
                  'LOCATION:'+ics_escape(e['location']),'DESCRIPTION:'+ics_escape('Tentative production shoot. Scene '+e['scene_id']+'. Cast: '+', '.join(e['cast'])+'. Verify permits, venue and availability.'),'STATUS:TENTATIVE','END:VEVENT']
    lines+=['END:VCALENDAR']
    folded=[]
    for line in lines:
        # Fold by octet, preserving complete UTF-8 characters (RFC 5545).
        chunk='';limit=75
        for char in line:
            if len((chunk+char).encode())>limit:
                folded.append(chunk);chunk=' '+char;limit=75
            else:chunk+=char
        folded.append(chunk)
    return ('\r\n'.join(folded)+'\r\n').encode()


def csv_bytes(rows, fields):
    stream=io.StringIO(newline='');writer=csv.DictWriter(stream,fieldnames=fields,extrasaction='ignore');writer.writeheader()
    for row in rows:
        sanitized={}
        for key,value in row.items():
            if isinstance(value,(list,dict)):value=json.dumps(value,ensure_ascii=False)
            if isinstance(value,str) and value.lstrip().startswith(('=','+','-','@')):value="'"+value
            sanitized[key]=value
        writer.writerow(sanitized)
    return stream.getvalue().encode('utf-8-sig')


def export(plan, kind):
    if kind=='calendar.ics': return calendar_ics(plan),'text/calendar; charset=utf-8'
    if kind=='budget.csv': return csv_bytes(plan['budget']['items'],['category','description','quantity','unit','low_rate','high_rate','low_total','high_total','basis','status']),'text/csv; charset=utf-8'
    if kind=='schedule.csv': return csv_bytes(plan['schedule']['events'],['scene_id','summary','start','end','location','cast','setup_move_minutes','meal_before','status']),'text/csv; charset=utf-8'
    if kind=='tasks.csv':
        return csv_bytes(plan['recommendations'].get('legal_logistics',[]),['task','owner','source_ids','status','verification']),'text/csv; charset=utf-8'
    if kind=='plan.json': return json.dumps(plan,ensure_ascii=False,indent=2).encode(),'application/json'
    if kind=='call-sheets.txt':
        lines=[plan['title'],'DRAFT CALL SHEETS — confirm crew, contacts, venue, safety plan and permissions before issue.']
        for e in plan['schedule']['events']:
            lines+=['',e['start']+' — '+e['end'],e['scene_id']+': '+e['summary'],'Location: '+e['location'],'Cast: '+', '.join(e['cast']),'Setup/move: '+str(e['setup_move_minutes'])+' minutes before scene','Meal before: '+str(e['meal_before']),'Emergency contact / nearest hospital / parking / weather / crew call: TO CONFIRM']
        return '\n'.join(lines).encode(),'text/plain; charset=utf-8'
    raise ValueError('Unknown export')


class GoogleCalendar:
    """Tokens stay in process memory or server environment, never in plan artifacts."""
    def __init__(self):
        self.access=os.getenv('GOOGLE_CALENDAR_ACCESS_TOKEN','')
        self.refresh=os.getenv('GOOGLE_CALENDAR_REFRESH_TOKEN','')
        self.expires=0

    def token(self):
        import time
        if self.access and (not self.expires or time.time()<self.expires-60):return self.access
        if self.refresh and os.getenv('GOOGLE_CLIENT_ID') and os.getenv('GOOGLE_CLIENT_SECRET'):
            self.accept(self.form_token({'grant_type':'refresh_token','refresh_token':self.refresh}))
            return self.access
        raise ProviderError('Connect Google Calendar first, or configure server-side Calendar OAuth credentials. ICS export works without Google authorization.')

    def form_token(self, values):
        from urllib.request import Request,urlopen
        from urllib.error import HTTPError,URLError
        values={**values,'client_id':os.getenv('GOOGLE_CLIENT_ID',''),'client_secret':os.getenv('GOOGLE_CLIENT_SECRET','')}
        try:
            with urlopen(Request('https://oauth2.googleapis.com/token',data=urlencode(values).encode(),headers={'Content-Type':'application/x-www-form-urlencoded'}),timeout=30) as response:
                return json.load(response)
        except (HTTPError,URLError,OSError,ValueError):raise ProviderError('Google authorization failed; check client credentials, consent and redirect URI') from None

    def accept(self, value):
        import time
        self.access=value['access_token'];self.refresh=value.get('refresh_token',self.refresh)
        self.expires=time.time()+value.get('expires_in',3600)

    def request(self, path, payload=None):
        return request_json('https://www.googleapis.com/calendar/v3/'+path,payload,{'Authorization':'Bearer '+self.token(),'Content-Type':'application/json'},timeout=30)

    def sync(self, plan, calendar='primary'):
        # Preview is supplied by the application; this is only called by its explicit sync action.
        events=plan['schedule']['events']
        if not events:return {'created':[],'existing':[],'conflicts':[]}
        if plan['schedule']['unscheduled']:raise ValueError('Resolve unscheduled scenes before syncing')
        path='calendars/'+quote(calendar,safe='')+'/events'
        lo=min(e['start'] for e in events);hi=max(e['end'] for e in events)
        query={'timeMin':lo,'timeMax':hi,'singleEvents':'true','maxResults':1000}
        existing=[]
        for page in range(6):
            data=self.request(path+'?'+urlencode(query));existing+=data.get('items',[])
            if not data.get('nextPageToken'):break
            query['pageToken']=data['nextPageToken']
        else:raise ValueError('Calendar range too large to check safely; use a dedicated production calendar')
        known={e['id'] for e in existing};out={'created':[],'existing':[],'conflicts':[]}
        from zoneinfo import ZoneInfo
        def edge(raw):
            if 'dateTime' in raw:return datetime.fromisoformat(raw['dateTime'].replace('Z','+00:00'))
            return datetime.fromisoformat(raw['date']).replace(tzinfo=ZoneInfo(plan['config']['timezone']))
        for e in events:
            ident=event_id(plan,e)
            if ident in known:out['existing'].append(e['scene_id']);continue
            conflicts=[x for x in existing if x.get('status')!='cancelled' and x.get('transparency')!='transparent' and edge(x['start'])<datetime.fromisoformat(e['end']) and edge(x['end'])>datetime.fromisoformat(e['start'])]
            if conflicts:
                out['conflicts'].append({'scene_id':e['scene_id'],'message':'Existing calendar event overlaps; resolve before sync'});continue
            body={'id':ident,'summary':e['summary'],'location':e['location'],'description':'StoryForge draft production plan. Scene '+e['scene_id']+'. Cast: '+', '.join(e['cast']),
                  'start':{'dateTime':e['start'],'timeZone':plan['config']['timezone']},'end':{'dateTime':e['end'],'timeZone':plan['config']['timezone']},'status':'tentative','visibility':'private','extendedProperties':{'private':{'storyforge_plan':plan['id'],'scene_id':e['scene_id']}}}
            try:result=self.request(path+'?sendUpdates=none',body)
            except ProviderError as exc:
                if str(exc)=='Provider HTTP 409':out['existing'].append(e['scene_id']);continue
                # Preserve partial results if the provider fails after some inserts.
                out['error']=str(exc);out['stopped_at']=e['scene_id'];break
            out['created'].append({'scene_id':e['scene_id'],'event_id':result.get('id',ident),'url':result.get('htmlLink','')})
        return out
