from contextlib import contextmanager
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.core.settings import settings

engine = create_engine(settings().database_url, hide_parameters=True, pool_pre_ping=True, pool_size=8, max_overflow=8)
Session = sessionmaker(engine, expire_on_commit=False)

def set_identity(db, user_id, org_id):
    db.execute(text("SELECT set_config('app.user_id', :user, true), set_config('app.org_id', :org, true), set_config('statement_timeout','3000',true)"),
               {'user': str(user_id), 'org': str(org_id)})

@contextmanager
def transaction(user_id, org_id):
    with Session.begin() as db:
        set_identity(db, user_id, org_id)
        yield db
