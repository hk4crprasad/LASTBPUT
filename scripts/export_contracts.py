"""Export public request/schema contracts; no operational DB or provider call occurs."""
import json,sys
from pathlib import Path
root=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(root/'services/api'))
from app.main import app
from app.domains.contracts import CONTRACTS
out=root/'packages/contracts';out.mkdir(parents=True,exist_ok=True)
(out/'openapi.json').write_text(json.dumps(app.openapi(),indent=2)+'\n')
(out/'domain-schemas.json').write_text(json.dumps({name:contract.model_json_schema() for name,(contract,domain) in CONTRACTS.items()},indent=2)+'\n')
print('Exported public OpenAPI and domain contracts to packages/contracts')
