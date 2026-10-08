from datetime import datetime
from uuid import UUID
from fastapi import HTTPException
from pydantic import BaseModel,Field,ConfigDict
from sqlalchemy import select,text
from app.core.auth import ADMIN
from app.core.models import TABLES
from app.core.records import insert,get,serialize,audit

STATES={'open':{'acknowledged'},'acknowledged':{'in_progress'},'in_progress':{'resolved','acknowledged'},
        'resolved':{'verified','in_progress'},'verified':{'closed','in_progress'},'closed':{'open'}}
class ActionInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    name:str=Field(min_length=4,max_length=200)
    category:str=Field(pattern='^(maintenance|waste|water|energy|environment|parking|safety|sustainability)$')
    zone_code:str
    owner_id:UUID
    due_at:datetime
    description:str=Field(default='',max_length=4000)
    alert_id:UUID|None=None
    scenario_id:UUID|None=None
class Transition(BaseModel):
    model_config=ConfigDict(extra='forbid')
    state:str
    expected_version:int=Field(ge=1)
    reason:str=Field(min_length=3,max_length=2000)
    evidence:str|None=Field(default=None,max_length=4000)
    file_id:UUID|None=None

def create(db,scope,body:ActionInput,key):
    scope.require('actions');scope.zone(body.zone_code)
    if scope.principal.role=='waste_officer' and body.category!='waste':raise HTTPException(403,'Waste officers may create waste actions only')
    if scope.principal.role=='maintenance_technician' and (body.category!='maintenance' or body.owner_id!=scope.principal.user_id):raise HTTPException(403,'Technician actions must be assigned to self in granted zone')
    if scope.principal.role=='sustainability_officer' and body.category!='sustainability':raise HTTPException(403,'Sustainability scope only')
    if body.due_at.tzinfo is None:raise HTTPException(422,'Due date timezone required')
    cls=TABLES['actions']
    old=db.scalar(select(cls).where(cls.world_id==scope.world.id,cls.idempotency_key==key))
    if old:return serialize(old)
    owners=db.execute(text('SELECT * FROM scoped_owners(:org,:fac)'),{'org':scope.principal.organization_id,'fac':scope.world.facility_id}).mappings().all()
    if not any(o['id']==body.owner_id and (o['zone_code'] is None or o['zone_code']==body.zone_code) for o in owners):raise HTTPException(422,'Owner has no grant for this zone/facility')
    if not db.scalar(select(TABLES['zones']).where(TABLES['zones'].world_id==scope.world.id,TABLES['zones'].zone_code==body.zone_code)):raise HTTPException(422,'Zone not configured')
    if body.alert_id:get(db,scope,'alerts',body.alert_id)
    if body.scenario_id:get(db,scope,'simulation_runs',body.scenario_id)
    row=insert(db,scope,'actions',{'description':body.description,'alert_id':str(body.alert_id) if body.alert_id else None,
         'scenario_id':str(body.scenario_id) if body.scenario_id else None},name=body.name,category=body.category,zone_code=body.zone_code,owner_id=body.owner_id,
         due_at=body.due_at,status='open',idempotency_key=key)
    insert(db,scope,'action_events',{'before':None,'after':'open','actor':str(scope.principal.user_id)},parent_id=row.id,zone_code=row.zone_code,name='Created',owner_id=scope.principal.user_id)
    audit(db,scope,'create','actions',row.id,after=serialize(row))
    return serialize(row)

def transition(db,scope,record_id,body:Transition):
    scope.require('actions')
    row=get(db,scope,'actions',record_id,True)
    if scope.principal.role not in ADMIN|{'operations_supervisor'} and row.owner_id!=scope.principal.user_id:raise HTTPException(403,'Only owner or supervisor can update action')
    if body.expected_version!=row.version:raise HTTPException(409,'Action version changed; refresh before updating')
    if body.state not in STATES.get(row.status,set()):raise HTTPException(422,f'Invalid transition {row.status} → {body.state}')
    if body.state in {'verified','closed'}:
        if scope.principal.role not in ADMIN|{'operations_supervisor'}:raise HTTPException(403,'Reviewer role required')
        if not body.evidence and not body.file_id:raise HTTPException(422,'Verification/closure evidence required')
        if body.state=='verified' and row.data.get('resolved_by')==str(scope.principal.user_id):raise HTTPException(403,'Independent reviewer required')
        if body.file_id:get(db,scope,'stored_files',body.file_id)
    before=serialize(row)
    if body.evidence or body.file_id:
        insert(db,scope,'action_evidence',{'note':body.evidence,'file_id':str(body.file_id) if body.file_id else None,'state':body.state},parent_id=row.id,zone_code=row.zone_code,name='Recorded evidence',owner_id=scope.principal.user_id)
    data=dict(row.data)
    if body.state=='resolved':data['resolved_by']=str(scope.principal.user_id)
    row.data=data;row.status=body.state;row.version+=1
    insert(db,scope,'action_events',{'before':before['status'],'after':row.status,'reason':body.reason,'actor':str(scope.principal.user_id),'version':row.version},parent_id=row.id,zone_code=row.zone_code,name=body.state,owner_id=scope.principal.user_id)
    audit(db,scope,'transition','actions',row.id,before,serialize(row))
    return serialize(row)
