from io import BytesIO
from zipfile import ZipFile
import json
import numpy as np
import pandas as pd
import pytest
from src.data import read_noaa, load_upload, validate_series, manifest
from src.forecast import train_and_forecast, forecast_view, base_fit, historical_features, design, interval_width, HORIZONS
from src.reports import export_bundle

@pytest.fixture(scope='module')
def observations():
    return read_noaa('co2','MLO')

@pytest.fixture(scope='module')
def result(observations):
    return train_and_forecast(observations[0],14)

def test_real_data_flags_units_and_provenance(observations):
    f, info=observations
    assert info['unit']=='ppm' and len(f)>15000
    assert f.value.min()>250 and f.value.max()<500
    assert f.date.is_monotonic_increasing and not f.date.duplicated().any()
    assert info['rejected_rows']>0 and len(info['sha256'])==64
    assert 'CC0' in info['license']

@pytest.mark.parametrize('gas,station',[('co2','BRW'),('co2','SMO'),('co2','SPO'),('ch4','MLO')])
def test_available_stations(gas,station):
    f,i=read_noaa(gas,station)
    assert validate_series(f)['count']>=900
    assert i['unit']==('ppm' if gas=='co2' else 'ppb')

def test_future_measurements_cannot_change_historical_features(observations):
    f,_=observations
    s=f.set_index('date').value.asfreq('D').loc['2018':]
    cutoff=pd.Timestamp('2023-10-05')
    base=base_fit(s,cutoff)
    changed=s.copy();changed.loc[changed.index>=cutoff]+=100
    other_base=base_fit(changed,cutoff)
    np.testing.assert_allclose(base.predict([[0,0,0,0,0,0]]),other_base.predict([[0,0,0,0,0,0]]))
    pd.testing.assert_frame_equal(historical_features(s,base).loc[:cutoff-pd.Timedelta(days=1)],
                                  historical_features(changed,other_base).loc[:cutoff-pd.Timedelta(days=1)])
    rows=design(s,base)
    train=rows[rows.target<cutoff]
    assert (train.origin<cutoff).all() and (train.target<cutoff).all()

def test_holdout_cannot_change_model_selection_or_calibration(observations,result):
    changed=observations[0].copy()
    boundary=pd.Timestamp(result['split']['test_start'])
    changed.loc[changed.date>=boundary,'value']+=10
    other=train_and_forecast(changed,14)
    assert other['selected']==result['selected']
    assert other['validation_scores']==pytest.approx(result['validation_scores'])
    np.testing.assert_allclose(other['metrics'].calibration_rmse,result['metrics'].calibration_rmse)
    assert other['metrics'].mae.mean()>result['metrics'].mae.mean()

def test_forecast_dates_and_interval_order(result,observations):
    f=result['forecast']
    assert len(f)==14 and f.date.iloc[0]==observations[0].date.max()+pd.Timedelta(days=1)
    assert (f.lower<=f.predicted).all() and (f.predicted<=f.upper).all()
    assert np.isfinite(f.select_dtypes('number')).all().all()
    metrics=result['metrics']
    assert set(metrics.horizon_days)==set(HORIZONS)
    assert metrics.coverage_90.between(0,1).all()

def test_upload_roundtrip_preserves_daily_values(observations):
    original=observations[0].tail(1500).reset_index(drop=True)
    uploaded=load_upload(original.to_csv(index=False).encode(),'co2')
    pd.testing.assert_frame_equal(original,uploaded)

@pytest.mark.parametrize('payload,message',[
    (b'date,reading\n2020-01-01,420\n','date and value'),
    (b'date,value\nbad,420\n','valid date'),
    (b'date,value\n2020-01-01,-999.99\n','positive'),
    (b'date,value\n2020-01-01,inf\n','finite'),
    (b'date,value\n2020-01-01,420\n2020-01-01,421\n','one daily mean'),
    (b'date,value,unit\n2020-01-01,420,ppb\n','ppm units'),
    (b'date,value\n2020-01-01,420\n','900 valid')])
def test_bad_uploads_rejected(payload,message):
    with pytest.raises(ValueError,match=message):load_upload(payload,'co2')

def test_interval_finite_sample_quantile():
    assert interval_width(np.arange(10))==9

def test_switch_model_and_horizon_reuses_training_and_correct_bands(observations):
    trained=train_and_forecast(observations[0],30)
    view=forecast_view(trained,7,'Persistence')
    assert len(view['forecast'])==7 and view['selected']=='Persistence'
    assert view['forecast'].predicted.eq(observations[0].value.iloc[-1]).all()
    assert view['models'] is trained['models']
    assert view['metrics'] is trained['metrics']
    assert view['forecast'].upper.iloc[-1]-view['forecast'].predicted.iloc[-1]==pytest.approx(trained['interval_widths']['Persistence',7])
    long=forecast_view(trained,30,'Random forest')
    assert len(long['forecast'])==30
    assert long['forecast'].predicted.equals(long['forecast']['Random forest'])
    assert trained['selected']==trained['validation_winner']
    assert len(trained['forecast'])==30

def test_export_has_units_dates_metrics_and_source(observations,result):
    f,i=observations
    with ZipFile(BytesIO(export_bundle(i,result,f))) as z:
        assert {'forecast.csv','holdout_metrics.csv','backtest.csv','observations.csv','provenance.json','report.html'}==set(z.namelist())
        meta=json.loads(z.read('provenance.json'))
        assert meta['unit']=='ppm' and meta['source'].startswith('https://gml.noaa.gov/')
        out=pd.read_csv(BytesIO(z.read('forecast.csv')))
        assert out.unit.eq('ppm').all() and out.forecast_origin.eq('2025-12-30').all()
        assert b'90%' in z.read('report.html')

def test_uploaded_location_preserved_in_report(observations,result):
    f,i=observations
    local={**i,'name':'My sensor','latitude':18.5,'longitude':73.9}
    with ZipFile(BytesIO(export_bundle(local,result,f))) as z:
        meta=json.loads(z.read('provenance.json'))
        assert meta['latitude']==18.5 and meta['longitude']==73.9
