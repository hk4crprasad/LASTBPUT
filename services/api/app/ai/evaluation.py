"""Explicit live evaluation campaign; unit CI uses fixtures instead."""
import asyncio,json
from uuid import UUID,uuid4
from sqlalchemy import select
from app.core.models import World,TABLES
from app.core.auth import resolve_scope
from app.core.records import insert,get
from app.core.db import transaction
from app.ai.orchestrator import start_run,run

QUESTIONS=[
 ('facility','How many occupied beds and total beds are there in this selected world? Read the facility snapshot.'),
 ('energy','How much interval energy was observed in the last 24 hours? Read the facility snapshot and state units.'),
 ('water','Read water consumption for the last 24 hours and identify any missing coverage.'),
 ('operations','Read operational context and explain OPD counts versus occupied bed-days.'),
 ('assets','Which assets have operational dependencies? Use the assets tool and list recorded modes.'),
 ('reserves','Read separate water reserves and explain protected fire storage.'),
 ('waste','Which category-specific waste batches need attention first? Use waste state and configured deadlines.'),
 ('environment','Read latest indoor temperature, PM2.5 and CO2, with configured threshold limitations.'),
 ('parking','Read parking and safety. State occupancy, queue and capacity for latest parking snapshot.'),
 ('safety','Read parking and safety. Explain incident count and its zone-hour denominator.'),
 ('forecast','Read forecast targets and explain the supported leads and model limitations.'),
 ('actions','Read actions. Which actions remain open and who owns them?'),
 ('sustainability','Read sustainability. Explain estimated cost and carbon with exact factor assumptions.'),
 ('policy','Search operating documents for the operational SOP and state internal policy limitations.'),
 ('simulation','Simulate a 6-hour grid outage with pump failure using run_what_if and summarize unmet essential demand.')]

async def live_campaign(principal):
    results=[]
    with transaction(principal.user_id,principal.organization_id) as db:world_id=db.scalar(select(World.id).where(World.code=='extended_v1'))
    for domain,question in QUESTIONS:
        with transaction(principal.user_id,principal.organization_id) as db:
            scope=resolve_scope(db,principal,world_id)
            c=insert(db,scope,'conversations',{},name='Live evaluation: '+domain,owner_id=principal.user_id)
            record=start_run(db,scope,c.id,question,key='live-eval:'+str(uuid4()),enqueue_job=False)
        answer=await run(principal,world_id,record['id'])
        with transaction(principal.user_id,principal.organization_id) as db:
            r=get(db,resolve_scope(db,principal,world_id),'agent_runs',record['id'])
            tools=[x.get('tool') for x in r.data.get('tool_results',[])]
            evidence_count=sum(len(x.get('evidence',[])) for x in r.data.get('tool_results',[]))
            results.append({'domain':domain,'question':question,'run_id':record['id'],'status':r.status,'tools':tools,
                            'evidence_count':evidence_count,'grounding':r.data.get('grounding'),'answer':answer.get('answer'),'error':r.data.get('error')})
    return {'mode':'real_provider','questions':len(results),'passed':sum(r['status']=='completed' and bool(r['tools']) for r in results),
            'limitations':['Numeric/citation validator is conservative and can withhold valid paraphrases. Tool output remains authoritative.'], 'results':results}

def evaluate(db,principal):
    # Caller command is explicitly credentialed; sessions are reopened per run for durable evidence.
    return asyncio.run(live_campaign(principal))
