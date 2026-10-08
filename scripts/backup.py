"""Consistent database and scoped S3 artifact backup. Privileged DB URL only in backup process."""
import argparse,hashlib,json,os,subprocess,sys
from pathlib import Path
from urllib.parse import urlparse
import boto3
p=argparse.ArgumentParser();p.add_argument('operation',choices=['backup','restore']);p.add_argument('--directory',required=True);p.add_argument('--database-url',default=os.environ.get('BACKUP_DATABASE_URL'));p.add_argument('--pg-dump',default='pg_dump');p.add_argument('--pg-restore',default='pg_restore');p.add_argument('--skip-objects',action='store_true');p.add_argument('--container-runtime',choices=['docker','podman']);p.add_argument('--database-container');args=p.parse_args()
if not args.database_url:raise SystemExit('Dedicated BACKUP_DATABASE_URL required; runtime DB cannot bypass RLS')
u=urlparse(args.database_url.replace('postgresql+psycopg','postgresql'));env={**os.environ,'PGPASSWORD':u.password or ''};conn=['--host',u.hostname or 'localhost','--port',str(u.port or 5432),'--username',u.username or '', '--dbname',u.path.lstrip('/')]
directory=Path(args.directory)
s3=boto3.client('s3',endpoint_url=os.environ['OBJECT_STORAGE_ENDPOINT'],aws_access_key_id=os.environ['OBJECT_STORAGE_ACCESS_KEY'],aws_secret_access_key=os.environ['OBJECT_STORAGE_SECRET_KEY']) if not args.skip_objects else None
bucket=os.environ.get('OBJECT_STORAGE_BUCKET','greenops')
if args.operation=='backup':
 directory.mkdir(parents=True,exist_ok=False)
 if args.container_runtime:
  if not args.database_container:raise SystemExit('--database-container required')
  with (directory/'database.dump').open('wb') as target:
   subprocess.run([args.container_runtime,'exec','-i',args.database_container,'pg_dump','--username',u.username,'--dbname',u.path.lstrip('/'),'--format=custom','--no-owner'],stdout=target,env=env,check=True)
 else:subprocess.run([args.pg_dump,*conn,'--format=custom','--no-owner','--file',str(directory/'database.dump')],env=env,check=True)
 files=[]
 if s3:
  for page in s3.get_paginator('list_objects_v2').paginate(Bucket=bucket):
   for item in page.get('Contents',[]):
    dest=directory/'objects'/item['Key'];dest.parent.mkdir(parents=True,exist_ok=True);s3.download_file(bucket,item['Key'],str(dest));files.append({'key':item['Key'],'sha256':hashlib.sha256(dest.read_bytes()).hexdigest()})
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
   subprocess.run([args.container_runtime,'exec','-i',args.database_container,'pg_restore','--username',u.username,'--dbname',u.path.lstrip('/'),'--no-owner','--role','greenops_migrator'],stdin=source,env=env,check=True)
 else:subprocess.run([args.pg_restore,*conn,'--no-owner','--role','greenops_migrator',str(directory/'database.dump')],env=env,check=True)
 if s3:
  try:s3.head_bucket(Bucket=bucket)
  except Exception:s3.create_bucket(Bucket=bucket)
  for obj in manifest['objects']:
   src=directory/'objects'/obj['key']
   if hashlib.sha256(src.read_bytes()).hexdigest()!=obj['sha256']:raise SystemExit('Object backup checksum mismatch')
   s3.upload_file(str(src),bucket,obj['key'])
 print(json.dumps({'status':'restored','objects':len(manifest['objects']),'directory':str(directory)}))
