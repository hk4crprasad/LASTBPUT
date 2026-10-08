"""Explicit reads for static metadata when hosted Postgres auto-enables RLS."""
from alembic import op
revision = '0006'
down_revision = '0005'


def upgrade():
    # Supabase enables RLS on newly created public tables. These two static
    # tables have no tenant data; all operational/identity policies remain scoped.
    for table in ['metric_catalog', 'alembic_version']:
        op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY')
        op.execute(f'CREATE POLICY static_metadata_read ON {table} FOR SELECT TO greenops USING (true)')
        op.execute(f'GRANT SELECT ON {table} TO greenops')


def downgrade():
    for table in ['metric_catalog', 'alembic_version']:
        op.execute(f'DROP POLICY static_metadata_read ON {table}')
        op.execute(f'ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE {table} DISABLE ROW LEVEL SECURITY')
