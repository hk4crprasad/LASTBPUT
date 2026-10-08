"""Deterministic 15-minute operations simulation. No stochastic state or physical writes."""
from copy import deepcopy
from datetime import datetime,timedelta
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,model_validator

class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
class Intervention(Strict):
    kind:Literal['grid_outage','pump_failure','supply_interruption','occupancy_surge','opd_surge','heat_increase',
                 'water_leak','excess_energy','delayed_pickup','earlier_pickup','schedule_change','asset_restoration','rainfall']
    start_hour:float=Field(default=0,ge=0,le=72)
    duration_hours:float=Field(default=6,gt=0,le=72)
    amount:float=Field(default=0,ge=0,le=10000)
    target:Literal['potable','process','nonessential','pump','grid','waste','parking']='potable'
    @model_validator(mode='after')
    def limits(self):
        if self.kind in {'occupancy_surge','opd_surge','schedule_change'} and self.amount>100:
            raise ValueError('Percentage intervention exceeds 100')
        if self.kind=='heat_increase' and self.amount>15:raise ValueError('Heat increase exceeds 15 C')
        return self
class Tank(Strict):
    name:str
    kind:Literal['potable','process','fire']
    capacity_l:float=Field(gt=0)
    reserve_l:float=Field(ge=0)
    inflow_lph:float=Field(ge=0)
    essential_lph:float=Field(ge=0)
    nonessential_lph:float=Field(default=0,ge=0)
    @model_validator(mode='after')
    def balance(self):
        if self.reserve_l>self.capacity_l:raise ValueError('Reserve exceeds capacity')
        if self.kind=='fire' and self.essential_lph+self.nonessential_lph>0:
            raise ValueError('Protected fire reserve cannot supply routine demand')
        return self
class Baseline(Strict):
    as_of:datetime
    snapshot_version:int=Field(ge=1)
    demand_source:str
    tanks:list[Tank]
    battery_deliverable_kwh:float=Field(ge=0,default=120)
    essential_load_kw:float=Field(ge=0,default=60)
    nonessential_load_kw:float=Field(ge=0,default=20)
    pump_load_kw:float=Field(ge=0,default=5)
    genset_max_kw:float=Field(ge=0,default=0)
    fuel_l:float=Field(ge=0,default=0)
    fuel_l_per_kwh:float=Field(gt=0,default=.3)
    waste_fill_pct:float=Field(ge=0,default=30)
    waste_growth_pph:float=Field(ge=0,default=2)
    waste_age_hours:float|None=Field(ge=0,default=None)
    waste_fill_threshold_pct:float=Field(ge=0,le=100,default=85)
    waste_age_limit_hours:float=Field(gt=0,default=24)
    pickup_after_hours:float|None=Field(ge=0,default=12)
    parking_capacity:int=Field(gt=0,default=120)
    parking_occupancy:int=Field(ge=0,default=60)
    arrivals_per_hour:float=Field(ge=0,default=20)
    exits_per_hour:float=Field(ge=0,default=20)
    initial_queue:float=Field(ge=0,default=0)
    tariff_inr_per_kwh:float|None=Field(ge=0,default=None)
    carbon_kg_per_kwh:float|None=Field(ge=0,default=None)
    versions:dict=Field(default_factory=dict)
    @model_validator(mode='after')
    def time_capacity(self):
        if self.as_of.tzinfo is None:raise ValueError('Timezone required')
        if self.parking_occupancy>self.parking_capacity:raise ValueError('Parking over capacity')
        return self
class Scenario(Strict):
    name:str=Field(min_length=1,max_length=200)
    horizon_hours:int=Field(default=24,ge=1,le=72)
    step_minutes:Literal[15]=15
    events:list[Intervention]=Field(default_factory=list,max_length=20)
    sensitivity_pct:float=Field(default=20,ge=0,le=50)
    assumptions:str=Field(default='',max_length=2000)


def reserve_deadline(reserve_l,demand_lph,inflow_lph=0,excess_lph=0):
    if min(reserve_l,demand_lph,inflow_lph,excess_lph)<0:raise ValueError('Negative reserve parameters')
    drain=demand_lph+excess_lph-inflow_lph
    return {'hours_to_depletion':reserve_l/drain if drain>0 else None,'net_drain_lph':drain}

def waste_deadline(fill_pct,growth_pph,age_hours,threshold_pct=85,age_limit=24):
    fill=max(0,(threshold_pct-fill_pct)/growth_pph) if growth_pph>0 else (0 if fill_pct>=threshold_pct else None)
    age=max(0,age_limit-age_hours) if age_hours is not None and age_limit is not None else None
    known=[v for v in (fill,age) if v is not None]
    return {'hours_to_fill_threshold':fill,'hours_to_age_limit':age,'service_within_hours':min(known) if known else None,
            'age_status':'unknown' if age_hours is None else 'known','policy_note':'Configurable internal demo policy, not a legal limit'}

def simulate_path(baseline:Baseline,scenario:Scenario,multiplier=1):
    b=baseline.model_dump();dt=scenario.step_minutes/60
    tanks=deepcopy(b['tanks']);battery=b['battery_deliverable_kwh'];fuel=b['fuel_l']
    fill=b['waste_fill_pct'];age=b['waste_age_hours'];occupancy=float(b['parking_occupancy']);queue=b['initial_queue']
    total={'unmet_essential_water_l':0.,'unmet_nonessential_water_l':0.,'unmet_essential_energy_kwh':0.,
           'unmet_nonessential_energy_kwh':0.,'grid_energy_kwh':0.,'genset_energy_kwh':0.,'battery_energy_kwh':0.,
           'spilled_water_l':0.,'served_water_l':0.,'water_inflow_l':0.,'rejected_arrivals':0.}
    points=[];violations=[];pickup_done=False
    pickup=b['pickup_after_hours']
    for event in scenario.events:
        if event.kind=='delayed_pickup' and pickup is not None:pickup+=event.amount
        if event.kind=='earlier_pickup':pickup=event.start_hour
    deadline=waste_deadline(fill,b['waste_growth_pph']*multiplier,age,b['waste_fill_threshold_pct'],b['waste_age_limit_hours'])
    for i in range(int(scenario.horizon_hours/dt)):
        t=i*dt
        active=[e for e in scenario.events if e.start_hour<=t<e.start_hour+e.duration_hours]
        restored={e.target for e in active if e.kind=='asset_restoration'}
        grid=not any(e.kind=='grid_outage' for e in active) or 'grid' in restored
        pump=not any(e.kind=='pump_failure' for e in active) or 'pump' in restored
        supply=not any(e.kind=='supply_interruption' for e in active)
        activity=1+sum(e.amount/100 for e in active if e.kind in {'occupancy_surge','opd_surge'})
        heat=sum(e.amount for e in active if e.kind=='heat_increase')
        essential=b['essential_load_kw']*multiplier*activity*(1+.02*heat)
        nonessential=b['nonessential_load_kw']*multiplier*activity*(1+.04*heat)+sum(e.amount for e in active if e.kind=='excess_energy')
        reduction=sum(e.amount/100 for e in active if e.kind=='schedule_change')
        nonessential*=max(0,1-reduction)
        desired=(essential+b['pump_load_kw']+nonessential)*dt
        if grid:
            available=desired;total['grid_energy_kwh']+=available
        else:
            genset=min(b['genset_max_kw']*dt,fuel/b['fuel_l_per_kwh'],desired)
            fuel-=genset*b['fuel_l_per_kwh'];total['genset_energy_kwh']+=genset
            delivered=min(battery,desired-genset);battery-=delivered;total['battery_energy_kwh']+=delivered
            available=genset+delivered
        served_essential=min(essential*dt,available);available-=served_essential
        served_pump=min(b['pump_load_kw']*dt,available);available-=served_pump
        pump=bool(pump and (b['pump_load_kw']==0 or served_pump>=b['pump_load_kw']*dt-1e-9))
        served_nonessential=min(nonessential*dt,available)
        total['unmet_essential_energy_kwh']+=essential*dt-served_essential
        total['unmet_nonessential_energy_kwh']+=nonessential*dt-served_nonessential
        step_unmet=0
        for tank in tanks:
            if tank['kind']=='fire':continue
            inflow=tank['inflow_lph']*dt if pump and supply else 0
            excess=sum(e.amount for e in active if e.kind=='water_leak' and e.target==tank['kind'])*dt
            essential_water=tank['essential_lph']*dt*multiplier*activity
            nonessential_water=tank['nonessential_lph']*dt*multiplier*activity+excess
            # Inflow first, then use demand; spill is accounted, never silently clipped.
            available_water=tank['reserve_l']+inflow
            served_e=min(essential_water,available_water);available_water-=served_e
            served_n=min(nonessential_water,available_water);available_water-=served_n
            spill=max(0,available_water-tank['capacity_l']);tank['reserve_l']=available_water-spill
            total['water_inflow_l']+=inflow;total['served_water_l']+=served_e+served_n;total['spilled_water_l']+=spill
            total['unmet_essential_water_l']+=essential_water-served_e;step_unmet+=essential_water-served_e
            total['unmet_nonessential_water_l']+=nonessential_water-served_n
        if pickup is not None and t>=pickup and not pickup_done:
            fill=0;age=0;pickup_done=True
        fill+=b['waste_growth_pph']*dt*multiplier*activity
        if age is not None:age+=dt
        exits=min(occupancy,b['exits_per_hour']*dt);occupancy-=exits
        arrivals=b['arrivals_per_hour']*dt*activity+queue
        admitted=min(arrivals,b['parking_capacity']-occupancy);occupancy+=admitted
        queue=arrivals-admitted
        blocked=any(e.kind=='rainfall' for e in active) or queue>10
        if step_unmet>0:violations.append({'hour':t+dt,'kind':'unmet_essential_water','value_l':step_unmet})
        if essential*dt-served_essential>0:violations.append({'hour':t+dt,'kind':'unmet_essential_power','value_kwh':essential*dt-served_essential})
        points.append({'hour':t+dt,'at':(baseline.as_of+timedelta(hours=t+dt)).isoformat(),
          'tanks':{tank['name']:tank['reserve_l'] for tank in tanks},'battery_kwh':battery,'fuel_l':fuel,
          'waste_fill_pct':fill,'waste_age_hours':age,'parking_occupancy':occupancy,'parking_queue':queue,
          'protected_route_at_risk':blocked,'pump_available':pump,'grid_available':grid,
          'unmet_essential_water_l':total['unmet_essential_water_l'],'unmet_essential_energy_kwh':total['unmet_essential_energy_kwh']})
    return {'points':points,'totals':{**total,'remaining_water_l':sum(t['reserve_l'] for t in tanks if t['kind']!='fire'),
              'initial_water_l':sum(t['reserve_l'] for t in b['tanks'] if t['kind']!='fire'),
              'cost_estimate_inr':total['grid_energy_kwh']*b['tariff_inr_per_kwh'] if b['tariff_inr_per_kwh'] is not None else None,
              'carbon_estimate_kgco2e':total['grid_energy_kwh']*b['carbon_kg_per_kwh'] if b['carbon_kg_per_kwh'] is not None else None,
              'final_parking_queue':queue},'violations':violations,'waste_deadline':deadline,
            'battery_runtime_hours':b['battery_deliverable_kwh']/b['essential_load_kw'] if b['essential_load_kw'] else None,
            'demand_multiplier':multiplier}

def run_engine(baseline:Baseline,scenario:Scenario):
    central=simulate_path(baseline,scenario)
    normal=simulate_path(baseline,scenario.model_copy(update={'events':[]}))
    low=simulate_path(baseline,scenario,1-scenario.sensitivity_pct/100)
    high=simulate_path(baseline,scenario,1+scenario.sensitivity_pct/100)
    return {'central':central,'baseline':normal,'sensitivity':{'low':low['totals'],'high':high['totals'],
            'label':'Demand sensitivity range, not statistical confidence'},
            'deltas':{k:central['totals'][k]-normal['totals'][k] if central['totals'][k] is not None and normal['totals'][k] is not None else None for k in central['totals']},
            'source_type':'simulated','limitations':['Constant demand/pump assumptions from frozen snapshot; no validated trajectory forecasting.',
             'Battery capacity is deliverable; efficiency is not applied twice. Genset uses explicit linear L/kWh curve.',
             'Fire water is protected. Waste may exceed capacity; queue and unmet demand remain visible.',
             'Carbon covers grid energy only; genset embodied/fuel emissions omitted. Modeled deltas are not measured savings.']}
