import argparse
import json
from pathlib import Path
from sqlalchemy import select,text
from app.core.auth import Principal, resolve_scope
from app.core.db import transaction
from app.core.models import World
from app.core.settings import settings


def demo_principal():
    creds=json.loads(Path(settings().demo_credentials_path).read_text())['hospital_admin']
    from uuid import UUID
    from app.bootstrap import uid
    return Principal(UUID(creds['user_id']),uid('org'),'hospital_admin',creds['email'])

def main():
    parser=argparse.ArgumentParser(description='Hospital GreenOps operational commands')
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('seed-demo');p.add_argument('--starter',default=settings().starter_path)
    p=sub.add_parser('generate-world');p.add_argument('--config',required=True)
    p=sub.add_parser('infer');p.add_argument('--world',default='base_v1')
    for command in ['smoke-test','check-llm','verify-checksums','agent-evaluate','agent-refresh-evaluate','reconcile-jobs']:
        sub.add_parser(command)
    p=sub.add_parser('train');p.add_argument('--data',required=True);p.add_argument('--out',required=True)
    p=sub.add_parser('evaluate');p.add_argument('--data',required=True);p.add_argument('--out',required=True)
    args=parser.parse_args()
    if args.command=='verify-checksums':
        from app.domains.importer import verify_bundle
        print(json.dumps(verify_bundle(settings().starter_path),indent=2));return
    if args.command=='check-llm':
        import asyncio
        from app.ai.provider import check_provider
        print(json.dumps(asyncio.run(check_provider()),indent=2));return
    if args.command in {'train','evaluate'}:
        import os,subprocess,sys
        if os.environ.get('OFFLINE_TRAINING')!='true':raise SystemExit('Use isolated offline trainer; set OFFLINE_TRAINING=true only in the offline environment')
        script=Path(os.environ.get('OFFLINE_TRAIN_SCRIPT','/workspace/scripts/offline_train.py'))
        raise SystemExit(subprocess.call([sys.executable,str(script),'--data',args.data,'--out',args.out]))
    p=demo_principal()
    with transaction(p.user_id,p.organization_id) as db:
        db.execute(text("SELECT set_config('statement_timeout','0',true)"))
        if args.command=='seed-demo':
            from app.domains.importer import import_starter
            for world in db.scalars(select(World).where(World.code.in_(['base_v1','stress_v1']))):
                result=import_starter(db,resolve_scope(db,p,world.id),args.starter)
                print(json.dumps({'world':world.code,'import':result['data']}))
        elif args.command=='generate-world':
            from app.domains.generator import generate
            print(json.dumps(generate(db,p,Path(args.config))))
        elif args.command=='infer':
            from app.analytics.service import infer
            world=db.scalar(select(World).where(World.code==args.world))
            print(json.dumps(infer(db,resolve_scope(db,p,world.id))))
        elif args.command=='smoke-test':
            from app.domains.metrics import overview
            for w in db.scalars(select(World)):
                scope=resolve_scope(db,p,w.id)
                print(json.dumps(overview(db,scope),default=str))
        elif args.command=='reconcile-jobs':
            from app.jobs.service import reconcile
            print(reconcile(db,p))
        elif args.command=='agent-refresh-evaluate':
            import asyncio
            from app.ai.refresh_evaluation import evaluate_refresh
            print(json.dumps(asyncio.run(evaluate_refresh(p)),indent=2))
        elif args.command=='agent-evaluate':
            from app.ai.evaluation import evaluate
            print(json.dumps(evaluate(db,p),indent=2))

if __name__=='__main__':
    main()
