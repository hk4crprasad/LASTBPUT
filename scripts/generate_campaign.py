"""630,720-row future campaign option with separate public rows and offline injection truth."""
import argparse,csv,json,hashlib,sys,random
from pathlib import Path
root=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(root/'services/api'))
from app.domains.generator import generate_rows
p=argparse.ArgumentParser();p.add_argument('--days',type=int,default=365);p.add_argument('--facilities',type=int,default=6);p.add_argument('--zones',type=int,default=12);p.add_argument('--seed',type=int,default=11001);p.add_argument('--out',default='research/evaluation/campaign-v1');args=p.parse_args()
if not 1<=args.facilities<=6:raise SystemExit('Use 1–6 fictional facility archetypes')
out=Path(args.out)
if out.exists():raise SystemExit('Choose a new immutable campaign version directory')
out.mkdir(parents=True);total=0
archetypes=['compact_urban','regional_general','teaching_campus','coastal','rural','high_activity']
for i in range(args.facilities):
 profile=random.Random(args.seed+i*7919)
 cfg={'demand_scale':round(profile.uniform(.8,1.3),3),'weather_offset_c':round(profile.uniform(-3,3),2),'fault_scale':round(profile.uniform(.6,1.8),3),'sensor_error_hours':[2+i,15+i*2],'seed':args.seed+i*7919,'days':args.days,'zones':args.zones,'start':'2025-01-01T00:00:00Z'}
 with (out/f'{i}-private-truth.jsonl').open('w') as truth:
  rows,states,zones=generate_rows(cfg,lambda r:truth.write(json.dumps(r)+'\n'))
 for row in rows:row['facility_id']=f'FICTIONAL_{archetypes[i%6].upper()}'
 file=out/f'{i}-observations.csv'
 with file.open('w') as f:
  writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
 total+=len(rows)
 (out/f'{i}-manifest.json').write_text(json.dumps({'configuration':cfg,'archetype':archetypes[i%6],'source_type':'synthetic_campaign','rows':len(rows),'sha256':hashlib.sha256(file.read_bytes()).hexdigest()},indent=2))
print(json.dumps({'rows':total,'facilities':args.facilities,'seed':args.seed,'out':str(out)}))
