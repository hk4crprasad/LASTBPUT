from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import select, func, case
from sqlalchemy.dialects.postgresql import distinct_on,aggregate_order_by
from fastapi import HTTPException
from app.core.models import Observation, Metric, TABLES
from app.core.records import query, serialize


def window(scope,start=None,end=None,hours=24):
    end = min(end,scope.world.as_of) if end else scope.world.as_of
    start = start or end-timedelta(hours=hours)
    if not start.tzinfo or not end.tzinfo or start>=end or (end-start).total_seconds()>366*86400:
        raise HTTPException(422,'Use a timezone-aware increasing window of at most 366 days')
    return start,end

def series(db,scope,metric,start=None,end=None,bucket='hour',zone_ids=None,limit=200,offset=0):
    catalog=db.get(Metric,metric)
    if not catalog:raise HTTPException(422,'Metric is not in allowlisted catalog')
    if bucket not in {'hour','day'} or not 1<=limit<=500 or offset<0:raise HTTPException(422,'Invalid bounded query')
    start,end=window(scope,start,end)
    zone_ids=zone_ids or []
    for zone in zone_ids:scope.zone(zone)
    time=func.date_trunc(bucket,Observation.interval_end,'UTC').label('time')
    # Consumption is sum; state avg is explicitly a sample-weighted mean on the hourly grid.
    agg=func.sum(Observation.value) if catalog.aggregation=='sum' else (func.array_agg(aggregate_order_by(Observation.value,Observation.interval_end.desc()))[1] if catalog.aggregation=='last' else func.avg(Observation.value))
    q=select(time,Observation.zone_code,agg.label('value'),func.count().label('rows'),func.count(Observation.value).label('valid_rows')).where(
        Observation.world_id==scope.world.id,Observation.metric==metric,Observation.interval_end>start,Observation.interval_end<=end)
    if zone_ids:q=q.where(Observation.zone_code.in_(zone_ids))
    q=q.group_by(time,Observation.zone_code).order_by(time,Observation.zone_code).limit(limit+1).offset(offset)
    rows=db.execute(q).mappings().all()
    return {'metric':metric,'unit':catalog.unit,'semantics':catalog.semantics,'aggregation':catalog.aggregation,
            'start':start.isoformat(),'end':end.isoformat(),'items':[{'time':r['time'].isoformat(),'zone':r['zone_code'],
             'value':r['value'],'valid_rows':r['valid_rows'],'rows':r['rows'],'quality':'complete' if r['rows']==r['valid_rows'] else 'partial'} for r in rows[:limit]],
            'window_totals':totals(db,scope,start,end).get(metric),'returned_sum':sum(r['value'] or 0 for r in rows[:limit]) if catalog.aggregation=='sum' else None,
            'truncated':len(rows)>limit,'limit':limit,'offset':offset,'source_type':'synthetic',
            'limitations':['State averages are hourly sample means; no parent/submeter double counting because imported zones are disjoint reporting boundaries.']}

def totals(db,scope,start,end):
    expected=max(1,int((end-start).total_seconds()/3600))*(len(scope.zone_codes) if scope.zone_codes is not None else db.scalar(select(func.count()).select_from(TABLES['zones']).where(TABLES['zones'].world_id==scope.world.id)))
    values=db.execute(select(Observation.metric,func.sum(Observation.value),func.count(),func.count(Observation.value)).where(
        Observation.world_id==scope.world.id,Observation.interval_end>start,Observation.interval_end<=end,
        Observation.metric.in_(['energy.interval_kwh','water.interval_l','waste.generated_kg'])).group_by(Observation.metric)).all()
    return {m:{'value':float(v) if v is not None else None,'rows':n,'valid_rows':valid,'expected_rows':expected,'coverage':min(1,valid/expected) if expected else None,'coverage_pct':min(100,100*valid/expected) if expected else None,'missing_intervals':max(0,expected-n),
               'unit':'kWh' if m.startswith('energy') else 'L' if m.startswith('water') else 'kg'} for m,v,n,valid in values}

def context(db,scope,start=None,end=None):
    start,end=window(scope,start,end)
    cls=TABLES['operational_snapshots']
    rows=db.execute(select(cls.zone_code,func.avg(cls.data['occupied_beds'].as_float()),func.sum(cls.data['opd_visits'].as_integer()),
                           func.max(cls.data['bed_capacity'].as_integer()),func.count()).where(cls.world_id==scope.world.id,cls.event_at>start,cls.event_at<=end).group_by(cls.zone_code)).all()
    return {'start':start.isoformat(),'end':end.isoformat(),'zones':[{'zone':z,'mean_occupied_beds':occ,'opd_visits':opd,'bed_capacity':cap,'intervals':n,
             'occupied_bed_days':occ*n/24 if occ is not None else None} for z,occ,opd,cap,n in rows],
            'total_occupied_bed_days':sum(occ*n/24 for z,occ,opd,cap,n in rows if occ is not None and cap>0),
            'total_opd_visits':sum(opd or 0 for z,occ,opd,cap,n in rows),
            'schedules':[serialize(v) for v in query(db,scope,'operating_schedules')],
            'source_type':'aggregate_synthetic','patient_data':False}

def latest_context(db,scope):
    cls=TABLES['operational_snapshots']
    return [serialize(v) for v in db.scalars(select(cls).where(cls.world_id==scope.world.id,cls.event_at<=scope.world.as_of)
                 .ext(distinct_on(cls.zone_code)).order_by(cls.zone_code,cls.event_at.desc()))]

def overview(db,scope,start=None,end=None):
    start,end=window(scope,start,end)
    values=totals(db,scope,start,end)
    latest=latest_context(db,scope)
    from app.domains.state import reserves_state,waste_state,assets_state
    sustainability_data=sustainability(db,scope,start,end)
    waste=waste_state(db,scope);assets=assets_state(db,scope)
    return {'world_id':str(scope.world.id),'world':scope.world.code,'as_of':scope.world.as_of.isoformat(),
            'timezone':'Asia/Kolkata','window_hours':(end-start).total_seconds()/3600,'start':start.isoformat(),'end':end.isoformat(),'source_type':'synthetic',
            'metrics':values,'bed_capacity':sum(r['data']['bed_capacity'] for r in latest) if latest else None,
            'occupied_beds':sum(r['data']['occupied_beds'] for r in latest) if latest else None,'zones':latest,
            'active_alert_count':db.scalar(select(func.count()).select_from(TABLES['alerts']).where(TABLES['alerts'].world_id==scope.world.id,TABLES['alerts'].status=='open',TABLES['alerts'].event_at<=scope.world.as_of)),
            'active_alerts':[serialize(v) for v in query(db,scope,'alerts',20,status='open')],
            'actions':[serialize(v) for v in query(db,scope,'actions',20)],
            'reserves':reserves_state(db,scope)['reserves'],'waste_deadlines':waste['categories'],
            'intensities':sustainability_data['intensities'],'occupied_bed_days':sustainability_data['occupied_bed_days'],
            'critical_assets':[a for a in assets['assets'] if a['data'].get('critical')],'critical_asset_telemetry':[r for r in assets['telemetry'] if r['data'].get('mode') in {'offline','degraded'}],
            'stale_zone_codes':[r['zone_code'] for r in latest if (scope.world.as_of-datetime.fromisoformat(r['event_at'])).total_seconds()>3600],
            'coverage':{m:v['coverage'] for m,v in values.items()},'boundary':'Sum of disjoint zone intervals; imported aggregate waste is separate from the extended-world batch ledger',
            'limitations':['Synthetic demonstration; no clinical workflows or validated real-hospital accuracy']}

def sustainability(db,scope,start=None,end=None):
    start,end=window(scope,start,end)
    usage=totals(db,scope,start,end)
    ctx=context(db,scope,start,end)
    bed_days=sum(r['occupied_bed_days'] or 0 for r in ctx['zones'] if r['bed_capacity']>0)
    inpatient=db.execute(select(Observation.metric,func.sum(Observation.value)).where(Observation.world_id==scope.world.id,
        Observation.interval_end>start,Observation.interval_end<=end,Observation.zone_code.in_([r['zone'] for r in ctx['zones'] if r['bed_capacity']>0]),
        Observation.metric.in_(['energy.interval_kwh','water.interval_l'])).group_by(Observation.metric)).all()
    tariffs=query(db,scope,'tariff_versions',100)
    factors=query(db,scope,'emission_factor_versions',100)
    def applicable(rows):
        return next((r for r in rows if r.event_at<=end and r.data.get('effective_from',r.event_at.isoformat())<=start.isoformat()),None)
    tariff=applicable(tariffs);factor=applicable(factors)
    energy=usage.get('energy.interval_kwh',{}).get('value')
    # A period crossing a tariff boundary is explicitly unavailable until segmented.
    crossing=any(start<r.event_at<=end for r in tariffs+factors)
    return {'start':start.isoformat(),'end':end.isoformat(),'window_hours':(end-start).total_seconds()/3600,'usage':usage,'occupied_bed_days':bed_days,
        'intensities':{m:float(v)/bed_days if bed_days else None for m,v in inpatient},
        'cost_estimate_inr':round(energy*float(tariff.value),2) if tariff and energy is not None and not crossing else None,
        'carbon_estimate_kgco2e':energy*float(factor.value) if factor and energy is not None and not crossing else None,
        'tariff':serialize(tariff) if tariff else None,'emission_factor':serialize(factor) if factor else None,
        'boundary':'Inpatient intensity excludes OPD and service zones; facility cost/carbon uses all disjoint zones',
        'source_type':'estimated_from_synthetic','limitations':['Demonstration tariff/factor assumptions, not official current values. Demand charges omitted. Missing consumption remains partial.','Period spanning changed factors requires segmentation; estimate unavailable.' if crossing else 'No measured savings claimed.']}
