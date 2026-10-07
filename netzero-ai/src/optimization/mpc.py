import pandas as pd
from src.optimization.model import optimize_dispatch

def rolling_mpc(forecast_df,cfg,step_hours=1,horizon=24):
    """Receding-horizon controller: solve a future window, execute first step, then re-solve."""
    f=forecast_df.reset_index(drop=True); executed=[]; state=dict(cfg['battery'])
    for start in range(0,len(f),step_hours):
        window=f.iloc[start:min(start+horizon,len(f))].copy()
        c={**cfg,'battery':dict(state)}
        d=optimize_dispatch(window,c); first=d.iloc[:step_hours].copy(); executed.append(first)
        state['soc_initial']=float(first.iloc[-1]['soc'])
    return pd.concat(executed,ignore_index=True)
