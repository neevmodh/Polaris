import numpy as np, pandas as pd
BASE=['temperature_c','humidity_pct','cloud_cover_pct','pressure_msl_hpa','wind_speed_100m_ms','wind_direction_100m_deg','shortwave_radiation_wm2']
LAGS=[1,2,3,6,12,24,48,168]

def add_time_features(df):
    df=df.copy(); t=pd.to_datetime(df['timestamp'])
    df['hour']=t.dt.hour; df['day_of_week']=t.dt.dayofweek; df['month']=t.dt.month; df['day_of_year']=t.dt.dayofyear; df['is_weekend']=(t.dt.dayofweek>=5).astype(int)
    df['hour_sin']=np.sin(2*np.pi*df.hour/24); df['hour_cos']=np.cos(2*np.pi*df.hour/24)
    df['doy_sin']=np.sin(2*np.pi*df.day_of_year/365.25); df['doy_cos']=np.cos(2*np.pi*df.day_of_year/365.25)
    return df

def make_features(df,target,lags=LAGS):
    x=add_time_features(df)
    for lag in lags: x[f'{target}_lag_{lag}']=x[target].shift(lag)
    for w in [3,6,24,168]:
        x[f'{target}_roll_mean_{w}']=x[target].shift(1).rolling(w).mean()
        x[f'{target}_roll_std_{w}']=x[target].shift(1).rolling(w).std()
    cols=[c for c in BASE if c in x.columns]+[c for c in x.columns if c.startswith(target+'_lag_') or c.startswith(target+'_roll_')]+['hour','day_of_week','month','day_of_year','is_weekend','hour_sin','hour_cos','doy_sin','doy_cos']
    return x.dropna(subset=cols+[target]),cols
