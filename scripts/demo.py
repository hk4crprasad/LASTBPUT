"""A repeatable HTTP walkthrough using actual persistent services and job outcomes."""
import argparse,json,time,hashlib
from pathlib import Path
from uuid import uuid4
from datetime import datetime,timedelta
import httpx
p=argparse.ArgumentParser();p.add_argument('--url',default='http://localhost:3000');p.add_argument('--credentials',default='.local/demo-credentials.json');p.add_argument('--llm',action='store_true');args=p.parse_args()
creds=json.loads(Path(args.credentials).read_text())
def login(role):
 c=httpx.Client(base_url=args.url+'/api/v1',timeout=30);r=c.post('/auth/login',json={'email':creds[role]['email'],'password':creds[role]['password']});r.raise_for_status();c.headers['X-CSRF-Token']=r.json()['csrf_token'];return c
c=login('hospital_admin');world=next(w for w in c.get('/worlds').json()['items'] if w['code']=='extended_v1');wid=world['id']
def request(method,path,body=None,client=c):
 r=client.request(method,path,params={'world_id':wid},json=body,headers={'Idempotency-Key':str(uuid4())});r.raise_for_status();return r.json()
def job(path,body):
 record=request('POST',path,body);jid=record['job_id'];deadline=time.monotonic()+150
 while time.monotonic()<deadline:
  result=request('GET','/jobs/'+jid)
  if result['status']=='completed':return result['data']['result']
  if result['status'] in {'failed','cancelled','waiting_provider'}:raise RuntimeError(json.dumps({'job_id':jid,'status':result['status'],'error':result['data'].get('error')}))
  time.sleep(1)
 raise TimeoutError('Job did not complete; inspect '+jid)
overview=request('GET','/overview');print(json.dumps({'world':world['code'],'as_of':world['as_of'],'usage':overview['metrics']}))
scenario={'name':'HTTP demo outage '+str(uuid4())[:8],'horizon_hours':6,'events':[{'kind':'grid_outage','duration_hours':6},{'kind':'pump_failure','duration_hours':6}]}
a=job('/simulations',scenario);b=job('/simulations',{**scenario,'name':'HTTP alternate '+str(uuid4())[:8],'events':[]});comparison=request('POST','/simulations/compare',{'run_ids':[a['id'],b['id']]});print(json.dumps({'simulation_ids':[a['id'],b['id']],'comparison':comparison}))
owner=creds['operations_supervisor']['user_id'];action=request('POST','/actions',{'name':'HTTP demo pump inspection','category':'maintenance','zone_code':'WARD_A','owner_id':owner,'due_at':(datetime.fromisoformat(world['as_of'])+timedelta(days=1)).isoformat(),'description':'Explicit synthetic demonstration task; inspect recorded reserve/pump evidence.'})
for state in ['acknowledged','in_progress','resolved']:action=request('POST','/actions/'+action['id']+'/transition',{'state':state,'expected_version':action['version'],'reason':'HTTP demo recorded progression'})
reviewer=login('operations_supervisor')
for state in ['verified','closed']:action=request('POST','/actions/'+action['id']+'/transition',{'state':state,'expected_version':action['version'],'reason':'Independent review completed','evidence':'Synthetic inspection record reviewed; no real equipment action claimed.'},reviewer)
print(json.dumps({'action_id':action['id'],'actual_status':action['status']}))
report=job('/reports',{'name':'HTTP demo report','hours':24})
for key in ['csv_file_id','html_file_id','pdf_file_id']:
 r=c.get('/files/'+report['data'][key]+'/download',params={'world_id':wid});r.raise_for_status();assert r.content
 if key=='pdf_file_id':assert r.content.startswith(b'%PDF-')
 print(json.dumps({'artifact':key,'bytes':len(r.content),'sha256':hashlib.sha256(r.content).hexdigest()}))
if args.llm:
 conversation=request('POST','/conversations',{'name':'HTTP demo investigation'})
 run=request('POST','/conversations/'+conversation['id']+'/messages',{'content':'Investigate recorded waste deadline risk using get_waste_state and alert evidence, run a relevant six-hour scenario and draft an inspection proposal for WARD_A.','mode':'investigate'})
 deadline=time.monotonic()+150
 while time.monotonic()<deadline:
  r=request('GET','/agent-runs/'+run['id'])
  if r['status'] not in {'queued','running'}:
   tools=r['data'].get('tool_results',[])
   print(json.dumps({'run_id':r['id'],'status':r['status'],'tools':[t['tool'] for t in tools],'answer':r['data'].get('answer'),'error':r['data'].get('error')}));assert r['status']=='completed'
   assert {'get_waste_state','run_what_if','draft_action_plan'}<={t['tool'] for t in tools if 'error' not in t}
   proposal_id=next(t['data']['id'] for t in tools if t['tool']=='draft_action_plan' and 'error' not in t)
   proposal=request('GET','/records/action_proposals/'+proposal_id)
   approved=request('POST','/action-proposals/'+proposal_id+'/approve',{'expected_version':proposal['version'],'review_evidence':'Synthetic waste deadline evidence and scenario reviewed by the demo administrator.','action':{'name':'HTTP reviewed waste inspection','category':'waste','zone_code':'WARD_A','owner_id':owner,'due_at':(datetime.fromisoformat(world['as_of'])+timedelta(hours=1)).isoformat(),'description':'Software follow-up from the actual saved proposal; no physical pickup claimed.','alert_id':proposal['data'].get('alert_id')}})
   assert approved['proposal']['status']=='approved' and approved['action']['status']=='open'
   print(json.dumps({'proposal_id':proposal_id,'proposal_status':approved['proposal']['status'],'permitted_action_id':approved['action']['id'],'action_status':approved['action']['status']}));break
  time.sleep(1)
 else:raise TimeoutError('Agent run still pending')
print('PASS actual HTTP demo, action lifecycle and stored report artifacts')
