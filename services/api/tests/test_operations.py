import json
from pathlib import Path
from datetime import timedelta
from uuid import UUID,uuid4
import pytest
from sqlalchemy import select,text
from fastapi import HTTPException
from app.cli import demo_principal
from app.core.db import transaction
from app.core.auth import Principal,resolve_scope
from app.core.models import World,TABLES,now
from app.bootstrap import uid
from app.core.records import get,insert
from app.core.settings import settings
from app.jobs.service import enqueue,reconcile
from app.jobs.tasks import execute
from app.domains.contracts import RecordInput
from app.domains.crud import create_record
from app.ai.monitor import authorize_autonomy,investigate_triggers
from app.ai.orchestrator import grounded_check

def test_populated_other_tenant_and_facility_write_denied():
    p=demo_principal()
    with transaction(p.user_id,p.organization_id) as db:
        assert not db.get(World,uid('isolation-world'))
        assert not db.get(TABLES['assets'],uid('isolation-asset'))
        result=db.execute(text("UPDATE assets SET name='cross tenant hacked' WHERE id=:id"),{'id':uid('isolation-asset')})
        assert result.rowcount==0
        with pytest.raises(Exception):
            with db.begin_nested():
                db.add(TABLES['assets'](organization_id=uid('isolation-org'),facility_id=uid('isolation-fac'),world_id=uid('isolation-world'),name='Unauthorized',data={}))
                db.flush()

def test_expired_worker_lease_recovers_without_duplicate_effect():
    p=demo_principal()
    with transaction(p.user_id,p.organization_id) as db:
        w=db.scalar(select(World).where(World.code=='extended_v1'));s=resolve_scope(db,p,w.id)
        j=enqueue(db,s,'report',{'hours':24},'recovery-'+str(uuid4()))
        row=get(db,s,'jobs',j['job_id']);row.status='running';row.data={**row.data,'lease_until':(now()-timedelta(seconds=1)).isoformat()}
        assert reconcile(db,p)['recovered']>=1
    assert execute.run(j['job_id'])['status']=='completed'
    assert execute.run(j['job_id'])['status']=='already_finished_or_unavailable'

def test_monitor_cooldown_and_autonomy_require_server_flag(monkeypatch):
    p=demo_principal()
    with transaction(p.user_id,p.organization_id) as db:
        fixture=db.begin_nested()
        w=db.scalar(select(World).where(World.code=='extended_v1'));s=resolve_scope(db,p,w.id)
        # Exercise a fresh cooldown window without persisting changes to the demo clock.
        w.as_of+=timedelta(days=2)
        policy=create_record(db,s,'agent_policies',RecordInput(name='Test monitor',data={'monitor_enabled':True,'autonomous_task_creation':False,'categories':['waste'],'daily_brief':True,'max_tasks_per_day':0}))
        first=investigate_triggers(db,p);second=investigate_triggers(db,p)
        assert first['queued_runs'] and not second['queued_runs']
        run=get(db,s,'agent_runs',first['queued_runs'][0]);monkeypatch.setattr(settings(),'agent_autonomous_writes_enabled',False)
        with pytest.raises(HTTPException):authorize_autonomy(db,s,run,None)
        # This test does not dispatch provider jobs; cancel them before committing the fixture.
        for rid in first['queued_runs']:
            run=get(db,s,'agent_runs',rid);run.status='cancelled'
        policy_row=get(db,s,'agent_policies',policy['id']);policy_row.event_at=s.world.as_of+timedelta(days=1)
        fixture.rollback()

def test_numeric_dates_rounding_and_failed_write_grounding():
    result={'data':{'value':1699.4154,'cutoff':'2025-06-29T23:00:00Z','coverage_pct':100},'evidence':[]}
    assert grounded_check('Observed 1699.4154 kWh, 100 percent coverage at June 30 04:30 IST.',[result])[0]
    assert not grounded_check('The task was created.',[{'tool':'create_action','error':{'message':'denied'},'data':{}}])[0]

def test_http_sse_resume_and_cancellation():
    from fastapi.testclient import TestClient
    from app.main import app
    credentials=json.loads(Path(settings().demo_credentials_path).read_text())['hospital_admin']
    c=TestClient(app);response=c.post('/api/v1/auth/login',json={'email':credentials['email'],'password':credentials['password']});assert response.status_code==200
    c.headers['X-CSRF-Token']=response.json()['csrf_token']
    w=next(v for v in c.get('/api/v1/worlds').json()['items'] if v['code']=='extended_v1')['id']
    conversation=c.post('/api/v1/conversations',params={'world_id':w},json={'name':'SSE cancellation fixture'}).json()
    response=c.post('/api/v1/conversations/'+conversation['id']+'/messages',params={'world_id':w},json={'content':'Read water reserves','mode':'ask'});assert response.status_code==202
    rid=response.json()['id'];cancel=c.post('/api/v1/agent-runs/'+rid+'/cancel',params={'world_id':w});assert cancel.status_code==200 and cancel.json()['status']=='cancelled'
    stream=c.get('/api/v1/agent-runs/'+rid+'/events',params={'world_id':w});assert stream.status_code==200 and 'event: run_completed' in stream.text
    cursor=cancel.json()['data']['events'][-1]['id']
    resumed=c.get('/api/v1/agent-runs/'+rid+'/events',params={'world_id':w},headers={'Last-Event-ID':str(cursor)})
    assert resumed.status_code==200 and 'event:' not in resumed.text

def test_provider_retry_budget_is_bounded(monkeypatch):
    from test_ai import new_run,FixtureProvider
    p,w,r=new_run()
    monkeypatch.setattr(settings(),'job_max_retries',1)
    monkeypatch.setattr('app.ai.orchestrator.OpenAICompatible',lambda:FixtureProvider([TimeoutError('Provider unavailable fixture')]))
    with transaction(p.user_id,p.organization_id) as db:
        s=resolve_scope(db,p,w);job=enqueue(db,s,'agent',{'run_id':r},'bounded-provider-'+str(uuid4()))
    result=execute.run(job['job_id']);assert result['status']=='failed'
    assert execute.run(job['job_id'])['status']=='already_finished_or_unavailable'
    with transaction(p.user_id,p.organization_id) as db:
        j=get(db,resolve_scope(db,p,w),'jobs',job['job_id']);assert j.data['attempts']==1 and 'retry budget' in j.data['error']

@pytest.mark.asyncio
async def test_success_response_is_sent_after_database_commit():
    import httpx
    from app.main import app
    p=demo_principal();credentials=json.loads(Path(settings().demo_credentials_path).read_text())['hospital_admin']
    with transaction(p.user_id,p.organization_id) as db:
        world_id=db.scalar(select(World.id).where(World.code=='extended_v1'))
    observed=[]
    async def probe(scope,receive,send):
        async def committed_send(message):
            if scope['path']=='/api/v1/records/assets' and message['type']=='http.response.body' and message.get('body'):
                body=json.loads(message['body'])
                if 'id' in body:
                    with transaction(p.user_id,p.organization_id) as db:
                        row=get(db,resolve_scope(db,p,world_id),'assets',body['id'])
                        observed.append(row.name)
            await send(message)
        await app(scope,receive,committed_send)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=probe),base_url='http://testserver') as c:
        login=await c.post('/api/v1/auth/login',json={'email':credentials['email'],'password':credentials['password']})
        c.headers['X-CSRF-Token']=login.json()['csrf_token']
        response=await c.post('/api/v1/records/assets',params={'world_id':str(world_id)},json={'name':'Response commit fixture','zone_code':'WARD_A','data':{'kind':'pump','mode':'operational','critical':False}})
        assert response.status_code==201 and observed==['Response commit fixture']

def test_waste_totals_include_batches_beyond_detail_limit():
    from app.domains.state import waste_state
    p=demo_principal()
    with transaction(p.user_id,p.organization_id) as db:
        fixture=db.begin_nested();w=db.scalar(select(World).where(World.code=='extended_v1'));s=resolve_scope(db,p,w.id)
        before=waste_state(db,s);initial=sum(c['stock_kg'] for c in before['categories'])
        bins=TABLES['waste_bins'];bin=db.scalar(select(bins).where(bins.world_id==w.id,bins.zone_code=='WARD_A',bins.data['category'].as_string()=='red'))
        # Bulk fixtures retain the >500 boundary without 1,002 remote DB round trips.
        from sqlalchemy.dialects.postgresql import insert as bulk_insert
        batches=[];movements=[]
        for _ in range(501):
            batch_id=uuid4()
            common={**s.keys,'event_at':s.world.as_of,'zone_code':'WARD_A'}
            batches.append({**common,'id':batch_id,'name':'Detail-limit regression batch',
                            'data':{'category':'red','generated_kg':1,'bin_id':str(bin.id)}})
            movements.append({**common,'parent_id':batch_id,'name':'Recorded generation',
                              'data':{'kind':'generation'},'value':1,'unit':'kg'})
        db.execute(bulk_insert(TABLES['waste_batches']).values(batches))
        db.execute(bulk_insert(TABLES['waste_movements']).values(movements))
        result=waste_state(db,s)
        assert result['truncated'] and len(result['batches'])==500
        assert result['batch_count']==before['batch_count']+501 and not result['category_totals_partial']
        assert abs(sum(c['stock_kg'] for c in result['categories'])-initial-501)<1e-8
        fixture.rollback()
