from datetime import timedelta
from uuid import UUID
from sqlalchemy import select,func,text
from fastapi import HTTPException
from app.core.models import TABLES,World
from app.core.auth import resolve_scope
from app.core.records import query,insert,serialize,get
from app.core.settings import settings
from app.ai.orchestrator import start_run

def authorize_autonomy(db,scope,run,body):
    db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),{'key':str(scope.world.id)+':autonomous-task-budget'})
    if not settings().agent_autonomous_writes_enabled:raise HTTPException(403,'Server autonomous writes disabled')
    policies=query(db,scope,'agent_policies',1)
    if not policies or str(policies[0].id)!=run.data.get('policy',{}).get('id'):raise HTTPException(409,'Agent policy version changed; fresh investigation required')
    p=policies[0].data
    if not p.get('monitor_enabled') or not p.get('autonomous_task_creation'):raise HTTPException(403,'Policy is read/simulate/draft only')
    if body.category not in p.get('categories',[]) or str(body.owner_id) not in p.get('owner_pool',[]):raise HTTPException(403,'Category/owner outside autonomous policy')
    if not body.alert_id:raise HTTPException(422,'Autonomous task needs current incident')
    alert=get(db,scope,'alerts',body.alert_id,True)
    if alert.status!='open' or alert.severity not in p.get('severities',[]):raise HTTPException(409,'Risk no longer matches policy')
    cls=TABLES['actions'];cutoff=scope.world.as_of-timedelta(days=1)
    count=db.scalar(select(func.count()).select_from(cls).where(cls.world_id==scope.world.id,cls.idempotency_key.like('agent:%'),cls.event_at>cutoff))
    existing=db.scalar(select(cls).where(cls.world_id==scope.world.id,cls.data['alert_id'].as_string()==str(body.alert_id),cls.status!='closed'))
    if existing:raise HTTPException(409,'Active action already linked to incident')
    if count>=p.get('max_tasks_per_day',0):raise HTTPException(429,'Autonomous daily task budget reached')

def investigate_triggers(db,principal):
    queued=[]
    from app.analytics.service import detect
    from app.domains.state import waste_state,reserves_state
    for world in db.scalars(select(World)):
        scope=resolve_scope(db,principal,world.id)
        policies=query(db,scope,'agent_policies',1)
        # Deterministic alerts continue even when monitoring/provider is disabled.
        detect(db,scope)
        waste=waste_state(db,scope)
        for cat in waste['categories']:
            deadline=cat['deadline']
            if deadline and deadline['service_within_hours'] is not None and deadline['service_within_hours']<=2:
                key=f"waste-deadline:{cat['category']}:{world.as_of.date()}"
                if not db.scalar(select(TABLES['alerts']).where(TABLES['alerts'].world_id==world.id,TABLES['alerts'].idempotency_key==key)):
                    insert(db,scope,'alerts',cat,name='Waste pickup deadline risk',category='waste',status='open',severity='high',idempotency_key=key)
        for resource in reserves_state(db,scope)['reserves']:
            config=resource['configuration']['data'];state=resource['state']['data']
            if 'reserve_l' in state and config.get('kind')!='fire':
                net=config.get('essential_lph',0)+config.get('nonessential_lph',0)-state.get('inflow_lph',0)
                eta=state['reserve_l']/net if net>0 else None
                if eta is not None and eta<=6:
                    key=f"reserve:{resource['configuration']['id']}:{world.as_of.date()}"
                    if not db.scalar(select(TABLES['alerts']).where(TABLES['alerts'].world_id==world.id,TABLES['alerts'].idempotency_key==key)):
                        insert(db,scope,'alerts',{'reserve_l':state['reserve_l'],'net_drain_lph':net,'hours_to_depletion':eta,'assumption':'Constant flow projection'},name='Reserve projection breach',category='water',severity='high',status='open',idempotency_key=key)
        from app.domains.state import assets_state,environment_state,parking_safety
        def rule(key,name,category,evidence,zone=None):
            identity=key+':'+world.as_of.date().isoformat()
            if not db.scalar(select(TABLES['alerts']).where(TABLES['alerts'].world_id==world.id,TABLES['alerts'].idempotency_key==identity)):
                alert=insert(db,scope,'alerts',evidence,name=name,category=category,severity='high',status='open',zone_code=zone,idempotency_key=identity)
                insert(db,scope,'alert_evidence',evidence,parent_id=alert.id,zone_code=zone,name='Observable rule evidence')
        for telemetry in assets_state(db,scope)['telemetry']:
            if telemetry['data'].get('mode') in {'offline','degraded'}:
                rule('asset:'+telemetry['parent_id'],'Recorded asset mode needs inspection','maintenance',telemetry,telemetry['zone_code'])
        environment=environment_state(db,scope)
        policy=environment['policies'][0]['data'] if environment['policies'] else {}
        for reading in environment['readings']:
            for field,threshold in [('temperature_c','temperature_max_c'),('pm25_ug_m3','pm25_max_ug_m3'),('co2_ppm','co2_max_ppm')]:
                maximum=policy.get(threshold)
                if maximum is not None and reading['data'].get(field,0)>maximum:
                    rule('environment:'+reading['zone_code']+':'+field,'Configured environment threshold exceeded','environment',{'reading':reading,'threshold':maximum,'policy':'Internal demonstration threshold'},reading['zone_code'])
        parking=parking_safety(db,scope)
        for snapshot in parking['parking'][:1]:
            if snapshot['data'].get('queue',0)>0:
                rule('parking:'+snapshot['parent_id'],'Parking queue needs review','parking',snapshot)
        if not policies or not policies[0].data.get('monitor_enabled'):continue
        policy=policies[0];p={**policy.data,'id':str(policy.id),'version':policy.version}
        alerts=[a for a in query(db,scope,'alerts',100,status='open') if a.severity in p.get('severities',['high','critical'])]
        overdue=[a for a in query(db,scope,'actions',100) if a.due_at and a.due_at<world.as_of and a.status not in {'closed','verified'}]
        triggers=[('alert',a.id,a.name,a.zone_code) for a in alerts]+[('overdue',a.id,a.name,a.zone_code) for a in overdue]
        if p.get('daily_brief'):triggers.append(('daily',str(world.as_of.date()),'Daily operations brief',None))
        for kind,tid,name,zone in triggers[:10]:
            key=f'monitor:{kind}:{tid}:{world.as_of.date()}'
            active=db.scalar(select(TABLES['agent_runs']).where(TABLES['agent_runs'].world_id==world.id,TABLES['agent_runs'].data['trigger_id'].as_string()==str(tid),
                        TABLES['agent_runs'].event_at>world.as_of-timedelta(hours=p.get('cooldown_hours',6))))
            if active:continue
            convo=insert(db,scope,'conversations',{'mode':'monitor'},name='Monitor '+name,owner_id=principal.user_id,zone_code=zone)
            run=start_run(db,scope,convo.id,f'Investigate {kind} {tid}: {name}. Use evidence, run relevant scenario, draft an action plan. Create a software task only if server policy permits.','monitor',str(tid),p,key)
            queued.append(run['id'])
    return {'queued_runs':queued,'provider_configured':settings().llm_enabled and bool(settings().openai_api_key)}
