from datetime import timedelta
from sqlalchemy import select,func
from app.core.models import TABLES
from app.core.records import query,serialize
from app.simulation.engine import waste_deadline

def waste_state(db,scope):
    batches=TABLES['waste_batches'];moves=TABLES['waste_movements']
    category=batches.data['category'].as_string()
    stocks=db.execute(select(moves.parent_id,func.sum(moves.value),category,batches.event_at).join(batches,batches.id==moves.parent_id).where(
        moves.world_id==scope.world.id,batches.world_id==scope.world.id,moves.event_at<=scope.world.as_of).group_by(moves.parent_id,category,batches.event_at).having(func.sum(moves.value)>0).order_by(batches.event_at,moves.parent_id)).all()
    batch_rows={b.id:b for b in db.scalars(select(batches).where(batches.world_id==scope.world.id,batches.id.in_([r[0] for r in stocks[:500]])))} if stocks else {}
    items=[]
    for batch_id,kg,cat,event_at in stocks[:500]:
        batch=batch_rows.get(batch_id)
        if not batch:continue
        age=(scope.world.as_of-batch.event_at).total_seconds()/3600
        record=serialize(batch);record.update(current_stock_kg=float(kg),age_hours=age)
        items.append(record)
    bins=query(db,scope,'waste_bins',100)
    categories=[]
    policy=next((p for p in query(db,scope,'policy_versions',100) if p.category=='waste'),None)
    age_limit=policy.data.get('age_limit_hours',24) if policy else 24
    fill_limit=(policy.data.get('fill_threshold_pct') or 85) if policy else 85
    for cat in ['yellow','red','white','blue']:
        group=[r for r in stocks if r[2]==cat]
        capacity=sum(float(b.data['capacity_kg']) for b in bins if b.data['category']==cat)
        stock=sum(float(r[1]) for r in group)
        age=max([(scope.world.as_of-r[3]).total_seconds()/3600 for r in group],default=None)
        fill=stock/capacity*100 if capacity else None
        categories.append({'category':cat,'stock_kg':stock,'capacity_kg':capacity,'fill_pct':fill,'oldest_age_hours':age,
                           'deadline':waste_deadline(fill or 0,2,age,fill_limit,age_limit) if capacity else None})
    return {'batches':items,'batch_count':len(stocks),'truncated':len(stocks)>500,'category_totals_partial':False,'bins':[serialize(b) for b in bins],'categories':categories,
            'pickups':[serialize(p) for p in query(db,scope,'pickups',30)],'handovers':[serialize(p) for p in query(db,scope,'handover_evidence',30)],
            'policy':serialize(policy) if policy else None,'source_type':'synthetic_extended_v1' if bins else 'unavailable',
            'limitations':['Additional category ledger exists only in the independent extended world. Pickup metadata does not prove real physical handover.','Batch stock derives from signed movements at virtual cutoff, not current stored status.']}

def assets_state(db,scope):
    assets=query(db,scope,'assets',100);cls=TABLES['asset_telemetry']
    telemetry=[]
    for a in assets:
        latest=db.scalar(select(cls).where(cls.world_id==scope.world.id,cls.parent_id==a.id,cls.event_at<=scope.world.as_of).order_by(cls.event_at.desc(),cls.created_at.desc(),cls.id).limit(1))
        if latest:telemetry.append(serialize(latest))
    return {'assets':[serialize(a) for a in assets],'dependencies':[serialize(a) for a in query(db,scope,'asset_dependencies')],
            'telemetry':telemetry,'maintenance_orders':[serialize(a) for a in query(db,scope,'maintenance_orders')],
            'limitations':['Telemetry fault candidates use rules until adequate labels/validation exist.']}

def reserves_state(db,scope):
    states=[]
    for table,parent in [('tank_states','tanks'),('power_states','power_sources')]:
        cls=TABLES[table]
        for item in query(db,scope,parent,30):
            latest=db.scalar(select(cls).where(cls.world_id==scope.world.id,cls.parent_id==item.id,cls.event_at<=scope.world.as_of).order_by(cls.event_at.desc(),cls.created_at.desc(),cls.id).limit(1))
            if latest:states.append({'configuration':serialize(item),'state':serialize(latest)})
    return {'reserves':states,'assumptions':scope.world.config,'limitations':['Potable, process and protected fire reserves are separate. No water quality certification inferred.']}

def environment_state(db,scope):
    cls=TABLES['environment_readings'];zones=query(db,scope,'zones',50);readings=[]
    for z in zones:
        latest=db.scalar(select(cls).where(cls.world_id==scope.world.id,cls.zone_code==z.zone_code,cls.event_at<=scope.world.as_of).order_by(cls.event_at.desc(),cls.created_at.desc(),cls.id).limit(1))
        if latest:readings.append(serialize(latest))
    policies=[serialize(p) for p in query(db,scope,'policy_versions',100) if p.category=='environment']
    return {'readings':readings,'policies':policies,'window':'Latest hourly state per zone','limitations':['Internal demonstration thresholds; not clinical exposure standards.']}

def parking_safety(db,scope):
    snapshots=query(db,scope,'parking_snapshots',1)
    cls=TABLES['safety_incidents'];start=scope.world.as_of-timedelta(days=30)
    count=db.scalar(select(func.count()).select_from(cls).where(cls.world_id==scope.world.id,cls.event_at>start,cls.event_at<=scope.world.as_of))
    ops=TABLES['operational_snapshots']
    denominator=db.scalar(select(func.count()).select_from(ops).where(ops.world_id==scope.world.id,ops.event_at>start,ops.event_at<=scope.world.as_of))
    return {'parking':[serialize(p) for p in snapshots],'areas':[serialize(p) for p in query(db,scope,'parking_areas')],
            'incidents':[serialize(p) for p in query(db,scope,'safety_incidents',20)],'incident_count_last_30_days':count,
            'rate_scale':1000,'rate_unit':'incidents per 1000 observed zone-hours','parking_queue_unit':'vehicles','zone_hours_last_30_days':denominator,'incidents_per_1000_zone_hours':count/denominator*1000 if denominator else None,
            'limitations':['Operational incident rate uses observed zone-hours. It is not a patient safety outcome or hospital comparison.']}
