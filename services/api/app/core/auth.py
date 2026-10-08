import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import HTTPException, Request
from sqlalchemy import select, text
from app.core.db import Session, set_identity
from app.core.models import Grant, LoginSession, World, User, now

ADMIN = {'organization_admin','hospital_admin'}
WRITE = {'facility': ADMIN, 'policy': ADMIN, 'models': ADMIN, 'imports': ADMIN,
         'waste': ADMIN|{'operations_supervisor','waste_officer'},
         'assets': ADMIN|{'operations_supervisor','maintenance_technician'},
         'sustainability': ADMIN|{'sustainability_officer'},
         'actions': ADMIN|{'operations_supervisor','waste_officer','maintenance_technician','sustainability_officer'},
         'safety': ADMIN|{'operations_supervisor'}, 'parking': ADMIN|{'operations_supervisor'},
         'environment': ADMIN|{'operations_supervisor'}, 'simulation': ADMIN|{'operations_supervisor','sustainability_officer','waste_officer'},
         'reports': ADMIN|{'operations_supervisor','sustainability_officer','auditor'},
         'chat': set(WRITE_ROLE for WRITE_ROLE in ['organization_admin','hospital_admin','operations_supervisor','maintenance_technician','waste_officer','sustainability_officer','auditor'])}

def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()

@dataclass
class Principal:
    user_id: UUID
    organization_id: UUID
    role: str
    email: str = ''
    name: str = ''

@dataclass
class Scope:
    principal: Principal
    world: World
    zone_codes: list[str] | None
    @property
    def keys(self):
        return {'organization_id':self.principal.organization_id,'facility_id':self.world.facility_id,'world_id':self.world.id}
    def zone(self, code):
        if code is None and self.zone_codes is not None:
            raise HTTPException(403,'A zone grant is required for this record')
        if code is not None and self.zone_codes is not None and code not in self.zone_codes:
            raise HTTPException(403,'Zone outside your grant')
    def require(self, domain):
        if self.principal.role not in WRITE.get(domain,ADMIN):
            raise HTTPException(403,f'Role cannot write {domain}')

def authenticate(request: Request, db):
    token = request.cookies.get('greenops_session','')
    row = db.execute(text('SELECT * FROM session_lookup(:token)'),{'token':digest(token)}).mappings().first()
    if not row:
        raise HTTPException(401,'Login required')
    if request.method not in {'GET','HEAD','OPTIONS'}:
        if not hmac.compare_digest(row['csrf_hash'],digest(request.headers.get('x-csrf-token',''))):
            raise HTTPException(403,'CSRF token missing or invalid')
        from app.core.settings import settings
        origin = request.headers.get('origin')
        if origin and origin not in settings().cors_origins.split(','):
            raise HTTPException(403,'Origin not allowed')
    p = Principal(row['user_id'],row['organization_id'],row['role'],row['email'],row['name'])
    set_identity(db,p.user_id,p.organization_id)
    return p

def resolve_scope(db,p,world_id):
    try:
        wid = UUID(str(world_id))
    except ValueError:
        raise HTTPException(422,'world_id must be UUID')
    world = db.get(World,wid)
    if not world:
        raise HTTPException(404,'World unavailable in your scope')
    grants = db.scalars(select(Grant).where(Grant.facility_id==world.facility_id,Grant.user_id==p.user_id)).all()
    if not grants:
        raise HTTPException(403,'Facility grant required')
    zones = None if any(g.zone_code is None for g in grants) else [g.zone_code for g in grants]
    return Scope(p,world,zones)

def request_db(request: Request):
    with Session.begin() as db:
        p = authenticate(request,db)
        yield db,p

def login(db,email,password):
    row = db.execute(text('SELECT * FROM auth_lookup(:email)'),{'email':email.lower().strip()}).mappings().first()
    # Equal-cost hash path prevents obvious timing enumeration.
    dummy = '$argon2id$v=19$m=65536,t=3,p=4$MTIzNDU2Nzg5MDEyMzQ1Ng$+eX4REqU8bbBLyn1wK16xLdRmPXCYDOqIqe0qWCNOu0'
    try:
        valid = PasswordHasher().verify(row['password_hash'] if row else dummy,password)
    except (VerificationError, ValueError):
        valid = False
    if not row or not valid:
        raise HTTPException(401,'Invalid credentials')
    p = Principal(row['id'],row['organization_id'],row['role'],row['email'],row['name'])
    set_identity(db,p.user_id,p.organization_id)
    token,csrf = secrets.token_urlsafe(40),secrets.token_urlsafe(32)
    db.add(LoginSession(token_hash=digest(token),csrf_hash=digest(csrf),user_id=p.user_id,
                        organization_id=p.organization_id,expires_at=now()+timedelta(hours=8)))
    return p,token,csrf
