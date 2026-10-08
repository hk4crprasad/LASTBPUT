"""Migration-only identity bootstrap. Never imported by the API or worker."""
import json
import os
import secrets
from pathlib import Path
from datetime import datetime, timezone
from uuid import UUID, uuid5, NAMESPACE_URL
from argon2 import PasswordHasher
from sqlalchemy import select
from app.core.db import database_engine
from sqlalchemy.orm import Session
from app.core.models import Organization, User, Membership, Facility, Grant, World, Metric

ROLES = ['organization_admin','hospital_admin','operations_supervisor','maintenance_technician','waste_officer','sustainability_officer','auditor']
def uid(name):
    return uuid5(NAMESPACE_URL, 'greenops-demo:'+name)

def main():
    import sys
    resetting="--reset-demo" in sys.argv
    if resetting and os.getenv("APP_MODE","demo")!="demo":raise SystemExit("Reset is restricted to APP_MODE=demo")
    if os.getenv('APP_MODE','demo') != 'demo':
        print('Production: demo bootstrap disabled')
        return
    dest = Path(os.environ.get('DEMO_CREDENTIALS_PATH','/app/shared/demo-credentials.json'))
    saved = json.loads(dest.read_text()) if dest.exists() else {}
    with Session(database_engine(os.environ['MIGRATION_DATABASE_URL'])) as db, db.begin():
        if resetting:
            from sqlalchemy import text
            db.execute(text('TRUNCATE organizations, users, metric_catalog CASCADE'))
            saved={}
        org = uid('org')
        if not db.get(Organization,org):
            db.add(Organization(id=org,name='Riverbend Hospital Demonstration'))
            db.flush()
        for code in ['DEMO_HOSPITAL','SECOND_FACILITY']:
            fac = uid(code)
            if not db.get(Facility,fac):
                db.add(Facility(id=fac,organization_id=org,code=code,name='Riverbend Hospital (fictional)' if code=='DEMO_HOSPITAL' else 'North Annex (isolation fixture)'))
                db.flush()
            for world in ['base_v1','stress_v1','extended_v1'] if code=='DEMO_HOSPITAL' else ['isolated_v1']:
                wid = uid(code+world)
                if not db.get(World,wid):
                    t = datetime(2025,1,1,tzinfo=timezone.utc)
                    db.add(World(id=wid,organization_id=org,facility_id=fac,code=world,name=world.replace('_',' ').title(),as_of=t,initial_as_of=t,config={}))
        db.flush()
        for role in ROLES + ['monitor_service']:
            email = role+'@demo.greenops.local'
            user_id = uid(email)
            if not db.get(User,user_id):
                previous = saved.get(role, {})
                if previous and (previous.get('email') != email or previous.get('user_id') != str(user_id)):
                    raise ValueError('Demo credential identity mismatch')
                password = previous.get('password') or secrets.token_urlsafe(18)
                db.add(User(id=user_id,email=email,name=role.replace('_',' ').title(),password_hash=PasswordHasher().hash(password),service_principal=role=='monitor_service'))
                db.flush()
                db.add(Membership(user_id=user_id,organization_id=org,role=role if role!='monitor_service' else 'operations_supervisor'))
                db.add(Grant(user_id=user_id,organization_id=org,facility_id=uid('DEMO_HOSPITAL'),zone_code='WARD_A' if role=='maintenance_technician' else None))
                if role!='monitor_service':
                    saved[role]={'email':email,'password':password,'user_id':str(user_id)}
        metrics = [('energy.interval_kwh','energy','kWh','interval','sum',None),('water.interval_l','water','L','interval','sum',None),
                   ('waste.generated_kg','waste','kg','interval','sum',None),('waste.stock_kg','waste','kg','state','last',None),
                   ('waste.fill_pct','waste','%','state','avg',100),('waste.age_hours','waste','h','state','last',None),
                   ('waste.pickup_recorded','waste','flag','state','last',1)]
        for code,domain,unit,sem,agg,maximum in metrics:
            if not db.get(Metric,code):
                db.add(Metric(code=code,domain=domain,unit=unit,semantics=sem,aggregation=agg,maximum=maximum))
        # A populated second tenant makes cross-tenant denial an observable integration check.
        from app.core.models import TABLES
        other_org,other_fac,other_world=uid('isolation-org'),uid('isolation-fac'),uid('isolation-world')
        if not db.get(Organization,other_org):
            db.add(Organization(id=other_org,name='Separate synthetic isolation tenant'));db.flush()
            db.add(Facility(id=other_fac,organization_id=other_org,code='ISOLATION_HOSPITAL',name='Isolation fixture'));db.flush()
            t=datetime(2025,1,1,tzinfo=timezone.utc)
            db.add(World(id=other_world,organization_id=other_org,facility_id=other_fac,code='tenant_isolation_v1',name='Tenant isolation',as_of=t,initial_as_of=t,config={}));db.flush()
            db.add(TABLES['assets'](id=uid('isolation-asset'),organization_id=other_org,facility_id=other_fac,world_id=other_world,name='Other tenant pump',event_at=t,data={'kind':'pump','mode':'operational','rated_kw':5,'critical':False}))
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(saved,indent=2))
    dest.chmod(0o644) # mounted shared directory is local-only; passwords intentionally needed by demo runner
    print('Demo credentials generated at '+str(dest)+'; preserve this file for idempotent setup')

if __name__=='__main__':
    main()
