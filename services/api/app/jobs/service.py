import hashlib
from datetime import timedelta
from uuid import UUID
from sqlalchemy import select
from app.core.models import TABLES,now
from app.core.records import insert,serialize,get
from app.core.settings import settings

def enqueue(db,scope,kind,payload,key=None):
    allowed={'simulation','infer','import','report','agent','train'}
    if kind not in allowed:raise ValueError('Unsupported job kind')
    payload={**payload,'_context':{'as_of':scope.world.as_of.isoformat(),'snapshot_version':scope.world.version,'world_config':scope.world.config}}
    if kind=='simulation':
        from app.simulation.service import capture_baseline
        payload={**payload,'baseline':capture_baseline(db,scope).model_dump(mode='json')}
    key=f'{scope.principal.user_id}:{kind}:{key}' if key else None
    cls=TABLES['jobs']
    if key:
        old=db.scalar(select(cls).where(cls.world_id==scope.world.id,cls.idempotency_key==key))
        if old:return {'job_id':str(old.id),'status':old.status,'result':old.data.get('result'),'idempotent':True}
    row=insert(db,scope,'jobs',{'payload':payload,'attempts':0,'max_retries':settings().job_max_retries,'role_at_request':scope.principal.role},
            category=kind,name=kind,status='queued',owner_id=scope.principal.user_id,idempotency_key=key,zone_code=scope.zone_codes[0] if scope.zone_codes else None)
    insert(db,scope,'outbox_events',{'job_id':str(row.id)},parent_id=row.id,name='Dispatch '+kind,status='pending',owner_id=scope.principal.user_id,zone_code=row.zone_code)
    return {'job_id':str(row.id),'status':row.status,'events_url':f'/api/v1/jobs/{row.id}'}

def reconcile(db,p):
    cls=TABLES['jobs'];rows=db.scalars(select(cls).where(cls.owner_id==p.user_id,cls.status.in_(['running','queued']))).all()
    recovered=0
    for row in rows:
        expired=row.data.get('lease_until')
        if row.status=='running' and expired and __import__('datetime').datetime.fromisoformat(expired)<now():
            row.status='queued';row.data={**row.data,'recovered_at':now().isoformat()};recovered+=1
    return {'recovered':recovered,'pending':len(rows)}
