"""Provision a restricted runtime role; keep admin credentials out of app services.
Run with the API venv from the repository root. Reads SUPABASE_ADMIN_DATABASE_URL
from ignored .env. Never changes an existing role's password or an occupied schema.
"""
import os
import secrets
from pathlib import Path
from urllib.parse import quote, urlparse
import psycopg
from psycopg import sql


def configure(path=Path('.env')):
    lines = path.read_text().splitlines()
    values = dict(line.split('=', 1) for line in lines if '=' in line and not line.startswith('#'))
    admin = values.get('SUPABASE_ADMIN_DATABASE_URL', '')
    if not admin:
        raise SystemExit('Set SUPABASE_ADMIN_DATABASE_URL to your session-pooler URL in ignored .env')
    u = urlparse(admin.replace('postgresql+psycopg', 'postgresql'))
    if u.port != 5432 or not u.username or '.' not in u.username:
        raise SystemExit('Use the Supabase session pooler on port 5432 with user.project username')
    project = u.username.split('.', 1)[1]
    current = urlparse(values.get('DATABASE_URL', '').replace('postgresql+psycopg', 'postgresql'))
    with psycopg.connect(u.geturl(), connect_timeout=15, prepare_threshold=None) as db:
        role = db.execute("SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname='greenops'").fetchone()
        if role:
            if role != (False, False) or current.username != 'greenops.' + project or not current.password:
                raise SystemExit('Existing greenops role cannot be safely reused with configured runtime URL')
            password = current.password
        else:
            if db.execute("SELECT count(*) FROM pg_tables WHERE schemaname='public'").fetchone()[0]:
                raise SystemExit('Review existing public tables before installing GreenOps in this project')
            password = secrets.token_urlsafe(32)
            db.execute(sql.SQL('CREATE ROLE greenops LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}').format(sql.Literal(password)))
            db.execute(sql.SQL('GRANT CONNECT ON DATABASE {} TO greenops').format(sql.Identifier(u.path.lstrip('/'))))
    runtime = f'postgresql+psycopg://greenops.{project}:{quote(password, safe="")}@{u.hostname}:6543{u.path}?sslmode=require'
    with psycopg.connect(runtime.replace('postgresql+psycopg', 'postgresql'), connect_timeout=15, prepare_threshold=None) as db:
        assert db.execute('SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user').fetchone() == (False, False)
    changes = {'DATABASE_URL': runtime, 'MIGRATION_DATABASE_URL': admin, 'DATABASE_PREPARE_THRESHOLD': 'disabled',
               'DATABASE_STATEMENT_TIMEOUT_MS': '10000'}
    for key, value in changes.items():
        lines = [line for line in lines if not line.startswith(key + '=')]
        lines.append(key + '=' + value)
    path.write_text('\n'.join(lines) + '\n')
    path.chmod(0o600)
    print('Restricted Supabase runtime login verified; server-side .env updated. Apply compose.supabase.yaml.')


if __name__ == '__main__':
    try:
        configure()
    except psycopg.Error as error:
        # Connection exception text/URLs can contain secrets. Report only its class.
        raise SystemExit('Supabase provisioning failed: ' + type(error).__name__) from None
