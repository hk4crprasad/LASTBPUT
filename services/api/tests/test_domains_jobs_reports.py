import json
from datetime import timedelta
from pathlib import Path
from uuid import UUID,uuid4
import pytest
from fastapi import HTTPException
from sqlalchemy import select,func,text
from app.core.db import transaction,Session
from app.core.auth import resolve_scope,Principal
from app.core.models import World,TABLES,Observation
from app.cli import demo_principal
from app.core.records import get,query,serialize
from app.core.settings import settings
from app.core.storage import read
from app.domains.contracts import RecordInput
from app.domains.crud import create_record,update_record
from app.domains.reports import create_report
from app.domains.state import waste_state,parking_safety
from app.jobs.service import enqueue
from app.jobs.tasks import execute
from app.simulation.engine import Scenario

@pytest.fixture
def extended():
    p=demo_principal()
    with transaction(p.user_id,p.organization_id) as db:
        w=db.scalar(select(World).where(World.code=='extended_v1'))
        yield db,resolve_scope(db,p,w.id)

def test_extended_full_domain_counts_and_balances(extended):
    db,s=extended
    assert db.scalar(select(func.count()).select_from(TABLES['source_events']).where(TABLES['source_events'].world_id==s.world.id))==25920
    for table in ['buildings','floors','assets','tanks','waste_batches','pickups','handover_evidence','environment_readings','parking_events','safety_incidents','tariff_versions']:
        assert query(db,s,table,1)
    ledger=waste_state(db,s)
    stocks=sum(c['stock_kg'] for c in ledger['categories'])
    move=TABLES['waste_movements']
    assert stocks==pytest.approx(float(db.scalar(select(func.sum(move.value)).where(move.world_id==s.world.id,move.event_at<=s.world.as_of))))
    state=TABLES['tank_states']
    for tank in query(db,s,'tanks'):
        previous=tank.data['initial_reserve_l']
        for row in db.scalars(select(state).where(state.world_id==s.world.id,state.parent_id==tank.id).order_by(state.event_at)):
            data=row.data
            assert previous+data['inflow_lph']-data['served_l']-data['spill_l']==pytest.approx(data['reserve_l'])
            previous=data['reserve_l']
    parked=40;queue=0
    for row in db.scalars(select(TABLES['parking_snapshots']).where(TABLES['parking_snapshots'].world_id==s.world.id).order_by(TABLES['parking_snapshots'].event_at)):
        d=row.data
        assert d['occupancy']<=d['capacity']
        assert parked+queue+d['arrivals']-d['exits']==d['occupancy']+d['queue']
        parked,queue=d['occupancy'],d['queue']

def test_persisted_crud_pickup_and_work_orders(extended):
    db,s=extended
    asset=create_record(db,s,'assets',RecordInput(name='CRUD pump',zone_code='WARD_A',data={'kind':'pump','mode':'operational','critical':True,'rated_kw':5}))
    body=RecordInput(name='CRUD inspection',zone_code='WARD_A',status='open',owner_id=s.principal.user_id,data={'asset_id':asset['id'],'inspection_type':'inspection'})
    order=create_record(db,s,'maintenance_orders',body)
    revised=body.model_copy(update={'name':'Revised inspection','expected_version':order['version'],'status':'in_progress'})
    saved=update_record(db,s,'maintenance_orders',order['id'],revised)
    assert saved['version']==2 and saved['status']=='in_progress'
    bin=next(b for b in query(db,s,'waste_bins') if b.zone_code=='WARD_A' and b.data['category']=='red')
    batch=create_record(db,s,'waste_batches',RecordInput(name='Synthetic CRUD batch',zone_code='WARD_A',data={'category':'red','bin_id':str(bin.id),'generated_kg':1.25,'generated_at':s.world.as_of.isoformat()}))
    pickup=RecordInput(name='CRUD pickup',zone_code='WARD_A',data={'batch_ids':[batch['id']],'vehicle_reference':'TEST-VEH','handover_reference':'TEST-HO','collected_at':s.world.as_of.isoformat(),'destination':'Fictional treatment'})
    result=create_record(db,s,'pickups',pickup,'pickup-test-'+batch['id'])
    assert result['value']==1.25
    assert get(db,s,'waste_batches',batch['id']).status=='collected'
    with pytest.raises(HTTPException):create_record(db,s,'pickups',pickup)

def test_deterministic_report_artifacts_and_auth_scope(extended):
    db,s=extended
    report=create_report(db,s,{'hours':24},'test-report-'+str(uuid4()))
    for key in ['csv_file_id','html_file_id','pdf_file_id']:
        file,body=read(db,s,report['data'][key]);assert body
    file,csv=read(db,s,report['data']['csv_file_id'])
    assert b'energy.interval_kwh' in csv and b'synthetic' in csv
    assert report['data']['facts']['sustainability']['emission_factor']['data']['assumption'] is True

def test_durable_job_duplicate_execution():
    p=demo_principal()
    with transaction(p.user_id,p.organization_id) as db:
        w=db.scalar(select(World).where(World.code=='extended_v1'));s=resolve_scope(db,p,w.id)
        job=enqueue(db,s,'simulation',{'scenario':Scenario(name='Durable fixture',horizon_hours=2).model_dump(mode='json')},'test-job-'+str(uuid4()))
    first=execute.run(job['job_id']);second=execute.run(job['job_id'])
    assert first['status']=='completed' and second['status']=='already_finished_or_unavailable'
    with transaction(p.user_id,p.organization_id) as db:
        s=resolve_scope(db,p,w.id);count=db.scalar(select(func.count()).select_from(TABLES['simulation_runs']).where(TABLES['simulation_runs'].idempotency_key=='job:'+job['job_id']))
        assert count==1

def test_auditor_write_rejected_at_rls():
    p=demo_principal();creds=json.loads(Path(settings().demo_credentials_path).read_text())['auditor']
    with transaction(UUID(creds['user_id']),p.organization_id) as db:
        w=db.scalar(select(World).where(World.code=='extended_v1'))
        result=db.execute(text("UPDATE assets SET name='unauthorized' WHERE world_id=:world"),{'world':w.id})
        assert result.rowcount==0
        assert not db.scalar(select(TABLES['assets']).where(TABLES['assets'].name=='unauthorized'))
