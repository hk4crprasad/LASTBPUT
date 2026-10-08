from alembic import op
revision='0003'
down_revision='0002'
def upgrade():
    op.execute('''CREATE FUNCTION dispatch_identity(job uuid) RETURNS TABLE(user_id uuid,organization_id uuid,role text,world_id uuid)
      LANGUAGE sql STABLE SECURITY DEFINER SET search_path=public,pg_temp AS $$
      SELECT j.owner_id,j.organization_id,m.role,j.world_id FROM jobs j JOIN users u ON u.id=j.owner_id
      JOIN memberships m ON m.user_id=j.owner_id AND m.organization_id=j.organization_id
      WHERE j.id=job AND u.active AND j.status IN ('queued','running','retry_pending') $$''')
    op.execute('''CREATE FUNCTION dispatch_queue() RETURNS TABLE(job_id uuid) LANGUAGE sql STABLE SECURITY DEFINER
      SET search_path=public,pg_temp AS $$ SELECT id FROM jobs WHERE status IN ('queued','retry_pending')
      OR (status='running' AND (data->>'lease_until')::timestamptz < now()) ORDER BY created_at LIMIT 100 $$''')
    op.execute('''CREATE FUNCTION monitor_principals() RETURNS TABLE(user_id uuid,organization_id uuid,role text)
      LANGUAGE sql STABLE SECURITY DEFINER SET search_path=public,pg_temp AS $$
      SELECT u.id,m.organization_id,m.role FROM users u JOIN memberships m ON m.user_id=u.id
      WHERE u.service_principal AND u.active $$''')
    for sig in ['dispatch_identity(uuid)','dispatch_queue()','monitor_principals()']:
        op.execute(f'REVOKE ALL ON FUNCTION {sig} FROM PUBLIC')
        op.execute(f'GRANT EXECUTE ON FUNCTION {sig} TO greenops')
def downgrade():
    for sig in ['dispatch_identity(uuid)','dispatch_queue()','monitor_principals()']:op.execute(f'DROP FUNCTION {sig}')
