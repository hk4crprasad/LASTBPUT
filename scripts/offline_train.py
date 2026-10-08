"""Offline-only training/evaluation with original private labels. Never used by API tools."""
import argparse,hashlib,json,os,sys
from pathlib import Path
os.environ.setdefault('OMP_NUM_THREADS','1');os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
root=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(root/'research/starter'));sys.path.insert(0,str(root/'services/api'))
import pandas as pd,numpy as np
from greenops.pipeline import train,features,chronological_masks,detection_metrics
from app.analytics.service import contextual_candidates

p=argparse.ArgumentParser();p.add_argument('--data',default=str(root/'research/starter/data'));p.add_argument('--out',default=str(root/'research/evaluation/retrained-v1'));args=p.parse_args()
data_dir,out=Path(args.data),Path(args.out)
if out.exists() and (out/'evaluation.json').exists():raise SystemExit('Immutable output already exists; choose a new version directory')
print(json.dumps({'stage':'training_started','input':str(data_dir),'output':str(out)}),flush=True)
report=train(data_dir,out)
print(json.dumps({'stage':'training_finished','models':len(report['forecast']),'next':'chronological and contextual evaluation'}),flush=True)
data=pd.read_csv(data_dir/'observations.csv',parse_dates=['observed_at'])
frame=features(data,24);masks=chronological_masks(frame,data.observed_at)
(out/'split-manifest.json').write_text(json.dumps({'split_policy':masks[3],'data_sha256':report['data_sha256'],'train_origin_count':int(masks[0].sum()),'validation_origin_count':int(masks[1].sum()),'test_origin_count':int(masks[2].sum()),'purged_origin_count':int((~(masks[0]|masks[1]|masks[2])).sum())},indent=2))
evaluation={}
for prefix in ['','stress_']:
 observable=pd.read_csv(data_dir/(prefix+'observations.csv'),parse_dates=['observed_at'])
 candidates=contextual_candidates(observable)
 # Incident starts are public detector output. Labels are joined only in this offline evaluator.
 labels=pd.read_csv(data_dir/(prefix+'private_labels.csv'),keep_default_na=False)
 index=observable[['observed_at','zone_id']].copy();pred=np.zeros(len(index),dtype=int)
 for incident in candidates:
  at=pd.Timestamp(incident['observed_at']);mask=(index.zone_id==incident['zone'])&(index.observed_at==at);pred[np.flatnonzero(mask)]=1
 metrics=detection_metrics(index,pred,labels)
 metrics['detector_version']='contextual-robust-v1';metrics['evaluation_note']='Predeclared context residual thresholds; incident-onset-only precision/recall, not raw sustained-row sensitivity. No label-based tuning.'
 evaluation[prefix or 'base']=metrics
(out/'contextual-detection.json').write_text(json.dumps(evaluation,indent=2))
for model,metric in report['forecast'].items():
 predictions=pd.read_csv(out/f'predictions_{model}.csv');metric['by_zone']={z:{'mae':float(np.mean(np.abs(g.actual-g.prediction))),'rows':len(g)} for z,g in predictions.groupby('zone_id')}
report['artifact_manifest']=[{'path':f.name,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()} for f in out.glob('*.joblib')]
(out/'evaluation.json').write_text(json.dumps(report,indent=2))
print(json.dumps({'out':str(out),'split_policy':masks[3],'models':len(report['forecast']),'contextual_detection':evaluation},indent=2))
