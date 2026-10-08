from alembic import op
revision='0005'
down_revision='0004'
def upgrade():
    op.execute('GRANT SELECT ON alembic_version TO greenops')
    op.create_unique_constraint('uq_observation_world_zone_metric_time','observations',['world_id','zone_code','metric','interval_end'])
    op.create_unique_constraint('uq_source_world_zone_time','source_events',['world_id','zone_code','event_at'])
    op.execute('REVOKE UPDATE, DELETE ON source_events,observations FROM greenops')
    op.execute("CREATE OR REPLACE FUNCTION dispatch_identity(job uuid) RETURNS TABLE(user_id uuid,organization_id uuid,role text,world_id uuid) LANGUAGE sql STABLE SECURITY DEFINER SET search_path=public,pg_temp AS $$ SELECT j.owner_id,j.organization_id,m.role,j.world_id FROM jobs j JOIN users u ON u.id=j.owner_id JOIN memberships m ON m.user_id=j.owner_id AND m.organization_id=j.organization_id WHERE j.id=job AND u.active AND j.status IN ('queued','running','retry_pending','waiting_provider') $$")
def downgrade():
    op.drop_constraint('uq_observation_world_zone_metric_time','observations',type_='unique')
    op.drop_constraint('uq_source_world_zone_time','source_events',type_='unique')
    op.execute('GRANT UPDATE,DELETE ON source_events,observations TO greenops')
