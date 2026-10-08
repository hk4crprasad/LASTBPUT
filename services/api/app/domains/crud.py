import hashlib
from uuid import UUID
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from app.core.models import TABLES
from app.core.records import insert,get,serialize,audit
from app.domains.contracts import CONTRACTS,RecordInput

READ_TABLES=set(TABLES)-{'audit_events','source_events','stored_files','outbox_events'}
VERSIONED={'policy_versions','tariff_versions','emission_factor_versions','documents','agent_policies'}
IMMUTABLE={'pickups','waste_batches','parking_events','environment_readings'}|VERSIONED

def validate(db,scope,table,body):
    if table not in CONTRACTS:raise HTTPException(405,'Ledger is maintained by domain workflow; direct write unavailable')
    contract,domain=CONTRACTS[table];scope.require(domain);scope.zone(body.zone_code)
    try:data=contract.model_validate(body.data).model_dump(mode='json')
    except ValidationError as e:raise HTTPException(422,str(e))
    if body.parent_id:
        from app.core.models import PARENTS
        if table in PARENTS:get(db,scope,PARENTS[table],body.parent_id)
    if body.owner_id:
        from sqlalchemy import text
        owners=db.execute(text('SELECT * FROM scoped_owners(:org,:fac)'),{'org':scope.principal.organization_id,'fac':scope.world.facility_id}).mappings().all()
        if not any(o['id']==body.owner_id and (o['zone_code'] is None or o['zone_code']==body.zone_code) for o in owners):raise HTTPException(422,'Owner outside scope')
    if table=='maintenance_orders':
        get(db,scope,'assets',data['asset_id'])
        if scope.principal.role=='maintenance_technician' and body.owner_id!=scope.principal.user_id:raise HTTPException(403,'Technician orders must be assigned to self')
    if table=='asset_dependencies':
        get(db,scope,'assets',data['from_asset_id']);get(db,scope,'assets',data['to_asset_id'])
        if data['from_asset_id']==data['to_asset_id']:raise HTTPException(422,'Self-dependency invalid')
    if table=='waste_batches':
        bin=get(db,scope,'waste_bins',data['bin_id'])
        if bin.data['category']!=data['category'] or bin.zone_code!=body.zone_code:raise HTTPException(422,'Category and zone must match bin')
    if table in {'tariff_versions','emission_factor_versions'}:
        expected='INR/kWh' if table=='tariff_versions' else 'kgCO2e/kWh'
        if data['unit']!=expected:raise HTTPException(422,f'Expected {expected}')
    if table=='operating_schedules' and data['essential'] and scope.principal.role not in {'hospital_admin','organization_admin'}:
        raise HTTPException(403,'Protected service schedule requires hospital admin')
    if body.event_at and body.event_at.tzinfo is None:raise HTTPException(422,'Timezone required')
    return data

def create_record(db,scope,table,body:RecordInput,key=None):
    data=validate(db,scope,table,body)
    key=f'user:{scope.principal.user_id}:{table}:{key}' if key else None
    if key:
        old=db.scalar(select(TABLES[table]).where(TABLES[table].world_id==scope.world.id,TABLES[table].idempotency_key==key))
        if old:return serialize(old)
    kwargs={k:getattr(body,k) for k in ['name','zone_code','category','status','severity','owner_id','parent_id','due_at']}
    if body.event_at:kwargs['event_at']=body.event_at
    if table in VERSIONED:
        kwargs['event_at']=__import__('datetime').datetime.fromisoformat(data.get('effective_from',scope.world.as_of.isoformat()))
    if table in {'tariff_versions','emission_factor_versions'}:kwargs.update(value=data['value'],unit=data['unit'])
    if table=='waste_batches':kwargs.update(value=data['generated_kg'],unit='kg',status='stored',event_at=__import__('datetime').datetime.fromisoformat(data['generated_at']))
    if table=='pickups':
        kwargs.update(status='recorded',event_at=__import__('datetime').datetime.fromisoformat(data['collected_at']))
        batches=[get(db,scope,'waste_batches',i,True) for i in data['batch_ids']]
        if any(b.status!='stored' for b in batches):raise HTTPException(409,'Batch already collected')
        if any(b.zone_code!=body.zone_code for b in batches):raise HTTPException(422,'Pickup batches must share a granted zone')
        from datetime import datetime
        if any(datetime.fromisoformat(data['collected_at'])<b.event_at for b in batches):raise HTTPException(422,'Collection cannot precede batch generation')
        total=sum(float(b.value) for b in batches);kwargs.update(value=total,unit='kg')
    row=insert(db,scope,table,data,idempotency_key=key,**kwargs)
    if table=='waste_batches':
        insert(db,scope,'waste_movements',{'kind':'generated','bin_id':data['bin_id'],'kg':data['generated_kg']},parent_id=row.id,zone_code=row.zone_code,name='Generated batch',value=row.value,unit='kg',event_at=row.event_at)
    if table=='pickups':
        for batch in batches:
            batch.status='collected';batch.version+=1
            insert(db,scope,'waste_movements',{'kind':'collected','pickup_id':str(row.id),'kg':float(batch.value)},parent_id=batch.id,zone_code=batch.zone_code,name='Collected batch',value=-float(batch.value),unit='kg',event_at=row.event_at)
        insert(db,scope,'handover_evidence',{'reference':data['handover_reference'],'destination':data['destination'],'source_type':'user_recorded_metadata','note':'Metadata is not a certified physical handover document'},parent_id=row.id,zone_code=row.zone_code,name='Recorded handover metadata')
    if table=='documents':
        for i in range(0,len(data['body']),1500):
            insert(db,scope,'document_chunks',{'body':data['body'][i:i+1500],'title':body.name,'source':data['source'],'policy_version':data['policy_version']},parent_id=row.id,zone_code=row.zone_code,name=body.name)
    if table=='parking_events':
        area=get(db,scope,'parking_areas',body.parent_id,True)
        cls=TABLES['parking_snapshots']
        state=db.scalar(select(cls).where(cls.world_id==scope.world.id,cls.parent_id==area.id,cls.event_at<=scope.world.as_of).order_by(cls.event_at.desc(),cls.created_at.desc(),cls.id).limit(1))
        occupancy=state.data['occupancy'] if state else 0;queue=state.data.get('queue',0) if state else 0
        capacity=area.data['capacity'];n=data['count']
        if data['direction']=='arrival':
            admitted=min(capacity-occupancy,n);occupancy+=admitted;queue+=n-admitted
        else:
            if n>occupancy:raise HTTPException(422,'Exits exceed parked occupancy')
            occupancy-=n;admitted=min(queue,capacity-occupancy);occupancy+=admitted;queue-=admitted
        insert(db,scope,'parking_snapshots',{'occupancy':occupancy,'queue':queue,'capacity':capacity,'arrivals':n if data['direction']=='arrival' else 0,'exits':n if data['direction']=='exit' else 0},parent_id=area.id,zone_code=row.zone_code,name='Updated parking state')
    audit(db,scope,'create',table,row.id,after=serialize(row))
    return serialize(row)

def update_record(db,scope,table,record_id,body:RecordInput):
    if table in IMMUTABLE:raise HTTPException(405,'Append-only evidence/version ledger; create a new record')
    data=validate(db,scope,table,body)
    row=get(db,scope,table,record_id,True)
    if body.expected_version!=row.version:raise HTTPException(409,'Record version changed')
    if scope.principal.role=='maintenance_technician' and row.owner_id!=scope.principal.user_id:raise HTTPException(403,'Assigned orders only')
    before=serialize(row)
    for key in ['name','category','status','severity','owner_id','due_at']:
        setattr(row,key,getattr(body,key))
    row.data=data;row.version+=1
    audit(db,scope,'update',table,row.id,before,serialize(row))
    return serialize(row)

def archive_record(db,scope,table,record_id,version):
    if table not in CONTRACTS or table in IMMUTABLE:raise HTTPException(405,'Append-only ledger cannot be archived')
    scope.require(CONTRACTS[table][1]);row=get(db,scope,table,record_id,True)
    if row.version!=version:raise HTTPException(409,'Stale record')
    if scope.principal.role=='maintenance_technician' and row.owner_id!=scope.principal.user_id:raise HTTPException(403,'Assigned orders only')
    before=serialize(row);row.status='archived';row.version+=1
    audit(db,scope,'archive',table,row.id,before,serialize(row))
    return serialize(row)
