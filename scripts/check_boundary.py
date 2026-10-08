import ast,json
from pathlib import Path
root=Path(__file__).resolve().parent.parent
runtime=root/'data/public/starter'
for p in runtime.rglob('*'):
 if 'private_label' in p.name:raise SystemExit('Private labels in public bundle')
for p in (runtime/'data').glob('*facility.json'):
 obj=json.loads(p.read_text())
 if 'events' in obj:raise SystemExit('Hidden event configuration leaked')
for p in (root/'apps/web').rglob('*'):
 if p.is_file() and 'node_modules' not in p.parts and '.next' not in p.parts and p.suffix in {'.ts','.tsx','.json'}:
  text=p.read_text()
  if 'OPENAI_API_KEY=' in text or 'NEXT_PUBLIC_OPENAI' in text:raise SystemExit('Provider key surface in web source')
print('PASS public/runtime boundary and server-only provider configuration')
