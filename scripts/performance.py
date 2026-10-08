"""Warm real HTTP measurements; reads generated demo credentials without printing them."""
import argparse,json,time,statistics,sys,os
from pathlib import Path
import httpx
p=argparse.ArgumentParser();p.add_argument('--url',default='http://localhost:3000');p.add_argument('--credentials',default='.local/demo-credentials.json');args=p.parse_args()
c=httpx.Client(base_url=args.url+'/api/v1',timeout=15);cr=json.loads(Path(args.credentials).read_text())['hospital_admin']
c.post('/auth/login',json={'email':cr['email'],'password':cr['password']}).raise_for_status()
worlds=c.get('/worlds').json()['items'];results=[]
for w in worlds:
 for path,params,target in [('/overview',{},2),('/metrics/series',{'metric':'energy.interval_kwh','limit':200},3)]:
  c.get(path,params={'world_id':w['id'],**params}).raise_for_status();samples=[]
  for _ in range(5):
   start=time.perf_counter();r=c.get(path,params={'world_id':w['id'],**params});r.raise_for_status();samples.append(time.perf_counter()-start)
  results.append({'world':w['code'],'endpoint':path,'seconds':samples,'median_seconds':statistics.median(samples),'max_seconds':max(samples),'target_seconds':target,'passed':max(samples)<target})
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'services/api'))
from app.simulation.engine import Baseline,Tank,Scenario,run_engine
from datetime import datetime,timezone
baseline=Baseline(as_of=datetime.now(timezone.utc),snapshot_version=1,demand_source='Performance fixture, not actual hospital prediction',tanks=[Tank(name='potable',kind='potable',capacity_l=30000,reserve_l=30000,inflow_lph=0,essential_lph=3000)],essential_load_kw=60,battery_deliverable_kwh=120)
a=time.perf_counter();run_engine(baseline,Scenario(name='72-hour performance scenario',horizon_hours=72));elapsed=time.perf_counter()-a
results.append({'operation':'72_hour_engine_low_central_high_plus_baseline','seconds':elapsed,'target_seconds':5,'passed':elapsed<5})
print(json.dumps({'measurements':results,'all_passed':all(r['passed'] for r in results)},indent=2))
