import asyncio
from sqlalchemy import select
from app.core.db import transaction
from app.core.auth import resolve_scope
from app.core.models import World
from app.core.records import query,insert,get
from app.domains.crud import update_record
from app.domains.contracts import RecordInput
from app.ai.orchestrator import start_run,run

async def evaluate_refresh(principal):
    with transaction(principal.user_id,principal.organization_id) as db:
        world=db.scalar(select(World).where(World.code=='extended_v1'));scope=resolve_scope(db,principal,world.id)
        asset=query(db,scope,'assets',1)[0];original=dict(asset.data);name=asset.name;asset_id=asset.id;world_id=world.id
    async def ask():
        with transaction(principal.user_id,principal.organization_id) as db:
            scope=resolve_scope(db,principal,world_id);conversation=insert(db,scope,'conversations',{},name='Actual input refresh verification',owner_id=principal.user_id)
            record=start_run(db,scope,conversation.id,f'Read get_assets_and_dependencies. State only the configured mode for the asset named {name}, distinguish it from telemetry. Use the asset register, no arithmetic.',enqueue_job=False)
        result=await run(principal,world_id,record['id'])
        with transaction(principal.user_id,principal.organization_id) as db:
            scope=resolve_scope(db,principal,world_id);record=get(db,scope,'agent_runs',record['id']);tools=record.data.get('tool_results',[])
        return {'run_id':str(record.id),'status':record.status,'answer':result.get('answer'),'tool_register_mode':next((a['data']['mode'] for t in tools for a in t.get('data',{}).get('assets',[]) if a['id']==str(asset_id)),None)}
    before=await ask();changed='offline' if original.get('mode')!='offline' else 'operational'
    try:
        with transaction(principal.user_id,principal.organization_id) as db:
            scope=resolve_scope(db,principal,world_id);row=get(db,scope,'assets',asset_id)
            update_record(db,scope,'assets',row.id,RecordInput(name=row.name,zone_code=row.zone_code,owner_id=row.owner_id,category=row.category,status=row.status,expected_version=row.version,data={**original,'mode':changed}))
        after=await ask()
    finally:
        with transaction(principal.user_id,principal.organization_id) as db:
            scope=resolve_scope(db,principal,world_id);row=get(db,scope,'assets',asset_id)
            update_record(db,scope,'assets',row.id,RecordInput(name=row.name,zone_code=row.zone_code,owner_id=row.owner_id,category=row.category,status=row.status,expected_version=row.version,data=original))
    passed=before['status']==after['status']=='completed' and before['tool_register_mode']!=after['tool_register_mode'] and changed.lower() in (after['answer'] or '').lower()
    return {'status':'passed_real_provider_input_refresh' if passed else 'failed','asset_id':str(asset_id),'before':before,'after':after,'original_restored':True}
