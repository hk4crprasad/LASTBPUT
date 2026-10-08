import asyncio
from datetime import timedelta
from uuid import UUID
from celery import Celery
from sqlalchemy import text,select
from app.core.settings import settings
from app.core.db import Session,transaction
from app.core.models import TABLES,now
from app.core.auth import Principal,resolve_scope
from app.core.records import get,serialize

celery=Celery('greenops',broker=settings().redis_url)
celery.conf.update(task_acks_late=True,task_reject_on_worker_lost=True,worker_prefetch_multiplier=1,
   task_serializer='json',accept_content=['json'],broker_connection_retry_on_startup=True,
   beat_schedule={'reconcile-outbox':{'task':'greenops.dispatch','schedule':10.},'monitor-risks':{'task':'greenops.monitor','schedule':60.}},
   task_soft_time_limit=180,task_time_limit=210)

@celery.task(name='greenops.dispatch')
def dispatch():
    with Session.begin() as db:ids=list(db.scalars(text('SELECT job_id FROM dispatch_queue()')))
    for job in ids:
        try:execute.delay(str(job))
        except Exception:return {'dispatched':False,'reason':'Broker unavailable; jobs remain in PostgreSQL'}
    return {'queued':len(ids)}

@celery.task(name='greenops.execute',bind=True,max_retries=3)
def execute(self,job_id):
    with Session.begin() as db:
        identity=db.execute(text('SELECT * FROM dispatch_identity(:job)'),{'job':UUID(job_id)}).mappings().first()
    if not identity:return {'status':'already_finished_or_unavailable'}
    p=Principal(identity['user_id'],identity['organization_id'],identity['role'])
    with transaction(p.user_id,p.organization_id) as db:
        scope=resolve_scope(db,p,identity['world_id']);job=get(db,scope,'jobs',job_id,True)
        if job.status=='running' and job.data.get('lease_until') and __import__('datetime').datetime.fromisoformat(job.data['lease_until'])>now():return {'status':'leased'}
        job.status='running';job.data={**job.data,'attempts':job.data.get('attempts',0)+1,'lease_until':(now()+timedelta(seconds=settings().job_lease_seconds)).isoformat()}
        kind=job.category;payload=job.data['payload'];attempts=job.data['attempts']
    try:
        if kind=='agent':
            from app.ai.orchestrator import run
            result=asyncio.run(run(p,identity['world_id'],payload['run_id']))
        else:
            with transaction(p.user_id,p.organization_id) as db:
                db.execute(text("SELECT set_config('statement_timeout','0',true)"))
                scope=resolve_scope(db,p,identity['world_id'])
                if kind in {'simulation','infer','report'} and payload.get('_context'):
                    from app.ai.orchestrator import pinned_scope
                    scope=pinned_scope(scope,payload['_context'])
                if kind=='simulation':
                    from app.simulation.service import save_simulation
                    from app.simulation.engine import Scenario,Baseline
                    result=save_simulation(db,scope,Scenario.model_validate(payload['scenario']),'job:'+job_id,Baseline.model_validate(payload['baseline']))
                elif kind=='infer':
                    scope.require('models')
                    from app.analytics.service import infer
                    result=infer(db,scope)
                elif kind=='import':
                    scope.require('imports')
                    from app.domains.importer import import_starter,import_rows
                    if payload.get('rows') is not None:result=import_rows(db,scope,payload['rows'],payload['dataset_code'],payload['sha256'])
                    else:result=import_starter(db,scope,settings().starter_path)
                elif kind=='report':
                    from app.domains.reports import create_report
                    result=create_report(db,scope,payload,'job:'+job_id)
                elif kind=='train':raise ValueError('Offline training isolation required; use documented training container')
                else:raise ValueError('Unsupported job handler')
        with transaction(p.user_id,p.organization_id) as db:
            scope=resolve_scope(db,p,identity['world_id']);job=get(db,scope,'jobs',job_id,True)
            if job.status!='cancelled':
                job.status='waiting_provider' if kind=='agent' and result.get('status') in {'configuration_required','waiting_provider'} else ('failed' if kind=='agent' and result.get('status') in {'failed','grounding_failed'} else 'completed')
                if job.status=='waiting_provider' and attempts>=settings().job_max_retries:
                    job.status='failed';job.data={**job.data,'error':'Provider retry budget exhausted; explicitly retry the original snapshot or start a fresh run'}
                job.data={**job.data,'result':result,'completed_at':now().isoformat(),'next_retry_at':(now()+timedelta(minutes=5)).isoformat()}
            cls=TABLES['outbox_events']
            for event in db.scalars(select(cls).where(cls.parent_id==job.id)):event.status='delivered'
        return {'status':job.status,'job_id':job_id}
    except Exception as exc:
        retryable=type(exc).__name__ in {'APIConnectionError','APITimeoutError','RateLimitError','OperationalError','ConnectionError'}
        with transaction(p.user_id,p.organization_id) as db:
            scope=resolve_scope(db,p,identity['world_id']);job=get(db,scope,'jobs',job_id,True)
            job.status='retry_pending' if retryable and attempts<settings().job_max_retries else 'failed'
            job.data={**job.data,'error_type':type(exc).__name__,'error':'Provider/dependency failed' if retryable else str(exc)[:500],'failed_at':now().isoformat()}
        return {'status':job.status,'error_type':type(exc).__name__}

@celery.task(name='greenops.monitor')
def monitor():
    from app.ai.monitor import investigate_triggers
    with Session.begin() as db:principals=db.execute(text('SELECT * FROM monitor_principals()')).mappings().all()
    result=[]
    for identity in principals:
        p=Principal(identity['user_id'],identity['organization_id'],identity['role'])
        with transaction(p.user_id,p.organization_id) as db:result.append(investigate_triggers(db,p))
    return result
