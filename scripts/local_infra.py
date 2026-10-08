"""Rootless local integration infrastructure. Docker Compose remains delivery startup."""
import os
import subprocess
from pathlib import Path
from dotenv import dotenv_values
if subprocess.run(['podman','image','exists','localhost/greenops-minio']).returncode!=0:
    subprocess.run(['podman','build','-t','localhost/greenops-minio','-f','infra/minio.Dockerfile','.'],check=True)
values = dict(dotenv_values('.env'))
for service,image,port,args in [
 ('postgres','docker.io/library/postgres:18.3','55432:5432',['-e','POSTGRES_DB=greenops','-e','POSTGRES_USER=bootstrap','-e','POSTGRES_PASSWORD='+values['POSTGRES_PASSWORD'],'-e','RUNTIME_DB_PASSWORD='+values['RUNTIME_DB_PASSWORD'],'-e','MIGRATOR_DB_PASSWORD='+values['MIGRATOR_DB_PASSWORD'],'-v',str(Path('infra/bootstrap.sh').resolve())+':/docker-entrypoint-initdb.d/01-roles.sh:ro,z','-v','greenops-local-pg:/var/lib/postgresql']),
 ('redis','docker.io/library/redis:7.4.8-alpine','56379:6379',[]),
 ('minio','localhost/greenops-minio','59000:9000',['-e','MINIO_ROOT_USER='+values['OBJECT_STORAGE_ACCESS_KEY'],'-e','MINIO_ROOT_PASSWORD='+values['OBJECT_STORAGE_SECRET_KEY']])]:
    name='greenops-local-'+service
    if subprocess.run(['podman','container','exists',name]).returncode==0:
        subprocess.run(['podman','start',name],check=True)
    else:
        cmd=['podman','run','-d','--name',name,'-p','127.0.0.1:'+port]+args+[image]
        if service=='minio':
            cmd+=['server','/data']
        subprocess.run(cmd,check=True)
local = dict(values)
local.update(DATABASE_URL=values['DATABASE_URL'].replace('@postgres:5432','@127.0.0.1:55432'),
             MIGRATION_DATABASE_URL=values['MIGRATION_DATABASE_URL'].replace('@postgres:5432','@127.0.0.1:55432'),
             REDIS_URL='redis://127.0.0.1:56379/0',OBJECT_STORAGE_ENDPOINT='http://127.0.0.1:59000',
             DEMO_CREDENTIALS_PATH=str(Path('.local/demo-credentials.json').resolve()),STARTER_PATH=str(Path('data/public/starter').resolve()))
p=Path('.local/runtime.env')
p.write_text('\n'.join(f'{k}={v}' for k,v in local.items())+'\n')
p.chmod(0o600)
print('Local infrastructure configured; use scripts/local.py for commands')
