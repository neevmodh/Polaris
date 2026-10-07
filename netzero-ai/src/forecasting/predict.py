import os, joblib, pandas as pd
from src.features.features import make_features
MODEL_MAP={'solar':'solar_available_kw','wind':'wind_available_kw','load':'load_kw'}

def forecast(kind,history,horizon=24):
    pack=joblib.load(f'models/{MODEL_MAP[kind]}_xgb.joblib'); target=pack['target']; model=pack['model']; cols=pack['features']
    hist=history.copy(); hist['timestamp']=pd.to_datetime(hist['timestamp']); hist=hist.sort_values('timestamp').reset_index(drop=True)
    rows=[]
    for _ in range(horizon):
        last=hist.iloc[-1].copy(); row=last.copy(); row['timestamp']=last['timestamp']+pd.Timedelta(hours=1)
        # Exogenous weather is persisted in this local implementation; replace with live forecast weather in production.
        for c in ['solar_available_kw','wind_available_kw','load_kw']:
            row[c]=hist[c].iloc[-1]
        fx,_=make_features(pd.concat([hist,pd.DataFrame([row])],ignore_index=True),target)
        pred=float(model.predict(fx.iloc[[-1]][cols])[0]) if len(fx) else float(last[target])
        row[target]=max(0,pred)
        hist=pd.concat([hist,pd.DataFrame([row])],ignore_index=True)
        rows.append(row)
    return pd.DataFrame(rows)[['timestamp','solar_available_kw','wind_available_kw','load_kw']]

def forecast_all(history,horizon=24):
    out=None
    for kind,col in MODEL_MAP.items():
        p=forecast(kind,history,horizon)[['timestamp',col]]      # each model owns only its own target column
        out=p if out is None else out.merge(p,on='timestamp')
    return out[['timestamp','solar_available_kw','wind_available_kw','load_kw']]
