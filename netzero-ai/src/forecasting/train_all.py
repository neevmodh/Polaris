import os, json, joblib, numpy as np, pandas as pd
from xgboost import XGBRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error
from src.features.features import make_features

DATA='data/processed/master_hourly.csv'; os.makedirs('models',exist_ok=True)

def smape(y,p): return float(np.mean(2*np.abs(p-y)/(np.abs(y)+np.abs(p)+1e-6))*100)

def train(target):
    df=pd.read_csv(DATA,parse_dates=['timestamp'])
    if target not in df: raise ValueError(target)
    d,cols=make_features(df,target)
    n=len(d); a=int(.70*n); b=int(.85*n)
    tr,va,te=d.iloc[:a],d.iloc[a:b],d.iloc[b:]
    model=XGBRegressor(n_estimators=700,max_depth=7,learning_rate=.04,subsample=.85,colsample_bytree=.9,objective='reg:squarederror',random_state=42,n_jobs=4)
    model.fit(tr[cols],tr[target],eval_set=[(va[cols],va[target])],verbose=False)
    pred=model.predict(te[cols]); persistence=te[f'{target}_lag_1'].values
    metrics={'MAE':float(mean_absolute_error(te[target],pred)),'RMSE':float(mean_squared_error(te[target],pred)**.5),'sMAPE_pct':smape(te[target].values,pred),'baseline_MAE':float(mean_absolute_error(te[target],persistence))}
    path=f'models/{target}_xgb.joblib'; joblib.dump({'model':model,'features':cols,'target':target},path)
    return metrics

if __name__=='__main__':
    allm={t:train(t) for t in ['solar_available_kw','wind_available_kw','load_kw']}
    json.dump(allm,open('models/metrics.json','w'),indent=2)
    print(json.dumps(allm,indent=2))
