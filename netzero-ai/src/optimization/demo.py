import yaml, pandas as pd, os
from src.optimization.model import optimize_dispatch,kpis
cfg=yaml.safe_load(open('configs/config.yaml')); df=pd.read_csv('data/processed/master_hourly.csv').tail(24).reset_index(drop=True); d=optimize_dispatch(df,cfg); print(d.to_string(index=False)); print('\nKPIs:',kpis(df,d))
