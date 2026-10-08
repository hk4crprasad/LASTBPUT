import hashlib
import json
from datetime import timedelta
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import sklearn
from sqlalchemy import select
from app.core.models import TABLES,Observation
from app.core.records import insert,query,serialize
from app.core.settings import settings
from app.analytics.starter import features,FEATURES,model_predict,anomaly_features


def trusted_bundle(model_id):
    root=Path(settings().starter_path)
    name=f'artifacts/{model_id}.joblib'
    manifest=json.loads((root/'MANIFEST.json').read_text())
    entry=next((f for f in manifest['files'] if f['path']==name),None)
    path=root/name
    if not entry or hashlib.sha256(path.read_bytes()).hexdigest()!=entry['sha256']:
        raise ValueError('Untrusted artifact checksum')
    if sklearn.__version__!='1.8.0' or np.__version__!='2.3.5' or pd.__version__!='2.2.3' or joblib.__version__!='1.5.3':
        raise ValueError('Supplied artifact environment contract mismatch')
    bundle=joblib.load(path)
    if model_id!='anomaly' and bundle['feature_columns']!=FEATURES:
        raise ValueError('Feature contract mismatch')
    return bundle,entry['sha256']

def frame(db,scope,hours=201):
    cls=TABLES['source_events']
    rows=db.scalars(select(cls).where(cls.world_id==scope.world.id,cls.event_at<=scope.world.as_of,
                                    cls.event_at>=scope.world.as_of-timedelta(hours=hours)).order_by(cls.zone_code,cls.event_at)).all()
    data=pd.DataFrame([r.data for r in rows])
    if not data.empty:
        data['observed_at']=pd.to_datetime(data.observed_at,utc=True)
        for c in ['energy_kwh','water_l','temperature_c','occupied_beds','opd_visits','zone_code','cleaning_schedule']:
            data[c]=pd.to_numeric(data[c])
    return data

def models(db,scope):
    root=Path(settings().starter_path)
    registry=json.loads((root/'artifacts/model_registry.json').read_text())
    evaluation=json.loads((root/'artifacts/evaluation.json').read_text())
    statuses={r.name:r for r in query(db,scope,'model_versions',100)}
    for item in registry:
        existing=statuses.get(item['model_id'])
        if existing:item.update(status=existing.status,record_id=str(existing.id),version=existing.version)
        item['evaluation']=evaluation['anomaly'] if item['model_id']=='anomaly' else evaluation['forecast'][item['model_id']]
        item['limitations']=['Synthetic-only; energy loses to weekly baseline under shift. Generic detector has weak held-out precision/recall. No resource savings established.']
    return {'items':registry,'evaluation':evaluation,'versions':evaluation['versions']}

def infer(db,scope):
    register(db,scope)
    statuses={r.name:r.status for r in query(db,scope,'model_versions',100)}
    data=frame(db,scope)
    if data.empty:return {'status':'unavailable','reason':'No observations at virtual clock','points':[]}
    policy_hash=hashlib.sha256(json.dumps([(r.name,r.status,r.version) for r in query(db,scope,'model_versions',100)],sort_keys=True).encode()).hexdigest()[:16]
    run_key=f'infer:{scope.world.as_of.isoformat()}:starter-v1:{policy_hash}'
    cls=TABLES['forecast_runs']
    previous=db.scalar(select(cls).where(cls.world_id==scope.world.id,cls.idempotency_key==run_key))
    if previous:return {'status':previous.status,'run_id':str(previous.id),'idempotent':True}
    run=insert(db,scope,'forecast_runs',{'feature_version':'starter-v1','cutoff':scope.world.as_of.isoformat()},name='Experimental hourly target forecasts',status='running',idempotency_key=run_key)
    result=[]
    for lead in (1,6,24):
        eligible=features(data,lead)
        for zone,g in data.groupby('zone_id'):
            current=g.sort_values('observed_at').iloc[-1]
            issue=current.observed_at
            f=eligible[(eligible.zone_id==zone)&(eligible.origin_time==issue)]
            for target,metric,unit in [('energy_kwh','energy.interval_kwh','kWh'),('water_l','water.interval_l','L')]:
                model_id=f'{target}_{lead}h'
                bundle,sha=trusted_bundle(model_id)
                reason=None
                point={'metric':metric,'lead_hours':lead,'issue_time':issue.isoformat(),'target_time':(issue+timedelta(hours=lead)).isoformat(),
                       'model_id':model_id,'model_sha256':sha,'model_status':statuses.get(model_id,'experimental_synthetic_only'),'feature_version':'starter-v1',
                       'unit':unit,'interval_method':'90% validation residual; coverage not guaranteed under shift','source_type':'forecast'}
                baseline=g[g.observed_at==issue-timedelta(hours=168-lead)][target]
                b=None if baseline.empty or pd.isna(baseline.iloc[0]) else float(baseline.iloc[0])
                if issue<scope.world.as_of:
                    reason='Latest source observation precedes the selected virtual clock';b=None
                elif statuses.get(model_id) in {'disabled','rejected'}:reason='Model disabled by administrator; seasonal baseline used'
                elif int(current.zone_code)>3 or scope.world.code not in {'base_v1','stress_v1'}:reason='Extended-world feature distribution has not been evaluated with supplied models'
                elif f.empty:reason='Missing current/lags or insufficient contiguous history'
                elif len(g)!=len(pd.date_range(g.observed_at.min(),g.observed_at.max(),freq='h')):reason='History has missing intervals'
                if reason:
                    point.update(value=b,lower=None,upper=None,status='seasonal_baseline' if b is not None else 'unavailable',fallback_reason=reason)
                else:
                    value=float(model_predict(bundle,f)[0]);width=bundle['validation_residual_half_width']
                    point.update(value=value,lower=max(0,value-width),upper=value+width,status='experimental',fallback_reason=None)
                point['weekly_baseline']=b
                row=insert(db,scope,'forecast_points',point,parent_id=run.id,zone_code=zone,name=model_id,
                           value=point['value'],unit=unit,event_at=issue,source_type=point['source_type'])
                result.append({'id':str(row.id),'zone':zone,**point})
    # Persist the generic detector separately, never treat outlier score as proven fault.
    af=anomaly_features(data)
    if not af.empty and statuses.get('anomaly') not in {'disabled','rejected'}:
        detector,sha=trusted_bundle('anomaly')
        last=af.sort_values('observed_at').groupby('zone_id').tail(1)
        scores=detector['model'].decision_function(last[detector['feature_columns']])
        insert(db,scope,'detector_runs',{'artifact_sha256':sha,'results':[{'zone':z,'outlier_score':float(v)} for z,v in zip(last.zone_id,scores)],
                    'status':'experimental_synthetic_only','limitation':'Not a calibrated fault probability; not an operational alarm'},name='Generic Isolation Forest')
    run.status='completed';run.data={**run.data,'points':len(result)}
    detect(db,scope)
    return {'status':'completed','run_id':str(run.id),'points':result}

def contextual_candidates(data):
    """Predeclared robust residual + three-hour persistence, trained on past public context only."""
    found=[]
    for zone,g in data.groupby('zone_id'):
        g=g.sort_values('observed_at').reset_index(drop=True)
        if len(g)<72:continue
        hour=g.observed_at.dt.hour.to_numpy()
        x=np.column_stack([np.ones(len(g)),g.occupied_beds,g.opd_visits,np.maximum(g.temperature_c-25,0),g.cleaning_schedule,
                           np.sin(hour*2*np.pi/24),np.cos(hour*2*np.pi/24)])
        boundary=max(48,int(len(g)*.6))
        for target,minimum in [('energy_kwh',3),('water_l',60)]:
            y=g[target].to_numpy(dtype=float);valid=np.isfinite(y[:boundary])
            if valid.sum()<40:continue
            coeff=np.linalg.lstsq(x[:boundary][valid],y[:boundary][valid],rcond=None)[0]
            residual=y-x@coeff
            median=np.nanmedian(residual[:boundary]);mad=np.nanmedian(np.abs(residual[:boundary]-median))
            threshold=max(minimum,6*1.4826*mad)
            positive=np.isfinite(residual)&(residual>median+threshold)
            streak=0;active=False
            for i in range(boundary,len(g)):
                streak=streak+1 if positive[i] else 0
                if streak>=3 and not active:
                    found.append({'zone':zone,'metric':target,'observed_at':g.observed_at.iloc[i].isoformat(),
                                  'start':g.observed_at.iloc[i-2].isoformat(),'actual':float(y[i]),'expected':float((x@coeff)[i]),
                                  'residual':float(residual[i]),'threshold':float(threshold),'method':'contextual-robust-v1',
                                  'interpretation':'Observed excess; possible fault requires inspection, not confirmed leak'})
                    active=True
                if not positive[i]:active=False
    return found

def detect(db,scope):
    data=frame(db,scope,24*28)
    candidates=contextual_candidates(data) if not data.empty else []
    for item in candidates:
        key=f"contextual:{item['zone']}:{item['metric']}:{item['start']}"
        cls=TABLES['alerts']
        if not db.scalar(select(cls).where(cls.world_id==scope.world.id,cls.idempotency_key==key)):
            alert=insert(db,scope,'alerts',item,name='Sustained contextual excess',zone_code=item['zone'],category=item['metric'],severity='medium',status='open',idempotency_key=key,
                         event_at=pd.Timestamp(item['observed_at']).to_pydatetime())
            insert(db,scope,'alert_evidence',item,parent_id=alert.id,zone_code=item['zone'],name='Context, residual and persistence')
    # Quality is an operational issue independent of anomaly models.
    for row in query(db,scope,'quality_events',20):
        if (scope.world.as_of-row.event_at).total_seconds()<=24*3600:
            key='missing:'+str(row.id)
            if not db.scalar(select(TABLES['alerts']).where(TABLES['alerts'].world_id==scope.world.id,TABLES['alerts'].idempotency_key==key)):
                a=insert(db,scope,'alerts',{'quality_event_id':str(row.id),'metric':row.category,'reason':'Missing observation, not zero demand','rule_version':'quality-v1'},
                         zone_code=row.zone_code,name='Missing reading',category='quality',severity='medium',status='open',idempotency_key=key)
                insert(db,scope,'alert_evidence',row.data,parent_id=a.id,zone_code=row.zone_code,name='Missing source interval')
    return {'contextual_incidents':len(candidates)}


def register(db,scope):
    registry=models(db,scope)
    for item in registry['items']:
        model_id=item['model_id'];cls=TABLES['model_versions']
        if db.scalar(select(cls).where(cls.world_id==scope.world.id,cls.idempotency_key=='starter:'+model_id)):continue
        bundle,sha=trusted_bundle(model_id)
        row=insert(db,scope,'model_versions',{'model_id':model_id,'artifact_sha256':sha,'feature_version':'starter-v1','evaluation':item['evaluation'],
            'serving_policy':item['serving_policy'],'limitations':item['limitations']},name=model_id,status=item['status'],idempotency_key='starter:'+model_id,source_type='experimental_synthetic')
        insert(db,scope,'evaluation_results',item['evaluation'],name=model_id,parent_id=row.id,source_type='synthetic_evaluation')
