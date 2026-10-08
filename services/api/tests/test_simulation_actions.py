from datetime import datetime,timezone,timedelta
from uuid import UUID
from pathlib import Path
import json
import pytest
from fastapi import HTTPException
from app.simulation.engine import Baseline,Tank,Scenario,Intervention,run_engine,reserve_deadline,waste_deadline
from app.domains.actions import create,transition,ActionInput,Transition
from app.core.auth import Principal,resolve_scope
from app.core.db import transaction
from app.core.settings import settings
from test_data_security import base_scope,principal


def test_five_numeric_fixtures_and_unknown_age():
    assert reserve_deadline(30000,3000)['hours_to_depletion']==10
    assert reserve_deadline(30000,3000,excess_lph=500)['hours_to_depletion']==pytest.approx(8.5714285714)
    b=Baseline(as_of=datetime.now(timezone.utc),snapshot_version=1,demand_source='fixture',tanks=[],essential_load_kw=60,battery_deliverable_kwh=120)
    assert run_engine(b,Scenario(name='battery'))['central']['battery_runtime_hours']==2
    assert waste_deadline(70,8,5)['service_within_hours']==1.875
    assert waste_deadline(30,2,23)['service_within_hours']==1
    assert waste_deadline(30,2,None)['age_status']=='unknown'
    assert waste_deadline(30,2,None)['hours_to_age_limit'] is None

def test_mass_balance_priority_fire_and_unmet():
    b=Baseline(as_of=datetime(2025,1,1,tzinfo=timezone.utc),snapshot_version=1,demand_source='fixture',
       tanks=[Tank(name='potable',kind='potable',capacity_l=30000,reserve_l=30000,inflow_lph=0,essential_lph=3000,nonessential_lph=500),
              Tank(name='fire',kind='fire',capacity_l=10000,reserve_l=10000,inflow_lph=0,essential_lph=0)],
       battery_deliverable_kwh=120,essential_load_kw=60,pump_load_kw=0,nonessential_load_kw=0)
    scenario=Scenario(name='outage',horizon_hours=24,events=[Intervention(kind='grid_outage',duration_hours=24)])
    first=run_engine(b,scenario);second=run_engine(b,scenario)
    assert first==second
    r=first['central']['totals']
    assert r['initial_water_l']+r['water_inflow_l']-r['served_water_l']-r['spilled_water_l']==pytest.approx(r['remaining_water_l'])
    assert r['battery_energy_kwh']==120
    assert r['unmet_essential_energy_kwh']==pytest.approx(60*22)
    assert r['unmet_essential_water_l']>0
    assert first['central']['points'][-1]['tanks']['fire']==10000
    assert r['final_parking_queue']>=0

def test_action_idempotency_version_roles_and_evidence(base_scope):
    db,scope=base_scope
    creds=json.loads(Path(settings().demo_credentials_path).read_text())
    owner=UUID(creds['operations_supervisor']['user_id'])
    body=ActionInput(name='Inspect pump fixture',category='maintenance',zone_code='WARD_A',owner_id=owner,due_at=scope.world.as_of+timedelta(days=1))
    row=create(db,scope,body,'test-state-'+str(__import__('uuid').uuid4()))
    same=create(db,scope,body,row['idempotency_key'])
    assert same['id']==row['id']
    with pytest.raises(HTTPException):transition(db,scope,row['id'],Transition(state='closed',expected_version=1,reason='Invalid shortcut',evidence='note'))
    for state in ['acknowledged','in_progress','resolved']:
        row=transition(db,scope,row['id'],Transition(state=state,expected_version=row['version'],reason='Test state progression'))
    with pytest.raises(HTTPException):transition(db,scope,row['id'],Transition(state='verified',expected_version=row['version'],reason='Missing evidence'))
    with pytest.raises(HTTPException):transition(db,scope,row['id'],Transition(state='verified',expected_version=1,reason='Stale update',evidence='Readings stable'))
    reviewer=Principal(owner,scope.principal.organization_id,'operations_supervisor')
    from app.core.db import set_identity
    set_identity(db,reviewer.user_id,reviewer.organization_id)
    review_scope=resolve_scope(db,reviewer,scope.world.id)
    row=transition(db,review_scope,row['id'],Transition(state='verified',expected_version=row['version'],reason='Independent check',evidence='Inspection record: pump stable, synthetic fixture'))
    row=transition(db,review_scope,row['id'],Transition(state='closed',expected_version=row['version'],reason='Complete review',evidence='Closure reviewed'))
    assert row['status']=='closed'
