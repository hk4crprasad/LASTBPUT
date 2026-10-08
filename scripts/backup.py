"""Consistent public-schema database and scoped S3/Azure artifact backup. Privileged DB URL only in backup process."""
import argparse,hashlib,json,os,subprocess,sys
from pathlib import Path
from urllib.parse import urlparse, parse_qsl
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'services/api'))
from app.core.object_store import object_store
p=argparse.ArgumentParser();p.add_argument('operation',choices=['backup','restore']);p.add_argument('--directory',required=True);p.add_argument('--database-url',default=os.environ.get('BACKUP_DATABASE_URL'));p.add_argument('--pg-dump',default='pg_dump');p.add_argument('--pg-restore',default='pg_restore');p.add_argument('--skip-objects',action='store_true');p.add_argument('--container-runtime',choices=['docker','podman']);p.add_argument('--database-container');p.add_argument('--restore-role',default='greenops_migrator');args=p.parse_args()
if not args.database_url:raise SystemExit('Dedicated BACKUP_DATABASE_URL required; runtime DB cannot bypass RLS')
u=urlparse(args.database_url.replace('postgresql+psycopg','postgresql'));env={**os.environ,'PGPASSWORD':u.password or '', 'PGSSLMODE':dict(parse_qsl(u.query)).get('sslmode','prefer')};conn=['--host',u.hostname or 'localhost','--port',str(u.port or 5432),'--username',u.username or '', '--dbname',u.path.lstrip('/')]
directory=Path(args.directory)
objects=object_store() if not args.skip_objects else None
bucket=objects.bucket if objects else None
if args.operation=='backup':
 directory.mkdir(parents=True,exist_ok=False)
 if args.container_runtime:
  if not args.database_container:raise SystemExit('--database-container required')
  with (directory/'database.dump').open('wb') as target:
   subprocess.run([args.container_runtime,'exec','-i',args.database_container,'pg_dump','--username',u.username,'--dbname',u.path.lstrip('/'),'--format=custom','--no-owner','--schema=public'],stdout=target,env=env,check=True)
 else:subprocess.run([args.pg_dump,*conn,'--format=custom','--no-owner','--schema=public','--file',str(directory/'database.dump')],env=env,check=True)
 files=[]
 if objects:
  for item in objects.objects():
   dest=(directory/'objects'/item.key).resolve()
   if not dest.is_relative_to((directory/'objects').resolve()):raise SystemExit('Unsafe artifact key')
   dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(objects.get(item.key));files.append({'key':item.key,'sha256':hashlib.sha256(dest.read_bytes()).hexdigest()})
 manifest={'database_sha256':hashlib.sha256((directory/'database.dump').read_bytes()).hexdigest(),'bucket':bucket,'objects':files}
 (directory/'manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps({'status':'backed_up','objects':len(files),'directory':str(directory)}))
else:
 manifest=json.loads((directory/'manifest.json').read_text())
 if hashlib.sha256((directory/'database.dump').read_bytes()).hexdigest()!=manifest['database_sha256']:raise SystemExit('Database backup checksum mismatch')
 # Deliberately refuse a populated target. Restore is authorized by invoking this explicit command.
 import psycopg
 with psycopg.connect(args.database_url.replace('postgresql+psycopg','postgresql')) as db:
  if db.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'").fetchone()[0]:raise SystemExit('Restore target must be a fresh empty database')
 if args.container_runtime:
  with (directory/'database.dump').open('rb') as source:
   subprocess.run([args.container_runtime,'exec','-i',args.database_container,'pg_restore','--username',u.username,'--dbname',u.path.lstrip('/'),'--no-owner','--role',args.restore_role],stdin=source,env=env,check=True)
 else:subprocess.run([args.pg_restore,*conn,'--no-owner','--role',args.restore_role,str(directory/'database.dump')],env=env,check=True)
 if objects:
  import mimetypes
  objects.ensure_container()
  for obj in manifest['objects']:
   src=(directory/'objects'/obj['key']).resolve()
   if not src.is_relative_to((directory/'objects').resolve()):raise SystemExit('Unsafe artifact key')
   body=src.read_bytes()
   if hashlib.sha256(body).hexdigest()!=obj['sha256']:raise SystemExit('Object backup checksum mismatch')
   objects.put(obj['key'],body,mimetypes.guess_type(str(src))[0] or 'application/octet-stream',{'sha256':obj['sha256']})
 print(json.dumps({'status':'restored','objects':len(manifest['objects']),'directory':str(directory)}))
