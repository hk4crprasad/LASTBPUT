import csv
import json
from pathlib import Path
from uuid import uuid4,UUID
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select,text,func
from app.main import app
from app.core.models import Observation,TABLES,World,Grant
from app.core.db import transaction,Session
from app.core.settings import settings
from app.cli import demo_principal
from app.core.auth import Principal,resolve_scope
from app.domains.importer import import_starter,verify_bundle,normalize

@pytest.fixture
def principal():
    return demo_principal()
@pytest.fixture
def base_scope(principal):
    with transaction(principal.user_id,principal.organization_id) as db:
        world=db.scalar(select(World).where(World.code=='base_v1'))
        yield db,resolve_scope(db,principal,world.id)

def test_exact_counts_and_missing_water(base_scope):
    db,scope=base_scope
    for code,count in [('base_v1',17280),('stress_v1',8640)]:
        world=db.scalar(select(World).where(World.code==code))
        assert db.scalar(select(func.count()).select_from(TABLES['source_events']).where(TABLES['source_events'].world_id==world.id))==count
        assert db.scalar(select(func.count()).select_from(Observation).where(Observation.world_id==world.id,Observation.metric=='water.interval_l',Observation.value.is_(None)))>0
        assert db.scalar(select(func.count()).select_from(Observation).where(Observation.world_id==world.id,Observation.metric=='energy.interval_kwh',Observation.quality!='ok'))==0
    assert db.scalar(select(func.count()).select_from(Observation).where(Observation.world_id==scope.world.id))==17280*7

def test_repeat_import_and_manifest(base_scope):
    db,scope=base_scope
    r=import_starter(db,scope,settings().starter_path)
    assert r['data']['accepted']==0 and r['data']['duplicates']==17280
    verify_bundle(settings().starter_path)
    root=Path(settings().starter_path)
    for file in root.rglob('*'):
        assert 'private_label' not in file.name
    for name in ['facility.json','stress_facility.json']:
        assert 'events' not in json.loads((root/'data'/name).read_text())

def test_rls_role_identity_and_pool_reset(principal):
    with transaction(principal.user_id,principal.organization_id) as db:
        role=db.execute(text('SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user')).one()
        assert role==(False,False)
        assert db.scalar(select(func.count()).select_from(Observation))>0
        assert not db.scalar(select(World).where(World.code=='isolated_v1'))
        # Client tenant substitution cannot grant membership.
        db.execute(text("SELECT set_config('app.org_id',:other,true)"),{'other':str(uuid4())})
        assert db.scalar(select(func.count()).select_from(Observation))==0
    with Session.begin() as db:
        assert db.scalar(select(func.count()).select_from(Observation))==0
        flags=db.execute(text("SELECT bool_and(relrowsecurity AND relforcerowsecurity) FROM pg_class WHERE relname=ANY(:names)"),{'names':['observations','actions','worlds','jobs','documents']}).scalar()
        assert flags is True

def test_technician_zone_isolation():
    creds=json.loads(Path(settings().demo_credentials_path).read_text())['maintenance_technician']
    admin=demo_principal()
    p=Principal(UUID(creds['user_id']),admin.organization_id,'maintenance_technician')
    with transaction(p.user_id,p.organization_id) as db:
        assert set(db.scalars(select(Observation.zone_code).distinct()))=={'WARD_A'}
        scope=resolve_scope(db,p,db.scalar(select(World).where(World.code=='base_v1')).id)
        with pytest.raises(Exception):scope.zone('ICU')

def test_auth_cookie_csrf_and_auditor():
    creds=json.loads(Path(settings().demo_credentials_path).read_text())['auditor']
    client=TestClient(app)
    assert client.get('/api/v1/worlds').status_code==401
    r=client.post('/api/v1/auth/login',json={'email':creds['email'],'password':creds['password']})
    assert r.status_code==200
    assert 'HttpOnly' in r.headers['set-cookie']
    world=client.get('/api/v1/worlds').json()['items'][0]['id']
    assert client.post('/api/v1/demo/clock',params={'world_id':world},json={'operation':'advance'}).status_code==403
    assert client.post('/api/v1/demo/clock',params={'world_id':world},headers={'X-CSRF-Token':r.json()['csrf_token']},json={'operation':'advance'}).status_code==403

def test_invalid_capacity_quarantine(base_scope):
    from app.domains.importer import import_rows
    db,scope=base_scope
    row=next(csv.DictReader((Path(settings().starter_path)/'data/observations.csv').open()))
    row['occupied_beds']='999'
    r=import_rows(db,scope,[row],'reject-test','reject-checksum')
    assert r['data']['rejected']==1
    assert db.scalar(select(func.count()).select_from(TABLES['import_rejects']))>=1
