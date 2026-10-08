"""Refresh only GreenOps table statistics after a large initial cloud seed."""
import sys
from pathlib import Path
import psycopg
from psycopg import sql
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'services/api'))
from app.core.models import Base

values = dict(line.split('=', 1) for line in Path('.env').read_text().splitlines()
              if '=' in line and not line.startswith('#'))
url = values['MIGRATION_DATABASE_URL'].replace('postgresql+psycopg', 'postgresql')
try:
    with psycopg.connect(url, connect_timeout=15, prepare_threshold=None, autocommit=True) as db:
        names = [sql.Identifier('public', name) for name in Base.metadata.tables]
        db.execute(sql.SQL('ANALYZE {}').format(sql.SQL(', ').join(names)))
    print('Refreshed statistics for', len(names), 'GreenOps tables. No other schemas changed.')
except psycopg.Error as error:
    raise SystemExit('Statistics refresh failed: ' + type(error).__name__) from None
