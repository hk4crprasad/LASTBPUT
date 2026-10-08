import hashlib
import json
from sqlalchemy import select
from app.core.models import TABLES
from app.core.records import insert,query,serialize,get,jsonable
from app.domains.metrics import overview,sustainability
from app.simulation.engine import Tank,Baseline,Scenario,run_engine

def capture_baseline(db,scope):
    tanks=query(db,scope,'tanks',20)
    states=query(db,scope,'tank_states',100)
    typed=[]
    for tank in tanks:
        state=next((s for s in states if s.parent_id==tank.id),None)
        data=tank.data
        typed.append(Tank(name=tank.name,kind=data['kind'],capacity_l=data['capacity_l'],reserve_l=state.data['reserve_l'] if state else data['initial_reserve_l'],
                          inflow_lph=state.data['inflow_lph'] if state else data.get('inflow_lph',0),essential_lph=data.get('essential_lph',0),nonessential_lph=data.get('nonessential_lph',0)))
    if not typed:
        config=scope.world.config
        typed=[Tank(name='Assumed usable potable reserve',kind='potable',capacity_l=config.get('tank_usable_l',30000),reserve_l=config.get('tank_usable_l',30000),
                    inflow_lph=0,essential_lph=config.get('essential_water_lph',3000))]
    overview_data=overview(db,scope);s=sustainability(db,scope)
    power=query(db,scope,'power_states',1)
    p=power[0].data if power else {}
    from app.domains.state import waste_state
    waste=waste_state(db,scope)
    age=max([c['oldest_age_hours'] for c in waste['categories'] if c['oldest_age_hours'] is not None],default=None)
    capacity=sum(c['capacity_kg'] for c in waste['categories'])
    fill=sum(c['stock_kg'] for c in waste['categories'])/capacity*100 if capacity else 30
    parking=query(db,scope,'parking_snapshots',1)
    park=parking[0].data if parking else {}
    policies=query(db,scope,'policy_versions',100)
    waste_policy=next((p for p in policies if p.category=='waste'),None)
    wp=waste_policy.data if waste_policy else {}
    return Baseline(as_of=scope.world.as_of,snapshot_version=scope.world.version,demand_source='Frozen observed snapshot plus explicitly configured constant engineering demand',tanks=typed,
        battery_deliverable_kwh=p.get('battery_deliverable_kwh',scope.world.config.get('battery_deliverable_kwh',120)),essential_load_kw=p.get('essential_load_kw',scope.world.config.get('essential_load_kw',60)),
        nonessential_load_kw=p.get('nonessential_load_kw',20),fuel_l=p.get('fuel_l',0),genset_max_kw=p.get('genset_max_kw',0),
        waste_fill_pct=fill,waste_age_hours=age,waste_fill_threshold_pct=(wp.get('fill_threshold_pct') or 85),waste_age_limit_hours=(wp.get('age_limit_hours') or 24),
        parking_occupancy=park.get('occupancy',60),parking_capacity=park.get('capacity',120),arrivals_per_hour=park.get('arrivals',20),exits_per_hour=park.get('exits',20),initial_queue=park.get('queue',0),
        tariff_inr_per_kwh=float(s['tariff']['value']) if s['tariff'] else None,carbon_kg_per_kwh=float(s['emission_factor']['value']) if s['emission_factor'] else None,
        versions={'world':scope.world.version,'tariff_id':s['tariff']['id'] if s['tariff'] else None,'factor_id':s['emission_factor']['id'] if s['emission_factor'] else None,
                  'policy_id':str(waste_policy.id) if waste_policy else None,'source_type':'synthetic'})

def save_simulation(db,scope,scenario:Scenario,key=None,baseline=None):
    scope.require('simulation')
    if key:
        cls=TABLES['simulation_runs']
        old=db.scalar(select(cls).where(cls.world_id==scope.world.id,cls.idempotency_key==key))
        if old:return serialize(old)
    b=baseline or capture_baseline(db,scope)
    scenario_row=insert(db,scope,'scenario_definitions',scenario.model_dump(),name=scenario.name)
    result=run_engine(b,scenario)
    row=insert(db,scope,'simulation_runs',{'scenario_id':str(scenario_row.id),'baseline':b.model_dump(mode='json'),
                'scenario':scenario.model_dump(mode='json'),'result':result,'engine_version':'greenops-15min-v1'},name=scenario.name,status='completed',
                idempotency_key=key,source_type='simulated')
    for point in result['central']['points']:
        insert(db,scope,'simulation_points',point,parent_id=row.id,name=scenario.name)
    return serialize(row)

def compare(db,scope,run_ids):
    if not 2<=len(run_ids)<=5:raise ValueError('Compare 2–5 runs')
    runs=[get(db,scope,'simulation_runs',i) for i in run_ids]
    snapshots=[r.data['baseline'] for r in runs]
    if any(b!=snapshots[0] for b in snapshots):raise ValueError('Comparison requires identical immutable baseline snapshots')
    if any(r.data['scenario']['horizon_hours']!=runs[0].data['scenario']['horizon_hours'] for r in runs):raise ValueError('Comparison horizons differ')
    ref=runs[0].data['result']['central']['totals']
    return {'baseline_run_id':str(runs[0].id),'runs':[{'id':str(r.id),'name':r.name,'totals':r.data['result']['central']['totals'],
            'delta_vs_first':{k:v-ref[k] if v is not None and ref[k] is not None else None for k,v in r.data['result']['central']['totals'].items()}} for r in runs],
            'source_type':'simulated','limitations':['Calculated deltas against the first saved run, not measured savings.']}
