"""Relational scope and time-series core; each operational ledger has its own table."""
from datetime import datetime, timezone
from uuid import UUID, uuid4
from sqlalchemy import (Boolean, CheckConstraint, DateTime, Float, ForeignKey, ForeignKeyConstraint,
                        Index, Integer, Numeric, String, Text, UniqueConstraint, Uuid)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now():
    return datetime.now(timezone.utc)

class Base(DeclarativeBase):
    pass

class Organization(Base):
    __tablename__ = 'organizations'
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(150))

class User(Base):
    __tablename__ = 'users'
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(200), unique=True)
    name: Mapped[str] = mapped_column(String(150))
    password_hash: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    service_principal: Mapped[bool] = mapped_column(Boolean, default=False)

class Membership(Base):
    __tablename__ = 'memberships'
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey('users.id'))
    organization_id: Mapped[UUID] = mapped_column(ForeignKey('organizations.id'))
    role: Mapped[str] = mapped_column(String(40))
    __table_args__ = (UniqueConstraint('user_id', 'organization_id'),)

class Facility(Base):
    __tablename__ = 'facilities'
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey('organizations.id'))
    code: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(200))
    timezone: Mapped[str] = mapped_column(String(80), default='Asia/Kolkata')
    facility_type: Mapped[str] = mapped_column(String(40), default='hospital')
    __table_args__ = (UniqueConstraint('id', 'organization_id'), UniqueConstraint('organization_id', 'code'))

class Grant(Base):
    __tablename__ = 'facility_grants'
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey('users.id'))
    organization_id: Mapped[UUID] = mapped_column(ForeignKey('organizations.id'))
    facility_id: Mapped[UUID] = mapped_column(Uuid)
    zone_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    __table_args__ = (ForeignKeyConstraint(['facility_id', 'organization_id'], ['facilities.id', 'facilities.organization_id']),)

class LoginSession(Base):
    __tablename__ = 'sessions'
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey('users.id'))
    organization_id: Mapped[UUID] = mapped_column(ForeignKey('organizations.id'))
    csrf_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class World(Base):
    __tablename__ = 'worlds'
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey('organizations.id'))
    facility_id: Mapped[UUID] = mapped_column(Uuid)
    code: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(200))
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    initial_as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    paused: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (ForeignKeyConstraint(['facility_id', 'organization_id'], ['facilities.id', 'facilities.organization_id']),
                      UniqueConstraint('id', 'organization_id', 'facility_id'),
                      UniqueConstraint('organization_id', 'facility_id', 'code'))

class Scoped:
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    facility_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    world_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    zone_code: Mapped[str | None] = mapped_column(String(80), nullable=True)

class Observation(Scoped, Base):
    __tablename__ = 'observations'
    metric: Mapped[str] = mapped_column(String(80))
    interval_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    interval_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str] = mapped_column(String(20))
    quality: Mapped[str] = mapped_column(String(40))
    source_type: Mapped[str] = mapped_column(String(60))
    source_event_id: Mapped[UUID] = mapped_column(Uuid)
    dataset_id: Mapped[UUID] = mapped_column(Uuid)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (ForeignKeyConstraint(['world_id', 'organization_id', 'facility_id'], ['worlds.id', 'worlds.organization_id', 'worlds.facility_id']),
                      UniqueConstraint('dataset_id', 'source_event_id', 'metric'),
                      CheckConstraint('interval_start IS NULL OR interval_start < interval_end'),
                      CheckConstraint('value IS NULL OR value >= 0'),
                      Index('ix_observations_scope_metric_time', 'world_id', 'metric', 'zone_code', 'interval_end'))

class Metric(Base):
    __tablename__ = 'metric_catalog'
    code: Mapped[str] = mapped_column(String(80), primary_key=True)
    domain: Mapped[str] = mapped_column(String(30))
    unit: Mapped[str] = mapped_column(String(20))
    semantics: Mapped[str] = mapped_column(String(30))
    aggregation: Mapped[str] = mapped_column(String(20))
    minimum: Mapped[float] = mapped_column(Float, default=0)
    maximum: Mapped[float | None] = mapped_column(Float, nullable=True)

# Separate tables keep ledger identities, RLS, indices, transitions and CRUD domain-specific.
# Configurations and immutable evidence bodies use validated JSONB; identity/status/time are relational.
LEDGERS = ['buildings', 'floors', 'zones', 'zone_capacities', 'operating_schedules', 'dataset_versions',
 'source_events', 'import_jobs', 'import_rejects', 'operational_snapshots', 'quality_events', 'aggregate_snapshots',
 'assets', 'asset_dependencies', 'asset_telemetry', 'tanks', 'tank_states', 'power_sources', 'power_states',
 'waste_categories', 'waste_bins', 'waste_batches', 'waste_movements', 'pickups', 'handover_evidence',
 'environment_readings', 'parking_areas', 'parking_events', 'parking_snapshots', 'safety_incidents',
 'maintenance_orders', 'policy_versions', 'tariff_versions', 'emission_factor_versions', 'documents',
 'document_chunks', 'model_versions', 'training_runs', 'evaluation_results', 'forecast_runs', 'forecast_points',
 'detector_runs', 'alerts', 'alert_evidence', 'actions', 'action_events', 'action_evidence', 'action_proposals',
 'scenario_definitions', 'simulation_runs', 'simulation_points', 'simulation_comparisons', 'conversations',
 'messages', 'agent_runs', 'tool_calls', 'ai_usage', 'agent_policies', 'jobs', 'outbox_events', 'audit_events',
 'report_runs', 'stored_files']

class Ledger(Scoped):
    name: Mapped[str] = mapped_column(String(300), default='')
    category: Mapped[str] = mapped_column(String(80), default='')
    status: Mapped[str] = mapped_column(String(40), default='active')
    severity: Mapped[str] = mapped_column(String(20), default='info')
    owner_id: Mapped[UUID | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    parent_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    version: Mapped[int] = mapped_column(Integer, default=1)
    idempotency_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    value: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(30), nullable=True)
    source_type: Mapped[str] = mapped_column(String(60), default='user_recorded')
    data: Mapped[dict] = mapped_column(JSONB, default=dict)

TABLES = {}
for table in LEDGERS:
    cls = type(''.join(w.title() for w in table.split('_')), (Ledger, Base), {
        '__tablename__': table,
        '__table_args__': (
            ForeignKeyConstraint(['world_id', 'organization_id', 'facility_id'], ['worlds.id', 'worlds.organization_id', 'worlds.facility_id']),
            UniqueConstraint('world_id', 'idempotency_key'),
            UniqueConstraint('id', 'world_id', 'organization_id', 'facility_id'),
            Index(f'ix_{table}_scope_status_time', 'world_id', 'status', 'event_at'),
        )
    })
    TABLES[table] = cls

# Cross-ledger parent references preserve scope in addition to application validation.
PARENTS = {'floors': 'buildings', 'zone_capacities': 'zones', 'operational_snapshots': 'source_events',
           'asset_telemetry': 'assets', 'tank_states': 'tanks', 'power_states': 'power_sources',
           'waste_movements': 'waste_batches', 'handover_evidence': 'pickups',
           'parking_events': 'parking_areas', 'parking_snapshots': 'parking_areas',
           'document_chunks': 'documents', 'forecast_points': 'forecast_runs', 'alert_evidence': 'alerts',
           'action_events': 'actions', 'action_evidence': 'actions', 'simulation_points': 'simulation_runs',
           'messages': 'conversations', 'tool_calls': 'agent_runs', 'ai_usage': 'agent_runs',
           'outbox_events': 'jobs'}
for child, parent in PARENTS.items():
    Base.metadata.tables[child].append_constraint(ForeignKeyConstraint(
        ['parent_id', 'world_id', 'organization_id', 'facility_id'],
        [f'{parent}.id', f'{parent}.world_id', f'{parent}.organization_id', f'{parent}.facility_id']))
