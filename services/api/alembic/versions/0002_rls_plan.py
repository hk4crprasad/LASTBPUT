"""Cache server-derived grant set once per statement rather than one membership query per row."""
from alembic import op
from app.core.models import LEDGERS
revision='0002'
down_revision='0001'

def upgrade():
    op.execute('''CREATE FUNCTION authz_scope() RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER
      SET search_path=public,pg_temp AS $$
      SELECT coalesce(jsonb_object_agg(k,true),'{}'::jsonb) FROM (
        SELECT g.facility_id::text AS k FROM facility_grants g JOIN memberships m ON
        m.user_id=g.user_id AND m.organization_id=g.organization_id WHERE
        g.user_id::text=current_setting('app.user_id',true) AND g.organization_id::text=current_setting('app.org_id',true)
        UNION ALL
        SELECT g.facility_id::text||'/'||coalesce(g.zone_code,'*') FROM facility_grants g JOIN memberships m ON
        m.user_id=g.user_id AND m.organization_id=g.organization_id WHERE
        g.user_id::text=current_setting('app.user_id',true) AND g.organization_id::text=current_setting('app.org_id',true)
      ) grants $$''')
    op.execute('REVOKE ALL ON FUNCTION authz_scope() FROM PUBLIC')
    op.execute('GRANT EXECUTE ON FUNCTION authz_scope() TO greenops')
    for table in LEDGERS+['observations','worlds','facilities']:
        fac='id' if table=='facilities' else 'facility_id'
        pred=f"organization_id::text=(SELECT current_setting('app.org_id',true)) AND (SELECT authz_scope()) ? {fac}::text"
        if table not in {'worlds','facilities'}:
            pred+=f" AND ((SELECT authz_scope()) ? ({fac}::text||'/*') OR (SELECT authz_scope()) ? ({fac}::text||'/'||zone_code))"
        op.execute(f'DROP POLICY tenant_scope ON {table}')
        op.execute(f'CREATE POLICY tenant_scope ON {table} USING ({pred}) WITH CHECK ({pred})')
    op.execute('CREATE INDEX ix_grants_principal_org ON facility_grants(user_id,organization_id,facility_id,zone_code)')

def downgrade():
    for table in LEDGERS+['observations','worlds','facilities']:
        fac='id' if table=='facilities' else 'facility_id'
        zone='NULL::text' if table in {'worlds','facilities'} else 'zone_code'
        pred=f'permitted(organization_id,{fac},{zone})'
        op.execute(f'DROP POLICY tenant_scope ON {table}')
        op.execute(f'CREATE POLICY tenant_scope ON {table} USING ({pred}) WITH CHECK ({pred})')
    op.execute('DROP INDEX ix_grants_principal_org')
    op.execute('DROP FUNCTION authz_scope()')
