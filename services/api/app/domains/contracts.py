"""Typed operational write contracts. Free-form documents are data, never instructions."""
from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel,ConfigDict,Field,model_validator

class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
class Building(Strict):
    address:str=Field(default='',max_length=500)
    gross_area_m2:float=Field(gt=0)
class Floor(Strict):
    level:int=Field(ge=-5,le=100)
    area_m2:float=Field(gt=0)
class Zone(Strict):
    source_zone_code:int=Field(ge=0)
    bed_capacity:int=Field(ge=0,le=2000)
    protected:bool=False
class Capacity(Strict):
    bed_capacity:int=Field(ge=0,le=2000)
class Schedule(Strict):
    start_hour:int=Field(ge=0,le=23)
    end_hour:int=Field(ge=1,le=24)
    days:list[int]=Field(min_length=1,max_length=7)
    essential:bool=False
    policy_source:str=Field(min_length=1,max_length=500)
class Asset(Strict):
    kind:Literal['pump','hvac','meter','genset','battery','bin','gate']
    mode:Literal['operational','degraded','offline','inspection']='operational'
    critical:bool=False
    rated_kw:float=Field(ge=0,default=0)
    inspection_interval_days:int=Field(gt=0,default=30)
class Dependency(Strict):
    from_asset_id:UUID
    to_asset_id:UUID
    resource:Literal['power','water','access']
class Maintenance(Strict):
    asset_id:UUID
    inspection_type:Literal['inspection','repair','preventive']
    notes:str=Field(default='',max_length=4000)
class TankConfig(Strict):
    kind:Literal['potable','process','fire']
    capacity_l:float=Field(gt=0)
    initial_reserve_l:float=Field(ge=0)
    inflow_lph:float=Field(ge=0)
    essential_lph:float=Field(ge=0)
    nonessential_lph:float=Field(ge=0,default=0)
    @model_validator(mode='after')
    def valid(self):
        if self.initial_reserve_l>self.capacity_l:raise ValueError('Reserve exceeds capacity')
        if self.kind=='fire' and self.essential_lph+self.nonessential_lph>0:raise ValueError('Fire reserves are protected')
        return self
class WasteBin(Strict):
    category:Literal['yellow','red','white','blue']
    capacity_kg:float=Field(gt=0)
class WasteBatch(Strict):
    category:Literal['yellow','red','white','blue']
    bin_id:UUID
    generated_kg:float=Field(gt=0)
    generated_at:datetime
    @model_validator(mode='after')
    def date(self):
        if self.generated_at.tzinfo is None:raise ValueError('Timezone required')
        return self
class Pickup(Strict):
    batch_ids:list[UUID]=Field(min_length=1,max_length=100)
    vehicle_reference:str=Field(min_length=1,max_length=100)
    handover_reference:str=Field(min_length=1,max_length=200)
    collected_at:datetime
    destination:str=Field(min_length=1,max_length=200)
class Environment(Strict):
    temperature_c:float=Field(ge=-30,le=65)
    humidity_pct:float=Field(ge=0,le=100)
    pm25_ug_m3:float=Field(ge=0,le=3000)
    co2_ppm:float=Field(ge=0,le=20000)
    outdoor:bool=False
class ParkingArea(Strict):
    capacity:int=Field(gt=0,le=10000)
    protected_route:str=Field(min_length=1,max_length=200)
class ParkingEvent(Strict):
    direction:Literal['arrival','exit']
    count:int=Field(gt=0,le=1000)
class Incident(Strict):
    kind:Literal['spill','blocked_route','equipment','slip','fire_risk','other']
    description:str=Field(min_length=3,max_length=4000)
    denominator_type:Literal['zone_hours','vehicle_arrivals','inspections']='zone_hours'
class Policy(Strict):
    source:str=Field(min_length=1,max_length=500)
    jurisdiction:str=Field(min_length=1,max_length=200)
    effective_from:datetime
    age_limit_hours:float|None=Field(default=None,gt=0)
    fill_threshold_pct:float|None=Field(default=None,gt=0,le=100)
    category_applicability:list[str]=Field(default_factory=list,max_length=10)
    temperature_max_c:float|None=None
    pm25_max_ug_m3:float|None=Field(default=None,ge=0)
    co2_max_ppm:float|None=Field(default=None,ge=0)
    humidity_min_pct:float|None=Field(default=None,ge=0,le=100)
    humidity_max_pct:float|None=Field(default=None,ge=0,le=100)
class Accounting(Strict):
    value:float=Field(ge=0)
    unit:Literal['INR/kWh','kgCO2e/kWh']
    source:str=Field(min_length=1,max_length=500)
    geography:str=Field(min_length=1,max_length=200)
    year:int=Field(ge=2000,le=2100)
    effective_from:datetime
    assumption:bool=True
class Document(Strict):
    body:str=Field(min_length=1,max_length=100000)
    source:str=Field(min_length=1,max_length=500)
    policy_version:str=Field(min_length=1,max_length=100)
class AgentPolicy(Strict):
    monitor_enabled:bool=False
    autonomous_task_creation:bool=False
    categories:list[Literal['maintenance','waste','water','energy','environment','parking','safety','sustainability']]=Field(default_factory=list)
    severities:list[Literal['medium','high','critical']]=Field(default_factory=lambda:['high','critical'])
    owner_pool:list[UUID]=Field(default_factory=list,max_length=20)
    max_tasks_per_day:int=Field(default=2,ge=0,le=10)
    cooldown_hours:float=Field(default=6,ge=1,le=168)
    daily_brief:bool=False

CONTRACTS={'buildings':(Building,'facility'),'floors':(Floor,'facility'),'zones':(Zone,'facility'),
 'zone_capacities':(Capacity,'facility'),'operating_schedules':(Schedule,'facility'),'assets':(Asset,'assets'),
 'asset_dependencies':(Dependency,'assets'),'maintenance_orders':(Maintenance,'assets'),'tanks':(TankConfig,'facility'),
 'waste_bins':(WasteBin,'waste'),'waste_batches':(WasteBatch,'waste'),'pickups':(Pickup,'waste'),
 'environment_readings':(Environment,'environment'),'parking_areas':(ParkingArea,'parking'),
 'parking_events':(ParkingEvent,'parking'),'safety_incidents':(Incident,'safety'),
 'policy_versions':(Policy,'policy'),'tariff_versions':(Accounting,'sustainability'),'emission_factor_versions':(Accounting,'sustainability'),
 'documents':(Document,'policy'),'agent_policies':(AgentPolicy,'policy')}

class RecordInput(Strict):
    name:str=Field(min_length=1,max_length=200)
    zone_code:str|None=Field(default=None,max_length=80)
    category:str=Field(default='',max_length=80)
    status:str=Field(default='active',pattern='^(active|operational|offline|open|in_progress|resolved|stored|collected)$')
    severity:Literal['info','low','medium','high','critical']='info'
    owner_id:UUID|None=None
    parent_id:UUID|None=None
    due_at:datetime|None=None
    event_at:datetime|None=None
    data:dict
    expected_version:int|None=None
