"""Independent causal extended-world generator. Observable state only enters runtime ledgers."""
import hashlib
import json
import math
from datetime import datetime,timedelta
from pathlib import Path
from uuid import uuid4
import numpy as np
import yaml
from sqlalchemy import select,text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app.core.models import TABLES,World
from app.core.auth import resolve_scope
from app.core.records import insert
from app.domains.importer import import_rows

VERSION='extended-generator-v1'
DEFAULT_ZONES=[('ICU',24,11),('WARD_A',72,6),('WARD_B',72,5.8),('OPD',0,8.5),('SERVICES',0,7),('ADMIN',0,4)]
FAULT_CATALOGUE=['excessive_energy','water_leak','missing_sensor','stuck_sensor','pump_outage','grid_outage',
                 'delayed_waste_pickup','bin_capacity_pressure','heat_load_surge','asset_telemetry_fault','parking_surge']

def generate_rows(config,truth_sink=None):
    seed=int(config['seed']);days=int(config.get('days',180));zone_count=int(config.get('zones',6))
    if not 1<=days<=365 or not 4<=zone_count<=12:raise ValueError('Use 1–365 days and 4–12 zones')
    rng=np.random.default_rng(seed);start=datetime.fromisoformat(str(config.get('start','2025-01-01T00:00:00Z')).replace('Z','+00:00'))
    zones=DEFAULT_ZONES[:zone_count]+[(f'SERVICE_{i}',0,5+i*.1) for i in range(len(DEFAULT_ZONES),zone_count)]
    demand_scale=float(config.get('demand_scale',1));weather_offset=float(config.get('weather_offset_c',0));fault_scale=float(config.get('fault_scale',1))
    if not .5<=demand_scale<=2 or not -10<=weather_offset<=10 or not .2<=fault_scale<=3:raise ValueError('Generator profile outside supported ranges')
    sensor_hours=config.get('sensor_error_hours',[3,18])
    if not 1<=sensor_hours[0]<sensor_hours[1]<=48:raise ValueError('Invalid intervention duration range')
    rows=[];states=[]
    # Private sampled interventions remain ephemeral; offline campaign may write them only to research/evaluation.
    intervals=[]
    for kind in FAULT_CATALOGUE:
        for _ in range(max(1,days//30)):
            begin=int(rng.integers(0,max(1,days*24-24)));length=int(rng.integers(*sensor_hours))
            intervals.append((kind,begin,begin+length,int(rng.integers(0,zone_count))))
    reserve=30000.;process=12000.;battery=120.;fuel=180.;parking=40;queue=0
    stock={z:0. for z,_,_ in zones};ages={z:0 for z,_,_ in zones}
    for i in range(days*24):
        at=start+timedelta(hours=i);hour=at.hour
        active={(kind,zone) for kind,a,b,zone in intervals if a<=i<b}
        grid=not any(k=='grid_outage' for k,z in active)
        pump=grid and not any(k=='pump_outage' for k,z in active)
        temp=29+weather_offset+5*math.sin(i/24*math.tau/365)+4*math.sin((hour-8)*math.tau/24)+rng.normal(0,.7)
        if any(k=='heat_load_surge' for k,z in active):temp+=4
        context=[];water_demand=0.;energy_total=0.;waste_total=0.
        for code,(zone,beds,base) in enumerate(zones):
            occupancy=int(round(beds*float(np.clip(.68+.1*math.sin(i/24*math.tau/14+code)+rng.normal(0,.035),.35,.97))))
            opened=8<=hour<=17 and at.weekday()<6
            opd=int(rng.poisson(25 if zone=='OPD' else 2)) if opened else 0
            cleaning=int(hour in [6,14,20])
            energy=max(0,base+.11*occupancy+.15*opd+.55*max(temp-25,0)+1.7*cleaning+rng.normal(0,.3))
            water=max(0,22+2.3*occupancy+2.5*opd+85*cleaning+rng.normal(0,5))
            energy*=demand_scale;water*=demand_scale
            if ('excessive_energy',code) in active:energy+=8*fault_scale
            if ('water_leak',code) in active:water+=150*fault_scale
            generated=max(0,.014*occupancy+.025*opd+.04+rng.normal(0,.02))
            if ('bin_capacity_pressure',code) in active:generated*=2
            pickup=hour in [7,19] and not any(k=='delayed_waste_pickup' for k,z in active)
            if pickup:stock[zone]=0;ages[zone]=0
            stock[zone]+=generated;ages[zone]+=1
            observed_water=None if ('missing_sensor',code) in active else round(water,3)
            if ('stuck_sensor',code) in active:observed_water=100.
            rows.append({'observed_at':at.isoformat(),'facility_id':'DEMO_HOSPITAL','zone_id':zone,'zone_code':code,'bed_capacity':beds,
                         'occupied_beds':occupancy,'opd_visits':opd,'temperature_c':round(temp,3),'cleaning_schedule':cleaning,
                         'energy_kwh':round(energy,4),'water_l':observed_water,'waste_generated_kg':round(generated,4),
                         'waste_stock_kg':round(stock[zone],4),'bin_fill_pct':round(stock[zone]/25*100,3),
                         'oldest_batch_age_hours':ages[zone],'pickup_recorded':int(pickup),'source_type':'synthetic_extended_v1',
                         'quality':'missing_water' if observed_water is None else 'ok'})
            context.append({'zone':zone,'temperature_c':round(temp,3),'humidity_pct':round(float(np.clip(60+10*math.sin(i/24)+rng.normal(0,3),20,95)),2),
                            'pm25_ug_m3':round(max(0,18+.2*opd+rng.normal(0,3)),2),'co2_ppm':round(410+3*occupancy+4*opd+rng.normal(0,15),2),'outdoor':False,
                            'waste_generated_kg':round(generated,4),'pickup':pickup,'asset_fault':('asset_telemetry_fault',code) in active})
            water_demand+=water;energy_total+=energy;waste_total+=generated
        inflow=1600. if pump else 0.
        before=reserve;served=min(before+inflow,water_demand*.8);spill=max(0,before+inflow-served-30000);reserve=before+inflow-served-spill
        process_in=400. if pump else 0.;process_served=min(process+process_in,water_demand*.2);process_spill=max(0,process+process_in-process_served-12000);process=process+process_in-process_served-process_spill
        if grid:battery=min(120.,battery+30)
        else:battery=max(0,battery-min(battery,60.))
        total_opd=sum(r['opd_visits'] for r in rows[-len(zones):]);arrivals=int(rng.poisson(5+.2*total_opd))
        if any(k=='parking_surge' for k,z in active):arrivals+=50
        exits=min(parking,int(rng.poisson(10 if hour>=16 else 5)));parking-=exits
        admitted=min(120-parking,arrivals+queue);parking+=admitted;queue=arrivals+queue-admitted
        states.append({'at':at,'grid':grid,'pump':pump,'water':reserve,'process':process,'inflow':inflow,'process_inflow':process_in,
           'served':served,'process_served':process_served,'unmet':water_demand*.8-served,'process_unmet':water_demand*.2-process_served,
           'spill':spill,'process_spill':process_spill,'battery':battery,'fuel':fuel,'parking':parking,'queue':queue,'arrivals':arrivals,
           'exits':exits,'context':context,'temperature_c':temp})
        if truth_sink:
            truth_sink({'at':at.isoformat(),'faults':[{'kind':k,'zone_code':z} for k,z in active]})
    return rows,states,zones

def generate(db,principal,path):
    config=yaml.safe_load(Path(path).read_text())
    if config.get('facility_count',1)!=1:raise ValueError('Use offline generate_campaign.py for multi-facility campaign')
    world=db.scalar(select(World).where(World.code==config.get('world','extended_v1')))
    if not world:raise ValueError('World must be provisioned by demo migration bootstrap')
    scope=resolve_scope(db,principal,world.id);scope.require('imports')
    config_hash=hashlib.sha256(json.dumps(config,sort_keys=True,default=str).encode()).hexdigest()
    old=db.scalar(select(TABLES['dataset_versions']).where(TABLES['dataset_versions'].world_id==world.id,TABLES['dataset_versions'].idempotency_key==VERSION))
    if old:
        if old.data.get('config_sha256')!=config_hash:raise ValueError('Immutable world already generated from a different config; use a new world version')
        return {'status':'already_generated','world':world.code,'rows':old.data['rows'],'dataset_sha256':old.data['sha256']}
    rows,states,zones=generate_rows(config)
    sha=hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()
    summary=import_rows(db,scope,rows,VERSION,sha,{'facility_id':'DEMO_HOSPITAL','bed_capacity':sum(b for z,b,k in zones),'source_type':'synthetic_extended_v1'})
    dataset=db.scalar(select(TABLES['dataset_versions']).where(TABLES['dataset_versions'].world_id==world.id,TABLES['dataset_versions'].idempotency_key==VERSION))
    dataset.data={**dataset.data,'config_sha256':config_hash,'seed':config['seed'],'generator_version':VERSION,'generator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  'rows':len(rows),'provenance':'Independent extended world; not reconstruction of starter waste categories'}
    first=states[0]['at'];last=states[-1]['at']
    building=insert(db,scope,'buildings',{'address':'Fictional facility, India','gross_area_m2':12000},name='Riverbend Main Building',event_at=first,source_type='synthetic_extended_v1')
    for level in [0,1,2]:insert(db,scope,'floors',{'level':level,'area_m2':4000},name=f'Floor {level}',parent_id=building.id,event_at=first,source_type='synthetic_extended_v1')
    asset_ids={}
    for zone,beds,kw in zones:
        a=insert(db,scope,'assets',{'kind':'pump' if zone=='SERVICES' else 'hvac','mode':'operational','critical':zone in ['ICU','SERVICES'],'rated_kw':kw,'inspection_interval_days':30},
                 name=f'{zone} '+('Supply pump' if zone=='SERVICES' else 'Air handling unit'),zone_code=zone,event_at=first,source_type='synthetic_extended_v1')
        asset_ids[zone]=a.id
        insert(db,scope,'operating_schedules',{'start_hour':0 if beds else 8,'end_hour':24 if beds else 18,'days':list(range(7)),'essential':zone=='ICU','policy_source':'Internal demonstration schedule'},
               name=zone+' operations',zone_code=zone,event_at=first,source_type='synthetic_extended_v1')
    insert(db,scope,'asset_dependencies',{'from_asset_id':str(asset_ids['SERVICES']),'to_asset_id':str(asset_ids['ICU']),'resource':'water'},name='Pump supplies essential zones',event_at=first,source_type='synthetic_extended_v1')
    tank_ids={}
    for name,kind,capacity,inflow,essential,non in [('Potable reserve','potable',30000,1600,700,100),('Process reserve','process',12000,400,100,100),('Protected fire reserve','fire',10000,0,0,0)]:
        tank_ids[kind]=insert(db,scope,'tanks',{'kind':kind,'capacity_l':capacity,'initial_reserve_l':capacity,'inflow_lph':inflow,'essential_lph':essential,'nonessential_lph':non},name=name,event_at=first,source_type='synthetic_extended_v1').id
    power=insert(db,scope,'power_sources',{'grid':True,'battery_deliverable_kwh':120,'genset_max_kw':80,'fuel_curve_l_per_kwh':.3},name='Grid and deliverable backup',event_at=first,source_type='synthetic_extended_v1')
    area=insert(db,scope,'parking_areas',{'capacity':120,'protected_route':'Emergency service access'},name='Main parking',zone_code='SERVICES',event_at=first,source_type='synthetic_extended_v1')
    bins={}
    for cat in ['yellow','red','white','blue']:
        insert(db,scope,'waste_categories',{'colour':cat,'policy_source':'Synthetic colour ledger; consult applicable local SOP'},name=cat,event_at=first,source_type='synthetic_extended_v1')
        for zone,_,_ in zones:
            bins[zone,cat]=insert(db,scope,'waste_bins',{'category':cat,'capacity_kg':12},name=f'{zone} {cat}',category=cat,zone_code=zone,event_at=first,source_type='synthetic_extended_v1').id
    for category,data in [('waste',{'source':'Internal demonstration SOP','jurisdiction':'Demo only','effective_from':first.isoformat(),'age_limit_hours':24,'fill_threshold_pct':85,'category_applicability':['yellow','red','white','blue']}),
                          ('environment',{'source':'Internal demonstration thresholds, not clinical standards','jurisdiction':'Demo only','effective_from':first.isoformat(),'temperature_max_c':35,'pm25_max_ug_m3':35,'co2_max_ppm':1000})]:
        insert(db,scope,'policy_versions',data,name=category.title()+' demo SOP',category=category,event_at=first,source_type='synthetic_extended_v1')
    for table,value,unit,name in [('tariff_versions',8.,'INR/kWh','Demo consumption tariff'),('emission_factor_versions',.7,'kgCO2e/kWh','Demo grid factor')]:
        insert(db,scope,table,{'value':value,'unit':unit,'source':'Explicit illustrative assumption, not an official current factor','geography':'Fictional demonstration in India','year':2025,'effective_from':first.isoformat(),'assumption':True},name=name,value=value,unit=unit,event_at=first,source_type='synthetic_extended_v1')
    doc=insert(db,scope,'documents',{'body':'Demo operating SOP: protect essential water and fire reserves. Inspect sustained excess using observation evidence. Waste age threshold is internal and configurable. Record pickup handover metadata. Never operate physical equipment from software.',
               'source':'Internal synthetic demo','policy_version':'demo-sop-v1'},name='GreenOps operational SOP',event_at=first,source_type='synthetic_extended_v1')
    insert(db,scope,'document_chunks',{**doc.data,'title':doc.name},name=doc.name,parent_id=doc.id,event_at=first,source_type='synthetic_extended_v1')
    pending={table:[] for table in ['tank_states','power_states','environment_readings','parking_events','parking_snapshots','asset_telemetry','waste_batches','waste_movements','pickups','handover_evidence','safety_incidents']}
    def add(table,data,at,**kwargs):
        rid=kwargs.pop('id',uuid4());pending[table].append({**scope.keys,'id':rid,'event_at':at,'data':data,'source_type':'synthetic_extended_v1',**kwargs});return rid
    def flush():
        for table,items in pending.items():
            if items:
                for i in range(0,len(items),100):db.execute(pg_insert(TABLES[table]).values(items[i:i+100]).on_conflict_do_nothing())
                items.clear()
    accum={(z,c):0. for z,_,_ in zones for c in ['yellow','red','white','blue']};batch_start=first
    fractions={'yellow':.45,'red':.3,'white':.1,'blue':.15}
    for i,state in enumerate(states):
        at=state['at']
        for kind,reserve,inflow,served,unmet,spill in [('potable',state['water'],state['inflow'],state['served'],state['unmet'],state['spill']),('process',state['process'],state['process_inflow'],state['process_served'],state['process_unmet'],state['process_spill']),('fire',10000,0,0,0,0)]:
            add('tank_states',{'kind':kind,'reserve_l':reserve,'inflow_lph':inflow,'served_l':served,'unmet_l':unmet,'spill_l':spill},at,parent_id=tank_ids[kind],name=kind,value=reserve,unit='L')
        add('power_states',{'grid_available':state['grid'],'battery_deliverable_kwh':state['battery'],'fuel_l':state['fuel'],'genset_max_kw':80,'essential_load_kw':60,'nonessential_load_kw':20},at,parent_id=power.id,name='Supply state')
        add('parking_events',{'direction':'arrival','count':state['arrivals']},at,parent_id=area.id,name='Hourly arrivals',zone_code='SERVICES',value=state['arrivals'],unit='vehicles')
        add('parking_events',{'direction':'exit','count':state['exits']},at,parent_id=area.id,name='Hourly exits',zone_code='SERVICES',value=state['exits'],unit='vehicles')
        add('parking_snapshots',{'capacity':120,'occupancy':state['parking'],'queue':state['queue'],'arrivals':state['arrivals'],'exits':state['exits'],'protected_route_at_risk':state['queue']>10},at,parent_id=area.id,name='Hourly parking balance',zone_code='SERVICES')
        for c in state['context']:
            zone=c['zone'];env={k:c[k] for k in ['temperature_c','humidity_pct','pm25_ug_m3','co2_ppm','outdoor']}
            add('environment_readings',env,at,zone_code=zone,name='Indoor environment')
            mode='offline' if zone=='SERVICES' and not state['pump'] else 'degraded' if c['asset_fault'] else 'operational'
            add('asset_telemetry',{'mode':mode,'temperature_c':c['temperature_c'],'sensor_quality':'suspect' if c['asset_fault'] else 'ok','power_available':state['grid']},at,parent_id=asset_ids[zone],zone_code=zone,name='Asset telemetry')
            for cat,fraction in fractions.items():accum[zone,cat]+=c['waste_generated_kg']*fraction
        if (i+1)%12==0 or i==len(states)-1:
            for (zone,cat),kg in accum.items():
                batch=add('waste_batches',{'category':cat,'bin_id':str(bins[zone,cat]),'generated_kg':kg,'generated_at':batch_start.isoformat(),'stream':'independent_extended_ledger'},batch_start,zone_code=zone,category=cat,name=f'{zone} {cat} batch',status='collected' if i<len(states)-13 else 'stored',value=kg,unit='kg')
                add('waste_movements',{'kind':'generated','kg':kg,'bin_id':str(bins[zone,cat])},batch_start,parent_id=batch,zone_code=zone,name='Generated',value=kg,unit='kg')
                if i<len(states)-13:
                    # Synthetic ledger pickups are independent records, never claimed reconstructed from base/stress waste.
                    pickup=add('pickups',{'batch_ids':[str(batch)],'vehicle_reference':'SYN-'+at.strftime('%j'),'handover_reference':'SYN-HO-'+str(batch),'collected_at':at.isoformat(),'destination':'Fictional licensed treatment operator','stream':'independent_extended_ledger'},at,zone_code=zone,name=cat+' pickup',status='recorded',value=kg,unit='kg')
                    add('waste_movements',{'kind':'collected','kg':kg,'pickup_id':str(pickup)},at,parent_id=batch,zone_code=zone,name='Collected',value=-kg,unit='kg')
                    add('handover_evidence',{'reference':'SYN-HO-'+str(batch),'source_type':'synthetic_metadata','note':'Synthetic metadata, not physical proof'},at,parent_id=pickup,zone_code=zone,name='Synthetic handover')
                accum[zone,cat]=0
            batch_start=at+timedelta(hours=1)
        if i%97==0:
            add('safety_incidents',{'kind':'blocked_route' if state['queue']>10 else 'spill','description':'Generated operational incident for demonstration; no patient information','denominator_type':'zone_hours'},at,zone_code='SERVICES',name='Synthetic safety observation',severity='medium',status='open')
        if i%96==95:flush()
    flush()
    insert(db,scope,'agent_policies',{'monitor_enabled':False,'autonomous_task_creation':False,'categories':['maintenance','waste'],
                'severities':['high','critical'],'owner_pool':[],'max_tasks_per_day':2,'cooldown_hours':6,'daily_brief':False},name='Monitor disabled until configured',event_at=first)
    return {'status':'generated','world':world.code,'rows':len(rows),'dataset_sha256':sha,'config_sha256':config_hash,'import':summary['data']}
