import secrets
from pathlib import Path
p = Path('.env')
if p.exists() and 'GENERATE_LOCALLY' not in p.read_text():
    print('.env already initialized; preserving secrets')
else:
    text = p.read_text() if p.exists() else Path('.env.example').read_text()
    runtime, migrator, db, obj, session = [secrets.token_urlsafe(32) for _ in range(5)]
    values = {'POSTGRES_PASSWORD': db, 'RUNTIME_DB_PASSWORD': runtime, 'MIGRATOR_DB_PASSWORD': migrator,
              'OBJECT_STORAGE_SECRET_KEY': obj, 'SESSION_SECRET': session,
              'DATABASE_URL': f'postgresql+psycopg://greenops:{runtime}@postgres:5432/greenops',
              'MIGRATION_DATABASE_URL': f'postgresql+psycopg://greenops_migrator:{migrator}@postgres:5432/greenops'}
    p.write_text('\n'.join(f'{line.split("=",1)[0]}={values[line.split("=",1)[0]]}' if line.split('=',1)[0] in values else line for line in text.splitlines())+'\n')
    p.chmod(0o600)
    print('Generated local secrets in .env')
