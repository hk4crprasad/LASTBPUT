from contextlib import contextmanager
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.core.settings import settings

def database_engine(url, **kwargs):
    # Supavisor transaction pooling cannot retain prepared statement names.
    threshold = settings().database_prepare_threshold
    return create_engine(url, hide_parameters=True, pool_pre_ping=True,
                         connect_args={'prepare_threshold': None if threshold == 'disabled' else int(threshold),
                                       'connect_timeout': settings().database_connect_timeout_seconds}, **kwargs)

engine = database_engine(settings().database_url, pool_size=8, max_overflow=8)
Session = sessionmaker(engine, expire_on_commit=False)

def set_identity(db, user_id, org_id):
    db.execute(text("SELECT set_config('app.user_id', :user, true), set_config('app.org_id', :org, true), set_config('statement_timeout',:timeout,true)"),
               {'user': str(user_id), 'org': str(org_id), 'timeout': str(settings().database_statement_timeout_ms)})

@contextmanager
def transaction(user_id, org_id):
    with Session.begin() as db:
        set_identity(db, user_id, org_id)
        yield db
