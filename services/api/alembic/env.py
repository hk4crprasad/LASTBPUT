import os
from alembic import context
from sqlalchemy import create_engine
from app.core.models import Base
url = os.environ['MIGRATION_DATABASE_URL']
with create_engine(url).connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()
