import pandas as pd, numpy as np
from src.optimization.model import optimize_dispatch,kpis

SCENARIOS=('cloud_event','wind_drop','load_spike','battery_low','grid_outage')

def apply_scenario(df,name):
    x=df.copy()
    if name=='cloud_event': x.loc[6:10,'solar_available_kw']*=0.20
    elif name=='wind_drop': x.loc[8:14,'wind_available_kw']*=0.25
    elif name=='load_spike': x.loc[17:21,'load_kw']*=1.45
    elif name=='battery_low': x.attrs['battery_soc_override']=0.22
    elif name=='grid_outage': x.attrs['grid_outage']=True
    else: raise ValueError('unknown scenario')
    return x

def run_scenario(df,cfg,name):
    x=apply_scenario(df,name); c={**cfg,'battery':dict(cfg['battery'])}
    if 'battery_soc_override' in x.attrs: c['battery']['soc_initial']=x.attrs['battery_soc_override']
    
    if x.attrs.get('grid_outage'):
        c['grid']=dict(c['grid']); c['grid']['import_kw']=0; c['grid']['export_kw']=0
    d=optimize_dispatch(x,c); return {'scenario':name,'kpis':kpis(x,d),'method':d.attrs.get('method'),'fallback_reason':d.attrs.get('fallback_reason'),'dispatch':d.to_dict(orient='records')}
