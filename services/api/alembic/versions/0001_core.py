"""Tenant core, operational ledgers and forced row security."""
from alembic import op
from app.core.models import Base, LEDGERS
revision = '0001'
down_revision = None

def upgrade():
    bind = op.get_bind()
    Base.metadata.create_all(bind)
    op.execute('REVOKE ALL ON SCHEMA public FROM PUBLIC')
    op.execute('GRANT USAGE ON SCHEMA public TO greenops')
    op.execute('GRANT SELECT ON metric_catalog TO greenops')
    op.execute('''CREATE FUNCTION permitted(org uuid, facility uuid, zone text) RETURNS boolean
      LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
      SELECT org::text = current_setting('app.org_id', true) AND EXISTS (
        SELECT 1 FROM memberships m WHERE m.organization_id=org
        AND m.user_id::text=current_setting('app.user_id',true)
        AND (facility IS NULL OR EXISTS (SELECT 1 FROM facility_grants g
          WHERE g.organization_id=org AND g.user_id=m.user_id AND g.facility_id=facility
          AND (g.zone_code IS NULL OR g.zone_code=zone)))) $$''')
    op.execute('REVOKE ALL ON FUNCTION permitted(uuid,uuid,text) FROM PUBLIC')
    op.execute('GRANT EXECUTE ON FUNCTION permitted(uuid,uuid,text) TO greenops')
    scoped = LEDGERS + ['observations', 'worlds', 'facilities', 'organizations']
    for table in scoped:
        org = 'id' if table == 'organizations' else 'organization_id'
        facility = 'id' if table == 'facilities' else ('NULL::uuid' if table == 'organizations' else 'facility_id')
        zone = 'NULL::text' if table in ('worlds', 'facilities', 'organizations') else 'zone_code'
        pred = f'permitted({org}, {facility}, {zone})'
        op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY')
        op.execute(f'CREATE POLICY tenant_scope ON {table} USING ({pred}) WITH CHECK ({pred})')
        op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO greenops')
    for table in ['users', 'memberships', 'facility_grants', 'sessions']:
        pred = "id::text=current_setting('app.user_id',true)" if table == 'users' else "user_id::text=current_setting('app.user_id',true)"
        op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY')
        op.execute(f'CREATE POLICY own_identity ON {table} USING ({pred}) WITH CHECK ({pred})')
        op.execute(f'GRANT SELECT ON {table} TO greenops')
    op.execute('GRANT INSERT, DELETE ON sessions TO greenops')
    op.execute('''CREATE FUNCTION auth_lookup(mail text) RETURNS TABLE(id uuid,email text,name text,password_hash text,organization_id uuid,role text)
      LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
      SELECT u.id,u.email,u.name,u.password_hash,m.organization_id,m.role FROM users u
      JOIN memberships m ON m.user_id=u.id WHERE u.email=mail AND u.active AND NOT u.service_principal LIMIT 1 $$''')
    op.execute('''CREATE FUNCTION session_lookup(token text) RETURNS TABLE(user_id uuid,organization_id uuid,role text,email text,name text,csrf_hash text)
      LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
      SELECT s.user_id,s.organization_id,m.role,u.email,u.name,s.csrf_hash FROM sessions s
      JOIN users u ON u.id=s.user_id JOIN memberships m ON m.user_id=s.user_id AND m.organization_id=s.organization_id
      WHERE s.token_hash=token AND s.expires_at > now() AND u.active $$''')
    op.execute('''CREATE FUNCTION scoped_owners(org uuid, fac uuid) RETURNS TABLE(id uuid,name text,role text,zone_code text)
      LANGUAGE sql STABLE SECURITY DEFINER SET search_path=public,pg_temp AS $$
      SELECT u.id,u.name,m.role,g.zone_code FROM users u JOIN memberships m ON m.user_id=u.id
      JOIN facility_grants g ON g.user_id=u.id AND g.organization_id=m.organization_id
      WHERE m.organization_id=org AND g.facility_id=fac AND u.active
      AND permitted(org,fac,g.zone_code) $$''')
    for signature in ['auth_lookup(text)', 'session_lookup(text)', 'scoped_owners(uuid,uuid)']:
        op.execute(f'REVOKE ALL ON FUNCTION {signature} FROM PUBLIC')
        op.execute(f'GRANT EXECUTE ON FUNCTION {signature} TO greenops')
    op.execute('''CREATE INDEX ix_documents_search ON document_chunks USING gin(to_tsvector('english',data->>'body'))''')
    op.execute('CREATE INDEX ix_actions_owner_due ON actions(world_id,owner_id,status,due_at)')
    op.execute('CREATE INDEX ix_forecasts_target ON forecast_points(world_id,event_at,zone_code)')

def downgrade():
    for signature in ['scoped_owners(uuid,uuid)', 'auth_lookup(text)', 'session_lookup(text)']:
        op.execute(f'DROP FUNCTION IF EXISTS {signature}')
    Base.metadata.drop_all(op.get_bind())
    op.execute('DROP FUNCTION IF EXISTS permitted(uuid,uuid,text)')
