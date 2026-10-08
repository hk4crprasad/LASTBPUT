"""Explicit migration-only identity provisioning; never exposed by HTTP or agents."""
import argparse,json,os,secrets
from pathlib import Path
from datetime import datetime,timezone
from uuid import UUID,uuid4
from pydantic import BaseModel,ConfigDict,Field
from typing import Literal
from sqlalchemy import create_engine,select
from sqlalchemy.orm import Session
from argon2 import PasswordHasher
from app.core.models import Organization,Facility,World,User,Membership,Grant,Metric
class Strict(BaseModel):model_config=ConfigDict(extra='forbid')
class Person(Strict):
    email:str=Field(min_length=3,max_length=200)
    name:str=Field(min_length=1,max_length=200)
    role:Literal['organization_admin','hospital_admin','operations_supervisor','maintenance_technician','waste_officer','sustainability_officer','auditor']
    facility_codes:list[str]=Field(min_length=1)
    zones:list[str]=Field(default_factory=list)
class Site(Strict):
    code:str=Field(min_length=1,max_length=80)
    name:str=Field(min_length=1,max_length=200)
    world_code:str=Field(default='operations_v1',max_length=80)
    as_of:datetime=Field(default_factory=lambda:datetime.now(timezone.utc))
class Input(Strict):
    organization_name:str=Field(min_length=1,max_length=200)
    organization_id:UUID|None=None
    facilities:list[Site]=Field(min_length=1)
    users:list[Person]=Field(min_length=1)
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--input',required=True);parser.add_argument('--credentials-out',required=True);args=parser.parse_args()
    data=Input.model_validate_json(Path(args.input).read_text());url=os.environ.get('MIGRATION_DATABASE_URL')
    if not url:raise SystemExit('Dedicated MIGRATION_DATABASE_URL is required; application credentials cannot provision identities')
    output={}
    with Session(create_engine(url,hide_parameters=True),expire_on_commit=False) as db,db.begin():
        org=db.get(Organization,data.organization_id) if data.organization_id else db.scalar(select(Organization).where(Organization.name==data.organization_name))
        if not org:org=Organization(id=data.organization_id or uuid4(),name=data.organization_name);db.add(org);db.flush()
        sites={}
        for item in data.facilities:
            if item.as_of.tzinfo is None:raise ValueError('Provisioned world timestamp requires timezone')
            fac=db.scalar(select(Facility).where(Facility.organization_id==org.id,Facility.code==item.code))
            if not fac:fac=Facility(organization_id=org.id,code=item.code,name=item.name);db.add(fac);db.flush()
            sites[item.code]=fac
            if not db.scalar(select(World).where(World.facility_id==fac.id,World.code==item.world_code)):
                db.add(World(organization_id=org.id,facility_id=fac.id,code=item.world_code,name=item.world_code,as_of=item.as_of,initial_as_of=item.as_of,config={}))
        for item in data.users:
            user=db.scalar(select(User).where(User.email==item.email.lower()))
            if not user:
                password=secrets.token_urlsafe(24);user=User(email=item.email.lower(),name=item.name,password_hash=PasswordHasher().hash(password));db.add(user);db.flush();output[item.email]={'user_id':str(user.id),'password':password}
            membership=db.scalar(select(Membership).where(Membership.user_id==user.id,Membership.organization_id==org.id))
            if not membership:db.add(Membership(user_id=user.id,organization_id=org.id,role=item.role))
            elif membership.role!=item.role:raise ValueError('Existing role differs; perform an explicitly reviewed role change')
            for code in item.facility_codes:
                if code not in sites:raise ValueError('Grant refers to an unprovisioned facility')
                for zone in item.zones or [None]:
                    q=select(Grant).where(Grant.user_id==user.id,Grant.facility_id==sites[code].id,Grant.zone_code==zone)
                    if not db.scalar(q):db.add(Grant(user_id=user.id,organization_id=org.id,facility_id=sites[code].id,zone_code=zone))
        from app.bootstrap import uid
        metrics=[('energy.interval_kwh','energy','kWh','interval','sum',None),('water.interval_l','water','L','interval','sum',None),('waste.generated_kg','waste','kg','interval','sum',None),('waste.stock_kg','waste','kg','state','last',None),('waste.fill_pct','waste','%','state','avg',100),('waste.age_hours','waste','h','state','last',None),('waste.pickup_recorded','waste','flag','state','last',1)]
        for code,domain,unit,sem,agg,maximum in metrics:
            if not db.get(Metric,code):db.add(Metric(code=code,domain=domain,unit=unit,semantics=sem,aggregation=agg,maximum=maximum))
    dest=Path(args.credentials_out);dest.parent.mkdir(parents=True,exist_ok=True)
    existing=json.loads(dest.read_text()) if dest.exists() else {};dest.write_text(json.dumps({**existing,**output},indent=2));dest.chmod(0o600)
    print(json.dumps({'status':'provisioned','organization_id':str(org.id),'new_users':len(output),'credential_file':str(dest)}))
if __name__=='__main__':main()
