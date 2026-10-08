from datetime import datetime,timedelta
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text, delete
from app.core.auth import login, request_db, resolve_scope, digest, ADMIN
from app.core.db import Session
from app.core.models import Facility, Organization, World, Metric, Grant, LoginSession, TABLES
from app.core.records import serialize, query, audit
from app.core.settings import settings

router=APIRouter(prefix='/api/v1')
class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid')
class LoginInput(Strict):
    email:str=Field(max_length=200)
    password:str=Field(max_length=200)

@router.post('/auth/login')
def auth_login(body:LoginInput,response:Response):
    with Session.begin() as db:
        p,token,csrf=login(db,body.email,body.password)
    response.set_cookie('greenops_session',token,httponly=True,secure=settings().cookie_secure,samesite='lax',max_age=28800,path='/')
    response.set_cookie('greenops_csrf',csrf,httponly=False,secure=settings().cookie_secure,samesite='lax',max_age=28800,path='/')
    return {'user':{'id':str(p.user_id),'organization_id':str(p.organization_id),'name':p.name,'role':p.role},'csrf_token':csrf}

from app.core.demo_login import DemoRole, DEMO_ROLES, credentials as demo_credentials

class DemoLoginInput(Strict):
    role:DemoRole

@router.get('/auth/demo-accounts')
def demo_accounts(response:Response):
    response.headers['Cache-Control']='no-store'
    if settings().app_mode!='demo':return {'enabled':False,'items':[]}
    saved=demo_credentials()
    return {'enabled':True,'items':[{'role':role,'name':name,'description':description,'email':saved[role]['email']}
                                   for role,(name,description) in DEMO_ROLES.items()]}

@router.post('/auth/demo-login')
def demo_login(body:DemoLoginInput,response:Response,request:Request):
    saved=demo_credentials()[body.role]
    origin=request.headers.get('origin')
    if origin and origin not in settings().cors_origins.split(','):
        raise HTTPException(403,'Origin not allowed')
    with Session.begin() as db:
        p,token,csrf=login(db,saved['email'],saved['password'])
        if p.role!=body.role or str(p.user_id)!=saved['user_id']:
            raise HTTPException(403,'Demo account identity mismatch')
    response.headers['Cache-Control']='no-store'
    response.set_cookie('greenops_session',token,httponly=True,secure=settings().cookie_secure,samesite='lax',max_age=28800,path='/')
    response.set_cookie('greenops_csrf',csrf,httponly=False,secure=settings().cookie_secure,samesite='lax',max_age=28800,path='/')
    return {'user':{'id':str(p.user_id),'organization_id':str(p.organization_id),'name':p.name,'role':p.role},'csrf_token':csrf}

@router.post('/auth/logout')
def logout(request:Request,response:Response,ctx=Depends(request_db,scope="function")):
    db,p=ctx
    db.execute(delete(LoginSession).where(LoginSession.token_hash==digest(request.cookies.get('greenops_session',''))))
    response.delete_cookie('greenops_session');response.delete_cookie('greenops_csrf')
    return {'status':'logged_out'}

@router.get('/me')
def me(ctx=Depends(request_db,scope="function")):
    db,p=ctx
    return {'id':str(p.user_id),'organization_id':str(p.organization_id),'name':p.name,'email':p.email,'role':p.role,
            'grants':[serialize(g) for g in db.scalars(select(Grant))],
            'llm':{'enabled':settings().llm_enabled,'configured':bool(settings().openai_api_key and settings().openai_chat_model),
                   'tools':settings().llm_supports_tools,'monitor_writes':settings().agent_autonomous_writes_enabled}}

@router.get('/organizations')
def organizations(ctx=Depends(request_db,scope="function")):
    return {'items':[serialize(v) for v in ctx[0].scalars(select(Organization))]}

@router.get('/facilities')
def facilities(ctx=Depends(request_db,scope="function")):
    return {'items':[serialize(v) for v in ctx[0].scalars(select(Facility))]}

@router.get('/worlds')
def worlds(ctx=Depends(request_db,scope="function")):
    return {'items':[serialize(v) for v in ctx[0].scalars(select(World).order_by(World.code))]}

@router.get('/metric-catalog')
def metrics(ctx=Depends(request_db,scope="function")):
    return {'items':[serialize(v) for v in ctx[0].scalars(select(Metric))]}

@router.get('/quality-events')
def quality(world_id:UUID,limit:int=100,offset:int=0,ctx=Depends(request_db,scope="function")):
    db,p=ctx;scope=resolve_scope(db,p,world_id)
    if not 1<=limit<=500 or offset<0:raise HTTPException(422,'Invalid pagination')
    return {'items':[serialize(v) for v in query(db,scope,'quality_events',limit,offset)],'limit':limit,'offset':offset}

@router.get('/demo/clock')
def clock(world_id:UUID,ctx=Depends(request_db,scope="function")):
    return serialize(resolve_scope(ctx[0],ctx[1],world_id).world)
class ClockInput(Strict):
    operation:str=Field(pattern='^(pause|advance|reset|replay)$')
    hours:float=Field(default=1,ge=0,le=4320)

@router.post('/demo/clock')
@router.post('/demo/replay')
def clock_update(world_id:UUID,body:ClockInput,ctx=Depends(request_db,scope="function")):
    db,p=ctx;scope=resolve_scope(db,p,world_id);scope.require('facility')
    if settings().app_mode!='demo':raise HTTPException(403,'Demo clock unavailable outside demo')
    before=serialize(scope.world)
    if body.operation=='pause':scope.world.paused=True
    elif body.operation=='reset':scope.world.as_of=scope.world.initial_as_of
    elif body.operation=='advance':scope.world.as_of+=timedelta(hours=body.hours)
    else:scope.world.as_of=scope.world.initial_as_of-timedelta(hours=body.hours)
    scope.world.version+=1
    audit(db,scope,body.operation,'worlds',scope.world.id,before,serialize(scope.world))
    return serialize(scope.world)

@router.get('/evidence/{record_id}')
def evidence(record_id:UUID,world_id:UUID,ctx=Depends(request_db,scope="function")):
    db,p=ctx;scope=resolve_scope(db,p,world_id)
    for table in ['source_events']+sorted(set(TABLES)-{'audit_events','outbox_events','stored_files'}):
        obj=db.scalar(select(TABLES[table]).where(TABLES[table].world_id==world_id,TABLES[table].id==record_id))
        if obj:
            if table in {'messages','conversations','agent_runs','tool_calls','ai_usage','jobs'} and obj.owner_id!=p.user_id and p.role not in ADMIN:raise HTTPException(403,'Run owner required')
            return {'table':table,'record':serialize(obj)}
    raise HTTPException(404,'Evidence unavailable')

@router.get('/overview')
def overview_route(world_id:UUID,start:datetime|None=None,end:datetime|None=None,ctx=Depends(request_db,scope="function")):
    from app.domains.metrics import overview
    return overview(ctx[0],resolve_scope(ctx[0],ctx[1],world_id),start,end)

@router.get('/metrics/series')
def series_route(world_id:UUID,metric:str,start:datetime|None=None,end:datetime|None=None,bucket:str='hour',zone_ids:str='',limit:int=200,offset:int=0,ctx=Depends(request_db,scope="function")):
    from app.domains.metrics import series
    return series(ctx[0],resolve_scope(ctx[0],ctx[1],world_id),metric,start,end,bucket,[z for z in zone_ids.split(',') if z],limit,offset)

@router.get('/metrics/comparison')
def comparison_route(world_id:UUID,metric:str,hours:int=24,ctx=Depends(request_db,scope="function")):
    from app.domains.metrics import series
    if not 1<=hours<=168:raise HTTPException(422,'hours must be 1–168')
    db,p=ctx;scope=resolve_scope(db,p,world_id);end=scope.world.as_of
    return {'current':series(db,scope,metric,end-timedelta(hours=hours),end,'hour',limit=500),
            'previous':series(db,scope,metric,end-timedelta(hours=hours*2),end-timedelta(hours=hours),'hour',limit=500)}

@router.get('/operational-snapshots')
def context_route(world_id:UUID,ctx=Depends(request_db,scope="function")):
    from app.domains.metrics import context
    return context(ctx[0],resolve_scope(ctx[0],ctx[1],world_id))

@router.get('/sustainability')
def sustainability_route(world_id:UUID,start:datetime|None=None,end:datetime|None=None,ctx=Depends(request_db,scope="function")):
    from app.domains.metrics import sustainability
    return sustainability(ctx[0],resolve_scope(ctx[0],ctx[1],world_id),start,end)

@router.get('/models')
def model_route(world_id:UUID,ctx=Depends(request_db,scope="function")):
    from app.analytics.service import models
    return models(ctx[0],resolve_scope(ctx[0],ctx[1],world_id))
@router.get('/models/{model_id}/evaluation')
def evaluation_route(model_id:str,world_id:UUID,ctx=Depends(request_db,scope="function")):
    from app.analytics.service import models
    items=models(ctx[0],resolve_scope(ctx[0],ctx[1],world_id))['items']
    item=next((x for x in items if x['model_id']==model_id),None)
    if not item:raise HTTPException(404,'Unknown model')
    return item
@router.get('/forecasts')
def forecasts_route(world_id:UUID,ctx=Depends(request_db,scope="function")):
    db,p=ctx;scope=resolve_scope(db,p,world_id)
    runs=query(db,scope,'forecast_runs',1)
    if not runs:return {'items':[],'status':'unavailable','reason':'Run explicit inference job'}
    cls=TABLES['forecast_points']
    return {'items':[serialize(r) for r in db.scalars(select(cls).where(cls.world_id==world_id,cls.parent_id==runs[0].id))],
            'run':serialize(runs[0]),'limitations':['Three hourly target points at 1, 6, 24 hours, not a daily trajectory or total.']}
@router.get('/alerts/{record_id}/evidence')
def alert_evidence_route(record_id:UUID,world_id:UUID,ctx=Depends(request_db,scope="function")):
    from app.core.records import get
    db,p=ctx;scope=resolve_scope(db,p,world_id)
    alert=get(db,scope,'alerts',record_id)
    cls=TABLES['alert_evidence']
    return {'alert':serialize(alert),'evidence':[serialize(v) for v in db.scalars(select(cls).where(cls.parent_id==record_id,cls.world_id==world_id))]}

from app.domains.actions import ActionInput,Transition
from app.simulation.engine import Scenario
class CompareInput(Strict):
    run_ids:list[UUID]=Field(min_length=2,max_length=5)
@router.post('/actions',status_code=201)
def action_create(world_id:UUID,body:ActionInput,request:Request,ctx=Depends(request_db,scope="function")):
    from app.domains.actions import create
    key=request.headers.get('Idempotency-Key')
    if not key or len(key)>150:raise HTTPException(422,'Idempotency-Key (1–150 characters) required')
    return create(ctx[0],resolve_scope(ctx[0],ctx[1],world_id),body,'user:'+str(ctx[1].user_id)+':'+key)
@router.post('/actions/{record_id}/transition')
def action_transition(record_id:UUID,world_id:UUID,body:Transition,ctx=Depends(request_db,scope="function")):
    from app.domains.actions import transition
    return transition(ctx[0],resolve_scope(ctx[0],ctx[1],world_id),record_id,body)
@router.post('/simulations',status_code=202)
def simulation_create(world_id:UUID,body:Scenario,request:Request,ctx=Depends(request_db,scope="function")):
    from app.jobs.service import enqueue
    db,p=ctx;scope=resolve_scope(db,p,world_id);scope.require('simulation')
    return enqueue(db,scope,'simulation',{'scenario':body.model_dump(mode='json')},request.headers.get('Idempotency-Key'))
@router.post('/simulations/compare')
def simulation_compare(world_id:UUID,body:CompareInput,ctx=Depends(request_db,scope="function")):
    from app.simulation.service import compare
    try:return compare(ctx[0],resolve_scope(ctx[0],ctx[1],world_id),body.run_ids)
    except ValueError as e:raise HTTPException(422,str(e))
@router.get('/simulations/{record_id}')
def simulation_get(record_id:UUID,world_id:UUID,ctx=Depends(request_db,scope="function")):
    from app.core.records import get
    return serialize(get(ctx[0],resolve_scope(ctx[0],ctx[1],world_id),'simulation_runs',record_id))
@router.get('/owners')
def owners(world_id:UUID,ctx=Depends(request_db,scope="function")):
    db,p=ctx;scope=resolve_scope(db,p,world_id)
    return {'items':[dict(r) for r in db.execute(text('SELECT * FROM scoped_owners(:org,:fac)'),{'org':p.organization_id,'fac':scope.world.facility_id}).mappings()]}

@router.get('/waste/state')
def waste_state_route(world_id:UUID,ctx=Depends(request_db,scope="function")):
    from app.domains.state import waste_state
    return waste_state(ctx[0],resolve_scope(ctx[0],ctx[1],world_id))
@router.get('/assets/state')
def assets_state_route(world_id:UUID,ctx=Depends(request_db,scope="function")):
    from app.domains.state import assets_state
    return assets_state(ctx[0],resolve_scope(ctx[0],ctx[1],world_id))
@router.get('/reserves')
def reserve_state_route(world_id:UUID,ctx=Depends(request_db,scope="function")):
    from app.domains.state import reserves_state
    return reserves_state(ctx[0],resolve_scope(ctx[0],ctx[1],world_id))
@router.get('/environment/state')
def environment_state_route(world_id:UUID,ctx=Depends(request_db,scope="function")):
    from app.domains.state import environment_state
    return environment_state(ctx[0],resolve_scope(ctx[0],ctx[1],world_id))
@router.get('/parking/state')
@router.get('/safety/state')
def parking_state_route(world_id:UUID,ctx=Depends(request_db,scope="function")):
    from app.domains.state import parking_safety
    return parking_safety(ctx[0],resolve_scope(ctx[0],ctx[1],world_id))

from app.domains.contracts import RecordInput,CONTRACTS
from app.domains.crud import READ_TABLES
from app.core.records import get
ALIASES={'waste/batches':'waste_batches','waste/pickups':'pickups','waste/bins':'waste_bins','assets':'assets','tanks':'tanks',
         'environment':'environment_readings','parking':'parking_areas','safety-incidents':'safety_incidents','maintenance-orders':'maintenance_orders',
         'zones':'zones','capacities':'zone_capacities','schedules':'operating_schedules','imports':'import_jobs','alerts':'alerts','actions':'actions',
         'action-proposals':'action_proposals','scenarios':'scenario_definitions','simulations':'simulation_runs','policies':'policy_versions',
         'tariffs':'tariff_versions','emission-factors':'emission_factor_versions','documents':'documents','training-runs':'training_runs',
         'agent-runs':'agent_runs','reports':'report_runs','jobs':'jobs','conversations':'conversations'}

def list_table(table):
    def handler(world_id:UUID,limit:int=100,offset:int=0,status:str|None=None,ctx=Depends(request_db,scope="function")):
        if not 1<=limit<=500 or offset<0:raise HTTPException(422,'Pagination out of bounds')
        db,p=ctx;scope=resolve_scope(db,p,world_id)
        rows=query(db,scope,table,limit+1,offset,status)
        if table in {'conversations','messages','agent_runs','tool_calls','ai_usage','jobs'}:
            rows=[r for r in rows if r.owner_id==p.user_id or p.role in ADMIN]
        return {'items':[serialize(v) for v in rows[:limit]],'limit':limit,'offset':offset,'truncated':len(rows)>limit}
    return handler
for path,table in ALIASES.items():
    router.add_api_route('/'+path,list_table(table),methods=['GET'],name='list_'+table)
for table in sorted(READ_TABLES):
    router.add_api_route('/records/'+table,list_table(table),methods=['GET'],name='ledger_'+table)

@router.get('/contracts')
def contracts_route(ctx=Depends(request_db,scope="function")):
    return {'items':{table:{'schema':contract.model_json_schema(),'permission_domain':domain} for table,(contract,domain) in CONTRACTS.items()}}
@router.post('/records/{table}',status_code=201)
def record_create(table:str,world_id:UUID,body:RecordInput,request:Request,ctx=Depends(request_db,scope="function")):
    from app.domains.crud import create_record
    return create_record(ctx[0],resolve_scope(ctx[0],ctx[1],world_id),table,body,request.headers.get('Idempotency-Key'))
@router.patch('/records/{table}/{record_id}')
def record_patch(table:str,record_id:UUID,world_id:UUID,body:RecordInput,ctx=Depends(request_db,scope="function")):
    from app.domains.crud import update_record
    return update_record(ctx[0],resolve_scope(ctx[0],ctx[1],world_id),table,record_id,body)
@router.delete('/records/{table}/{record_id}')
def record_delete(table:str,record_id:UUID,world_id:UUID,expected_version:int,ctx=Depends(request_db,scope="function")):
    from app.domains.crud import archive_record
    return archive_record(ctx[0],resolve_scope(ctx[0],ctx[1],world_id),table,record_id,expected_version)
@router.get('/records/{table}/{record_id}')
def record_get(table:str,record_id:UUID,world_id:UUID,ctx=Depends(request_db,scope="function")):
    if table not in READ_TABLES:raise HTTPException(404,'Unknown ledger')
    return serialize(get(ctx[0],resolve_scope(ctx[0],ctx[1],world_id),table,record_id))
@router.get('/facilities/{facility_id}/buildings')
def building_list(facility_id:UUID,world_id:UUID,ctx=Depends(request_db,scope="function")):
    scope=resolve_scope(ctx[0],ctx[1],world_id)
    if scope.world.facility_id!=facility_id:raise HTTPException(404,'Facility outside world')
    return {'items':[serialize(v) for v in query(ctx[0],scope,'buildings')]}

@router.get('/jobs/{record_id}')
def job_get(record_id:UUID,world_id:UUID,ctx=Depends(request_db,scope="function")):
    db,p=ctx;scope=resolve_scope(db,p,world_id);row=get(db,scope,'jobs',record_id)
    if row.owner_id!=p.user_id and p.role not in ADMIN:raise HTTPException(403,'Run owner required')
    return serialize(row)
@router.post('/imports',status_code=202)
def import_create(world_id:UUID,request:Request,ctx=Depends(request_db,scope="function")):
    from app.jobs.service import enqueue
    db,p=ctx;scope=resolve_scope(db,p,world_id);scope.require('imports')
    if scope.world.code not in {'base_v1','stress_v1'}:raise HTTPException(422,'Starter import only into its own base/stress world')
    return enqueue(db,scope,'import',{},request.headers.get('Idempotency-Key'))
@router.post('/forecasts',status_code=202)
def inference_create(world_id:UUID,request:Request,ctx=Depends(request_db,scope="function")):
    from app.jobs.service import enqueue
    db,p=ctx;scope=resolve_scope(db,p,world_id);scope.require('models')
    return enqueue(db,scope,'infer',{},request.headers.get('Idempotency-Key'))

class ConversationInput(Strict):
    name:str=Field(default='Operations conversation',min_length=1,max_length=150)
@router.post('/conversations',status_code=201)
def conversation_create(world_id:UUID,body:ConversationInput,ctx=Depends(request_db,scope="function")):
    from app.core.records import insert
    db,p=ctx;scope=resolve_scope(db,p,world_id)
    return serialize(insert(db,scope,'conversations',{},name=body.name,owner_id=p.user_id,zone_code=scope.zone_codes[0] if scope.zone_codes else None))
class MessageInput(Strict):
    content:str=Field(min_length=1,max_length=6000)
    mode:str=Field(default='ask',pattern='^(ask|investigate)$')
@router.get('/conversations/{record_id}/messages')
def conversation_messages(record_id:UUID,world_id:UUID,ctx=Depends(request_db,scope="function")):
    db,p=ctx;scope=resolve_scope(db,p,world_id);convo=get(db,scope,'conversations',record_id)
    if convo.owner_id!=p.user_id:raise HTTPException(403,'Conversation owner required')
    cls=TABLES['messages']
    return {'items':[serialize(v) for v in db.scalars(select(cls).where(cls.world_id==world_id,cls.parent_id==record_id).order_by(cls.created_at).limit(200))]}
@router.post('/conversations/{record_id}/messages',status_code=202)
def conversation_message(record_id:UUID,world_id:UUID,body:MessageInput,request:Request,ctx=Depends(request_db,scope="function")):
    from app.ai.orchestrator import start_run
    db,p=ctx;scope=resolve_scope(db,p,world_id)
    key=request.headers.get('Idempotency-Key')
    return start_run(db,scope,record_id,body.content,body.mode,key=f'user:{p.user_id}:{key}' if key else None)
@router.post('/agent-runs',status_code=202)
def agent_create(world_id:UUID,body:MessageInput,ctx=Depends(request_db,scope="function")):
    from app.ai.orchestrator import start_run
    from app.core.records import insert
    db,p=ctx;scope=resolve_scope(db,p,world_id)
    convo=insert(db,scope,'conversations',{},name=body.content[:150],owner_id=p.user_id,zone_code=scope.zone_codes[0] if scope.zone_codes else None)
    return start_run(db,scope,convo.id,body.content,body.mode)

def owned_run(db,p,world_id,record_id):
    scope=resolve_scope(db,p,world_id);run=get(db,scope,'agent_runs',record_id)
    if run.owner_id!=p.user_id and p.role not in ADMIN:raise HTTPException(403,'Run owner required')
    return scope,run
@router.get('/agent-runs/{record_id}')
def agent_get(record_id:UUID,world_id:UUID,ctx=Depends(request_db,scope="function")):
    return serialize(owned_run(ctx[0],ctx[1],world_id,record_id)[1])
@router.post('/agent-runs/{record_id}/cancel')
def agent_cancel(record_id:UUID,world_id:UUID,ctx=Depends(request_db,scope="function")):
    from app.ai.orchestrator import event
    db,p=ctx;scope,run=owned_run(db,p,world_id,record_id)
    if run.status in {'completed','cancelled'}:return serialize(run)
    run.status='cancelled';event(db,scope,run,'run_completed',{'status':'cancelled'})
    cls=TABLES['jobs']
    for job in db.scalars(select(cls).where(cls.world_id==world_id,cls.data['payload']['run_id'].as_string()==str(record_id))):job.status='cancelled'
    return serialize(run)
@router.get('/agent-runs/{record_id}/events')
def run_events(record_id:UUID,world_id:UUID,request:Request,after:int=0,ctx=Depends(request_db,scope="function")):
    from fastapi.responses import StreamingResponse
    import asyncio,json,time
    from app.core.db import transaction
    db,p=ctx;owned_run(db,p,world_id,record_id)
    try:last=max(after,int(request.headers.get('Last-Event-ID','0')))
    except ValueError:raise HTTPException(422,'Invalid event cursor')
    async def stream():
        nonlocal last
        started=time.monotonic()
        while time.monotonic()-started<settings().agent_max_run_seconds+30:
            if await request.is_disconnected():return
            with transaction(p.user_id,p.organization_id) as session:
                scope,run=owned_run(session,p,world_id,record_id)
                events=list(run.data.get('events',[]));status=run.status
            for event in events:
                if event['id']>last:
                    last=event['id'];yield f"id: {last}\nevent: {event['event']}\ndata: {json.dumps(event['data'])}\n\n"
            if status in {'completed','grounding_failed','cancelled','failed','configuration_required','waiting_provider'}:return
            yield ': heartbeat\n\n'
            await asyncio.sleep(1)
    return StreamingResponse(stream(),media_type='text/event-stream',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})

class ReportInput(Strict):
    name:str=Field(default='Operations daily brief',max_length=200)
    hours:int=Field(default=24,ge=1,le=720)
@router.post('/reports',status_code=202)
def report_create(world_id:UUID,body:ReportInput,request:Request,ctx=Depends(request_db,scope="function")):
    from app.jobs.service import enqueue
    db,p=ctx;scope=resolve_scope(db,p,world_id);scope.require('reports')
    return enqueue(db,scope,'report',body.model_dump(),request.headers.get('Idempotency-Key'))
@router.get('/reports/{record_id}')
def report_get(record_id:UUID,world_id:UUID,ctx=Depends(request_db,scope="function")):
    return serialize(get(ctx[0],resolve_scope(ctx[0],ctx[1],world_id),'report_runs',record_id))
@router.get('/files/{record_id}/download')
def download(record_id:UUID,world_id:UUID,ctx=Depends(request_db,scope="function")):
    from app.core.storage import read
    db,p=ctx;scope=resolve_scope(db,p,world_id);row,body=read(db,scope,record_id)
    filename=row.data['filename'].replace('"','').replace('\n','').replace('\r','')
    return Response(body,media_type=row.data['content_type'],headers={'Content-Disposition':f'attachment; filename="{filename}"',
                       'Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'",'X-Content-Type-Options':'nosniff'})
from fastapi import UploadFile,File
@router.post('/files',status_code=201)
async def upload(world_id:UUID,file:UploadFile=File(),ctx=Depends(request_db,scope="function")):
    from app.core.storage import store,MAX_FILE_BYTES
    db,p=ctx;scope=resolve_scope(db,p,world_id);scope.require('actions')
    body=await file.read(MAX_FILE_BYTES+1)
    try:return store(db,scope,(file.filename or 'evidence')[:150],body,file.content_type or 'application/octet-stream')
    except ValueError as e:raise HTTPException(422,str(e))

@router.post('/imports/csv',status_code=202)
async def csv_import(world_id:UUID,file:UploadFile=File(),ctx=Depends(request_db,scope="function")):
    import csv,hashlib,io
    from app.jobs.service import enqueue
    from app.domains.importer import PUBLIC_FIELDS
    db,p=ctx;scope=resolve_scope(db,p,world_id);scope.require('imports')
    body=await file.read(5*1024*1024+1)
    if len(body)>5*1024*1024:raise HTTPException(413,'CSV exceeds 5 MB')
    try:
        reader=csv.DictReader(io.StringIO(body.decode('utf-8-sig')))
        if set(reader.fieldnames or [])-PUBLIC_FIELDS:raise ValueError('Unallowlisted CSV fields; patient/private fields prohibited')
        rows=list(reader)
        if len(rows)>30000:raise ValueError('CSV row limit 30,000')
    except (ValueError,UnicodeDecodeError,csv.Error) as e:raise HTTPException(422,str(e))
    sha=hashlib.sha256(body).hexdigest()
    return enqueue(db,scope,'import',{'rows':rows,'dataset_code':'uploaded-'+sha,'sha256':sha},'csv:'+sha)

class ProposalApproval(Strict):
    action:ActionInput
    expected_version:int=Field(ge=1)
    review_evidence:str=Field(min_length=5,max_length=2000)
@router.post('/action-proposals/{record_id}/approve')
def approve_proposal(record_id:UUID,world_id:UUID,body:ProposalApproval,ctx=Depends(request_db,scope="function")):
    from app.domains.actions import create
    db,p=ctx;scope=resolve_scope(db,p,world_id);scope.require('facility')
    proposal=get(db,scope,'action_proposals',record_id,True)
    if proposal.version!=body.expected_version or proposal.status!='proposed':raise HTTPException(409,'Proposal changed or already reviewed')
    if proposal.zone_code!=body.action.zone_code:raise HTTPException(422,'Action must retain proposal zone')
    action=create(db,scope,body.action,'proposal:'+str(record_id))
    proposal.status='approved';proposal.version+=1;proposal.data={**proposal.data,'action_id':action['id'],'reviewer':str(p.user_id),'review_evidence':body.review_evidence}
    audit(db,scope,'approve','action_proposals',proposal.id,after=serialize(proposal))
    return {'proposal':serialize(proposal),'action':action}

class ModelStatusInput(Strict):
    status:str=Field(pattern='^(experimental_synthetic_only|disabled|rejected)$')
    expected_version:int=Field(ge=1)
    reason:str=Field(min_length=5,max_length=1000)
@router.patch('/models/{record_id}/status')
def model_status(record_id:UUID,world_id:UUID,body:ModelStatusInput,ctx=Depends(request_db,scope="function")):
    db,p=ctx;scope=resolve_scope(db,p,world_id);scope.require('models')
    row=get(db,scope,'model_versions',record_id,True)
    if row.version!=body.expected_version:raise HTTPException(409,'Model status changed; refresh')
    before=serialize(row);row.status=body.status;row.version+=1
    row.data={**row.data,'status_reason':body.reason,'status_actor':str(p.user_id)}
    audit(db,scope,'model_status','model_versions',row.id,before,serialize(row))
    return serialize(row)

# Public domain aliases and generic ledger endpoints share the exact same services.
def domain_create(table):
    def handler(world_id:UUID,body:RecordInput,request:Request,ctx=Depends(request_db,scope="function")):
        from app.domains.crud import create_record
        return create_record(ctx[0],resolve_scope(ctx[0],ctx[1],world_id),table,body,request.headers.get('Idempotency-Key'))
    return handler
def domain_update(table):
    def handler(record_id:UUID,world_id:UUID,body:RecordInput,ctx=Depends(request_db,scope="function")):
        from app.domains.crud import update_record
        return update_record(ctx[0],resolve_scope(ctx[0],ctx[1],world_id),table,record_id,body)
    return handler
def domain_archive(table):
    def handler(record_id:UUID,world_id:UUID,expected_version:int,ctx=Depends(request_db,scope="function")):
        from app.domains.crud import archive_record
        return archive_record(ctx[0],resolve_scope(ctx[0],ctx[1],world_id),table,record_id,expected_version)
    return handler
def domain_get(table):
    def handler(record_id:UUID,world_id:UUID,ctx=Depends(request_db,scope="function")):
        return serialize(get(ctx[0],resolve_scope(ctx[0],ctx[1],world_id),table,record_id))
    return handler
for alias,table in ALIASES.items():
    if table in CONTRACTS:
        router.add_api_route('/'+alias,domain_create(table),methods=['POST'],status_code=201,name='create_'+table)
        router.add_api_route('/'+alias+'/{record_id}',domain_update(table),methods=['PATCH'],name='update_'+table)
        router.add_api_route('/'+alias+'/{record_id}',domain_archive(table),methods=['DELETE'],name='archive_'+table)
        router.add_api_route('/'+alias+'/{record_id}',domain_get(table),methods=['GET'],name='get_'+table)
@router.get('/imports/{record_id}')
def import_get(record_id:UUID,world_id:UUID,ctx=Depends(request_db,scope="function")):
    return serialize(get(ctx[0],resolve_scope(ctx[0],ctx[1],world_id),'import_jobs',record_id))

@router.post('/jobs/{record_id}/retry')
def retry_job(record_id:UUID,world_id:UUID,ctx=Depends(request_db,scope="function")):
    db,p=ctx;scope=resolve_scope(db,p,world_id);job=get(db,scope,'jobs',record_id,True)
    if job.owner_id!=p.user_id and p.role not in ADMIN:raise HTTPException(403,'Job owner or administrator required')
    if job.status not in {'failed','waiting_provider','retry_pending'}:raise HTTPException(409,'Only a failed/deferred job may be explicitly retried')
    domain={'simulation':'simulation','report':'reports','infer':'models','import':'imports','agent':'chat','train':'models'}[job.category];scope.require(domain)
    if job.category=='agent':
        run=get(db,scope,'agent_runs',job.data['payload']['run_id'],True)
        if run.status=='cancelled':raise HTTPException(409,'Cancelled runs require a new request')
        run.status='queued';run.data={**run.data,'error':None,'lease_until':None}
    before=serialize(job);job.status='queued';job.data={**job.data,'attempts':0,'error':None,'lease_until':None}
    audit(db,scope,'explicit_retry','jobs',job.id,before,serialize(job))
    return serialize(job)
