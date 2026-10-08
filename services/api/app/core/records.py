from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import select
from fastapi import HTTPException
from app.core.models import TABLES, now

def jsonable(value):
    if isinstance(value,dict):
        return {k:jsonable(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value,datetime):
        return value.isoformat()
    if isinstance(value,UUID):
        return str(value)
    from decimal import Decimal
    if isinstance(value,Decimal):
        return float(value)
    return value

def serialize(row):
    return jsonable({c.name:getattr(row,c.name) for c in row.__table__.columns})

def query(db,scope,table,limit=100,offset=0,status=None,cutoff=True):
    cls = TABLES[table]
    q = select(cls).where(cls.world_id==scope.world.id)
    if cutoff:
        q = q.where(cls.event_at<=scope.world.as_of)
    if status:
        q = q.where(cls.status==status)
    return db.scalars(q.order_by(cls.event_at.desc(),cls.created_at.desc(),cls.id).limit(limit).offset(offset)).all()

def get(db,scope,table,record_id,lock=False):
    cls = TABLES[table]
    q = select(cls).where(cls.id==UUID(str(record_id)),cls.world_id==scope.world.id)
    if lock:
        q = q.with_for_update()
    obj = db.scalar(q)
    if not obj:
        raise HTTPException(404,'Record unavailable in your scope')
    return obj

def insert(db,scope,table,data=None,**kwargs):
    row = TABLES[table](**scope.keys,event_at=kwargs.pop('event_at',scope.world.as_of),data=jsonable(data or {}),**kwargs)
    db.add(row)
    db.flush()
    return row

def audit(db,scope,operation,table,record_id,before=None,after=None):
    return insert(db,scope,'audit_events',{'operation':operation,'table':table,'record_id':str(record_id),
                'before':before,'after':after,'actor':str(scope.principal.user_id)},name=operation,
                owner_id=scope.principal.user_id,event_at=now())
