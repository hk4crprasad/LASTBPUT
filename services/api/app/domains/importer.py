import csv
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app.core.models import TABLES, Observation
from app.core.records import insert, serialize

FIELDS = {'energy_kwh':('energy.interval_kwh','kWh','interval'), 'water_l':('water.interval_l','L','interval'),
          'waste_generated_kg':('waste.generated_kg','kg','interval'), 'waste_stock_kg':('waste.stock_kg','kg','state'),
          'bin_fill_pct':('waste.fill_pct','%','state'), 'oldest_batch_age_hours':('waste.age_hours','h','state'),
          'pickup_recorded':('waste.pickup_recorded','flag','state')}
PUBLIC_FIELDS = {'observed_at','facility_id','zone_id','zone_code','bed_capacity','occupied_beds','opd_visits',
                 'temperature_c','cleaning_schedule','source_type','quality'} | set(FIELDS)
CONFIG_FIELDS = {'facility_id','facility_type','source_type','seed','days','stress','bed_capacity','interval_semantics',
                 'tank_usable_l','essential_water_lph','battery_deliverable_kwh','essential_load_kw','waste_note'}

def verify_bundle(root):
    root = Path(root)
    manifest = json.loads((root/'MANIFEST.json').read_text())
    if manifest.get('sanitizer_version') != 1:
        raise ValueError('Only sanitized bundles may be imported')
    for f in manifest['files']:
        path = (root/f['path']).resolve()
        if not path.is_relative_to(root.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest()!=f['sha256']:
            raise ValueError('Public bundle checksum mismatch')
    for file in root.rglob('*'):
        if 'private_label' in file.name:
            raise ValueError('Private truth in public bundle')
    for name in ['facility.json','stress_facility.json']:
        if set(json.loads((root/'data'/name).read_text()))-CONFIG_FIELDS:
            raise ValueError('Configuration is not sanitized')
    return manifest

def normalize(row):
    if set(row)-PUBLIC_FIELDS:
        raise ValueError('Unallowlisted source fields')
    t = datetime.fromisoformat(row['observed_at'].replace('Z','+00:00'))
    if not t.tzinfo:
        raise ValueError('Timestamp timezone required')
    values = {}
    for key in FIELDS:
        raw = row.get(key)
        values[key] = None if raw is None or str(raw).strip() in {'','nan','NaN'} else float(raw)
        if values[key] is not None and (not __import__('math').isfinite(values[key]) or values[key] < 0):
            raise ValueError(f'Negative {key}')
    capacity,occupied,opd,code = [int(row[k]) for k in ['bed_capacity','occupied_beds','opd_visits','zone_code']]
    if not 0 <= occupied <= capacity or opd < 0 or code < 0:
        raise ValueError('Invalid operational capacity/context')
    if values['pickup_recorded'] not in {0,1,None}:
        raise ValueError('Invalid pickup flag')
    if row['source_type'] not in {'synthetic','synthetic_extended_v1','aggregate_hms_import'}:
        raise ValueError('Unsupported source type')
    public = {k:row.get(k) for k in PUBLIC_FIELDS}
    public.update(values,observed_at=t.astimezone(timezone.utc).isoformat(),bed_capacity=capacity,occupied_beds=occupied,
                  opd_visits=opd,zone_code=code,temperature_c=float(row['temperature_c']),cleaning_schedule=int(row['cleaning_schedule']))
    return t,public,values

def import_rows(db,scope,rows,dataset_code,source_hash,config=None):
    datasets = TABLES['dataset_versions']
    dataset = db.scalar(select(datasets).where(datasets.world_id==scope.world.id,datasets.idempotency_key==dataset_code))
    if dataset and dataset.data['sha256'] != source_hash:
        raise ValueError('Dataset version already exists with different checksum')
    if not dataset:
        dataset = insert(db,scope,'dataset_versions',{'sha256':source_hash,'dataset_code':dataset_code},name=dataset_code,idempotency_key=dataset_code,source_type='synthetic')
    job = insert(db,scope,'import_jobs',{'dataset_id':str(dataset.id)},name=dataset_code,status='running')
    accepted,duplicates,rejected,conflicts = 0,0,0,0
    latest = None
    batch_sources,batch_obs,batch_context,batch_quality = [],[],[],[]
    existing = {(r.zone_code,r.event_at.isoformat()):r.data for r in db.scalars(select(TABLES['source_events']).where(TABLES['source_events'].world_id==scope.world.id))}
    zones = {}
    def flush():
        for table,items in [('source_events',batch_sources),('observations',batch_obs),('operational_snapshots',batch_context),('quality_events',batch_quality)]:
            if items:
                model = Observation if table=='observations' else TABLES[table]
                db.execute(pg_insert(model).values(items).on_conflict_do_nothing())
                items.clear()
    for number,row in enumerate(rows,1):
        try:
            t,public,values = normalize(row)
            if public['facility_id']!='DEMO_HOSPITAL':
                raise ValueError('Unexpected source facility')
            zone = public['zone_id']
            scope.zone(zone)
            sid = uuid5(NAMESPACE_URL,f'{dataset.id}/{zone}/{t.isoformat()}')
            canonical=(zone,t.isoformat())
            if canonical in existing:
                if existing[canonical]!=public:
                    conflicts+=1
                    raise ValueError('Conflicting duplicate source event')
                duplicates+=1
                continue
            existing[canonical] = public
            base = {**scope.keys,'zone_code':zone,'event_at':t,'source_type':public['source_type']}
            batch_sources.append({**base,'id':sid,'category':dataset_code,'name':f'{zone} {t.isoformat()}',
                                  'data':public,'idempotency_key':str(sid)})
            for key,(metric,unit,sem) in FIELDS.items():
                value = values[key]
                invalid_range = key=='bin_fill_pct' and value is not None and value>100
                if invalid_range:
                    insert(db,scope,'import_rejects',{'row_number':number,'metric':metric,'reason':'Fill above 100%; raw source preserved, normalized metric quarantined','raw_value':value},name=f'Row {number}: fill',parent_id=job.id,zone_code=zone)
                    value=None
                batch_obs.append({**scope.keys,'zone_code':zone,'metric':metric,'unit':unit,'value':value,
                    'interval_start':t-timedelta(hours=1) if sem=='interval' else None,'interval_end':t,
                    'quality':'invalid_range' if invalid_range else ('missing' if value is None else 'ok'),'source_type':public['source_type'],
                    'source_event_id':sid,'dataset_id':dataset.id})
                if value is None:
                    batch_quality.append({**base,'name':f'Missing {metric}','category':metric,'data':{'row':number,'source_event_id':str(sid),'quality':'missing'}})
            batch_context.append({**base,'parent_id':sid,'data':{k:public[k] for k in ['bed_capacity','occupied_beds','opd_visits','zone_code','temperature_c','cleaning_schedule']}})
            zones[zone] = (public['zone_code'],public['bed_capacity'])
            latest = max(latest,t) if latest else t
            accepted+=1
            if len(batch_sources)>=300:
                flush()
        except (ValueError,KeyError,TypeError) as exc:
            rejected+=1
            insert(db,scope,'import_rejects',{'row_number':number,'reason':str(exc),'public_fields':{k:v for k,v in row.items() if k in PUBLIC_FIELDS}},name=f'Row {number}',parent_id=job.id)
    flush()
    for zone,(code,capacity) in zones.items():
        zcls = TABLES['zones']
        z = db.scalar(select(zcls).where(zcls.world_id==scope.world.id,zcls.zone_code==zone))
        if not z:
            z=insert(db,scope,'zones',{'source_zone_code':code,'bed_capacity':capacity,'protected':zone=='ICU'},name=zone,zone_code=zone,idempotency_key='zone:'+zone)
            insert(db,scope,'zone_capacities',{'bed_capacity':capacity},parent_id=z.id,zone_code=zone,name=zone)
    if latest:
        scope.world.as_of=latest
        scope.world.initial_as_of=latest
        scope.world.version+=1
    if config:
        scope.world.config={k:v for k,v in config.items() if k in CONFIG_FIELDS}
    job.status='completed' if not rejected else 'completed_with_rejects'
    job.data={**job.data,'accepted':accepted,'duplicates':duplicates,'rejected':rejected,'conflicts':conflicts,'source_rows':accepted+duplicates+rejected}
    db.flush()
    return serialize(job)

def import_starter(db,scope,root):
    root=Path(root)
    verify_bundle(root)
    stress=scope.world.code=='stress_v1'
    filename='stress_observations.csv' if stress else 'observations.csv'
    path=root/'data'/filename
    with path.open() as f:
        return import_rows(db,scope,csv.DictReader(f),scope.world.code,hashlib.sha256(path.read_bytes()).hexdigest(),
                           json.loads((root/'data'/('stress_facility.json' if stress else 'facility.json')).read_text()))
