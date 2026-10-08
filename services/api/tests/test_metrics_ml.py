import numpy as np
import pandas as pd
from pathlib import Path
from sqlalchemy import select,func
from app.core.models import Observation
from app.domains.metrics import overview,series
from app.analytics.service import trusted_bundle,infer,frame
from app.analytics.starter import FEATURES,features,chronological_masks
from app.core.settings import settings
from test_data_security import base_scope,principal

def test_api_aggregates_equal_sql(base_scope):
    db,scope=base_scope
    o=overview(db,scope)
    end=pd.Timestamp(o['end']);start=pd.Timestamp(o['start'])
    value=db.scalar(select(func.sum(Observation.value)).where(Observation.world_id==scope.world.id,Observation.metric=='energy.interval_kwh',Observation.interval_end>start,Observation.interval_end<=end))
    assert o['metrics']['energy.interval_kwh']['value']==value
    s=series(db,scope,'energy.interval_kwh',start.to_pydatetime(),end.to_pydatetime(),limit=200)
    assert abs(sum(x['value'] or 0 for x in s['items'])-value)<1e-8
    assert s['unit']=='kWh' and s['semantics']=='interval'

def test_feature_leakage_and_purge():
    data=pd.read_csv(Path(settings().starter_path)/'data/observations.csv',parse_dates=['observed_at']).groupby('zone_id').head(24*35)
    original=features(data,24)
    cutoff=pd.Timestamp('2025-01-20T00:00:00Z')
    changed=data.copy();changed.loc[changed.observed_at>cutoff,['energy_kwh','water_l','temperature_c','occupied_beds']]=9999
    later=features(changed,24)
    pd.testing.assert_frame_equal(original.loc[original.origin_time<=cutoff,FEATURES],later.loc[later.origin_time<=cutoff,FEATURES])
    tr,va,te,info=chronological_masks(original,data.observed_at)
    assert original.loc[tr,'target_time'].max()<original.loc[va,'origin_time'].min()
    assert original.loc[va,'target_time'].max()<original.loc[te,'origin_time'].min()

def test_trusted_reload_predictions_and_horizons(base_scope):
    db,scope=base_scope
    data=frame(db,scope)
    f=features(data,1).tail(4)
    a,sha=trusted_bundle('energy_kwh_1h');b,sha2=trusted_bundle('energy_kwh_1h')
    assert sha==sha2 and a['feature_columns']==FEATURES
    np.testing.assert_allclose(a['model'].predict(f[FEATURES]),b['model'].predict(f[FEATURES]),rtol=0,atol=0)
    result=infer(db,scope)
    assert result['status']=='completed'
    with __import__('pytest').raises(ValueError):features(data,12)
    with __import__('pytest').raises(ValueError):trusted_bundle('../../untrusted')
