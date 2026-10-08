import os
import subprocess
import sys
from pathlib import Path
from dotenv import dotenv_values
root=Path(__file__).resolve().parent.parent
env={**os.environ,**{k:v for k,v in dotenv_values(root/'.local/runtime.env').items() if v is not None},'PYTHONPATH':str(root/'services/api'),'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'}
args=sys.argv[1:]
if not args:
    raise SystemExit('Usage: python scripts/local.py <command> [args]')
cmd = [str(root/'services/api/.venv/bin'/args[0])]+args[1:]
raise SystemExit(subprocess.call(cmd,env=env,cwd=root/'services/api'))
