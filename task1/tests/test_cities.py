from pathlib import Path
import json
import numpy as np
import pandas as pd
import pytest
from src.cities import city_catalog, read_city, anomalies
from src.data import validate_series
from src.forecast import train_and_forecast, MODELS
from src.reports import metadata

ROOT=Path(__file__).resolve().parents[1]

@pytest.mark.parametrize('code',['NOIDA','AHMEDABAD'])
def test_city_extraction_matches_raw_native_cell(code):
    frame,info=read_city(code)
    assert validate_series(frame)['count']>=900
    assert info['variable']=='pbl_co2' and info['unit']=='ppm'
    west,south,east,north=info['grid_bounds']
    assert west<=info['longitude']<=east and south<=info['latitude']<=north
    assert east-west==3 and north-south==2
    for row in frame.iloc[[0,len(frame)//2,-1]].itertuples():
        raw=json.loads((ROOT/'data/cities/raw'/f'{row.date.date()}.json').read_text(encoding="utf-8"))
        native=raw['cities'][code]
        assert raw['url'].endswith(f'{row.date.date()}.nc')
        assert len(native['values_3hourly'])==8
        assert row.value==pytest.approx(np.mean(native['values_3hourly']))
        assert native['grid_bounds']==info['grid_bounds']

def test_city_series_differ_and_use_same_calendar():
    noida,_=read_city('NOIDA');ahmedabad,_=read_city('AHMEDABAD')
    assert noida.date.equals(ahmedabad.date)
    assert not np.allclose(noida.value,ahmedabad.value)
    assert set(e['station'] for e in city_catalog())=={'NOIDA','AHMEDABAD'}

def test_anomaly_threshold_has_no_future_or_current_leakage():
    frame=pd.DataFrame({'date':pd.date_range('2020-01-01',periods=150),'value':np.arange(150.)})
    original=anomalies(frame)
    changed=frame.copy();changed.loc[100:,'value']+=10000
    other=anomalies(changed)
    pd.testing.assert_series_equal(original.review_level.iloc[:101],other.review_level.iloc[:101])
    assert original.review_level.iloc[:60].isna().all()

def test_real_city_models_and_export_scope():
    frame,info=read_city('NOIDA');result=train_and_forecast(frame,14)
    assert result['selected'] in MODELS[:3]
    assert result['forecast'].date.min()==frame.date.max()+pd.Timedelta(days=1)
    assert np.isfinite(result['forecast'].select_dtypes('number')).all().all()
    assert (result['backtest'].origin<result['backtest'].target).all()
    assert (result['backtest'].origin>=pd.Timestamp(result['split']['test_start'])).all()
    meta=metadata(info,result)
    assert meta['grid_bounds']==info['grid_bounds'] and meta['source_variable']=='pbl_co2'
    assert '3°' in meta['scope'] and 'not a city sensor' in meta['scope'].lower()
