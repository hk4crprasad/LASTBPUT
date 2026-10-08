"""Role/assigned-write defense beneath the shared domain service permission checks."""
from alembic import op
from app.core.models import LEDGERS
revision='0004'
down_revision='0003'

ADMINS=['organization_admin','hospital_admin']
GROUPS={
 'facility':ADMINS,'assets':ADMINS+['operations_supervisor','maintenance_technician'],
 'waste':ADMINS+['operations_supervisor','waste_officer'], 'sustainability':ADMINS+['sustainability_officer'],
 'operations':ADMINS+['operations_supervisor'],
 'actions':ADMINS+['operations_supervisor','maintenance_technician','waste_officer','sustainability_officer'],
 'simulation':ADMINS+['operations_supervisor','waste_officer','sustainability_officer'],
 'reports':ADMINS+['operations_supervisor','auditor','sustainability_officer'],
 'platform':ADMINS+['operations_supervisor','maintenance_technician','waste_officer','sustainability_officer','auditor']}
CATEGORY={t:'platform' for t in LEDGERS}
for t in ['buildings','floors','zones','zone_capacities','operating_schedules','tanks','policy_versions','documents','document_chunks','agent_policies','dataset_versions','source_events','import_jobs','import_rejects','operational_snapshots','quality_events','aggregate_snapshots','model_versions','training_runs','evaluation_results','forecast_runs','forecast_points']:
    CATEGORY[t]='facility'
for t in ['assets','asset_dependencies','asset_telemetry','maintenance_orders']:CATEGORY[t]='assets'
for t in ['waste_categories','waste_bins','waste_batches','waste_movements','pickups','handover_evidence']:CATEGORY[t]='waste'
for t in ['tariff_versions','emission_factor_versions']:CATEGORY[t]='sustainability'
for t in ['tank_states','power_sources','power_states','environment_readings','parking_areas','parking_events','parking_snapshots','safety_incidents','detector_runs','alerts','alert_evidence']:CATEGORY[t]='operations'
for t in ['actions','action_events','action_evidence','action_proposals']:CATEGORY[t]='actions'
for t in ['scenario_definitions','simulation_runs','simulation_points','simulation_comparisons']:CATEGORY[t]='simulation'
CATEGORY['report_runs']='reports'
CATEGORY['observations']='facility'

def upgrade():
    op.execute('''CREATE FUNCTION effective_role() RETURNS text LANGUAGE sql STABLE SECURITY DEFINER SET search_path=public,pg_temp AS $$
      SELECT role FROM memberships WHERE user_id::text=current_setting('app.user_id',true) AND organization_id::text=current_setting('app.org_id',true) LIMIT 1 $$''')
    op.execute('REVOKE ALL ON FUNCTION effective_role() FROM PUBLIC')
    op.execute('GRANT EXECUTE ON FUNCTION effective_role() TO greenops')
    for table in LEDGERS+['observations']:
        roles=','.join("'"+r+"'" for r in GROUPS[CATEGORY[table]])
        scope="organization_id::text=(SELECT current_setting('app.org_id',true)) AND (SELECT authz_scope()) ? facility_id::text AND ((SELECT authz_scope()) ? (facility_id::text||'/*') OR (SELECT authz_scope()) ? (facility_id::text||'/'||zone_code))"
        write=f'{scope} AND (SELECT effective_role()) IN ({roles})'
        op.execute(f'DROP POLICY tenant_scope ON {table}')
        op.execute(f'CREATE POLICY tenant_read ON {table} FOR SELECT USING ({scope})')
        op.execute(f'CREATE POLICY tenant_insert ON {table} FOR INSERT WITH CHECK ({write})')
        owner=" AND ((SELECT effective_role())<>'maintenance_technician' OR owner_id::text=(SELECT current_setting('app.user_id',true)))" if table in {'actions','maintenance_orders'} else ''
        op.execute(f'CREATE POLICY tenant_update ON {table} FOR UPDATE USING ({write}{owner}) WITH CHECK ({write}{owner})')
        op.execute(f'CREATE POLICY tenant_delete ON {table} FOR DELETE USING ({write}{owner})')
    # Run-level privacy also applies to exports and generic ledger reads.
    for table in ['conversations','messages','agent_runs','tool_calls','ai_usage','jobs']:
        op.execute(f"CREATE POLICY run_owner ON {table} AS RESTRICTIVE USING (owner_id::text=(SELECT current_setting('app.user_id',true)) OR (SELECT effective_role()) IN ('hospital_admin','organization_admin')) WITH CHECK (owner_id::text=(SELECT current_setting('app.user_id',true)) OR (SELECT effective_role()) IN ('hospital_admin','organization_admin'))")
    op.execute("CREATE OR REPLACE FUNCTION dispatch_queue() RETURNS TABLE(job_id uuid) LANGUAGE sql STABLE SECURITY DEFINER SET search_path=public,pg_temp AS $$ SELECT id FROM jobs WHERE status IN ('queued','retry_pending') OR (status='running' AND (data->>'lease_until')::timestamptz < now()) OR (status='waiting_provider' AND (data->>'next_retry_at')::timestamptz<now()) ORDER BY created_at LIMIT 100 $$")

def downgrade():
    for table in ['conversations','messages','agent_runs','tool_calls','ai_usage','jobs']:op.execute(f'DROP POLICY run_owner ON {table}')
    for table in LEDGERS+['observations']:
        for suffix in ['read','insert','update','delete']:op.execute(f'DROP POLICY tenant_{suffix} ON {table}')
        scope="organization_id::text=(SELECT current_setting('app.org_id',true)) AND (SELECT authz_scope()) ? facility_id::text AND ((SELECT authz_scope()) ? (facility_id::text||'/*') OR (SELECT authz_scope()) ? (facility_id::text||'/'||zone_code))"
        op.execute(f'CREATE POLICY tenant_scope ON {table} USING ({scope}) WITH CHECK ({scope})')
    op.execute('DROP FUNCTION effective_role()')
