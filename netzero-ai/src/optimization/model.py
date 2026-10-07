import numpy as np
import pandas as pd
try:
    import pyomo.environ as pyo
except Exception:
    pyo=None

def optimize_dispatch(forecast, cfg):
    """24h LP/MILP dispatch. Uses HiGHS when available; otherwise rule-based fallback."""
    f=forecast.reset_index(drop=True).copy(); T=len(f); dt=1.0
    batt=cfg['battery']; grid=cfg['grid']; w=cfg['optimization']['weights']
    if pyo is None:
        return greedy_dispatch(f,cfg,'pyomo is not installed')
    m=pyo.ConcreteModel(); m.T=pyo.RangeSet(0,T-1)
    for name in ['solar','wind','charge','discharge','grid_import','grid_export','curtail','unserved']:
        setattr(m,name,pyo.Var(m.T,domain=pyo.NonNegativeReals))
    m.soc=pyo.Var(pyo.RangeSet(0,T),bounds=(batt['soc_min'],batt['soc_max']))
    m.soc[0]=batt['soc_initial']
    def balance(m,t): return m.solar[t]+m.wind[t]+m.grid_import[t]+m.discharge[t]+m.unserved[t] == f.loc[t,'load_kw']+m.charge[t]+m.grid_export[t]
    m.balance=pyo.Constraint(m.T,rule=balance)
    m.unserved_cap=pyo.Constraint(m.T,rule=lambda m,t:m.unserved[t]<=max(0,float(f.loc[t,'load_kw'])))
    m.solar_cap=pyo.Constraint(m.T,rule=lambda m,t:m.solar[t]<=max(0,float(f.loc[t,'solar_available_kw'])))
    m.wind_cap=pyo.Constraint(m.T,rule=lambda m,t:m.wind[t]<=max(0,float(f.loc[t,'wind_available_kw'])))
    m.charge_cap=pyo.Constraint(m.T,rule=lambda m,t:m.charge[t]<=batt['charge_kw'])
    m.discharge_cap=pyo.Constraint(m.T,rule=lambda m,t:m.discharge[t]<=batt['discharge_kw'])
    m.grid_cap=pyo.Constraint(m.T,rule=lambda m,t:m.grid_import[t]<=grid['import_kw'])
    m.export_cap=pyo.Constraint(m.T,rule=lambda m,t:m.grid_export[t]<=grid['export_kw'])
    m.soc_dyn=pyo.Constraint(m.T,rule=lambda m,t:m.soc[t+1]==m.soc[t]+batt['eta_charge']*m.charge[t]/batt['capacity_kwh']-m.discharge[t]/batt['eta_discharge']/batt['capacity_kwh'])
    # Reserve SOC at horizon end.
    # Soft reserve: a hard bound is infeasible when the battery starts low and the grid is out; the shortfall is priced instead.
    m.res_short=pyo.Var(domain=pyo.NonNegativeReals)
    m.end_reserve=pyo.Constraint(expr=m.soc[T]+m.res_short>=max(batt['soc_min'],cfg['optimization']['reserve_soc']))
    m.obj=pyo.Objective(expr=sum(w['cost']*f.loc[t,'grid_price_rs_kwh']*m.grid_import[t]+w['carbon']*f.loc[t,'grid_carbon_kgco2_kwh']*m.grid_import[t]+w['battery']*(m.charge[t]+m.discharge[t])+w['curtailment']*(max(0,float(f.loc[t,'solar_available_kw']))+max(0,float(f.loc[t,'wind_available_kw']))-m.solar[t]-m.wind[t])+w['unserved']*m.unserved[t]-0.1*f.loc[t,'grid_price_rs_kwh']*m.grid_export[t] for t in m.T)+0.5*w['unserved']*batt['capacity_kwh']*m.res_short,sense=pyo.minimize)
    solver=pyo.SolverFactory('highs')
    if not solver.available(exception_flag=False): return greedy_dispatch(f,cfg,'the HiGHS solver is unavailable')
    try: res=solver.solve(m,tee=False)
    except Exception: return greedy_dispatch(f,cfg,'no feasible optimal plan exists for these limits')   # e.g. a grid outage the renewables cannot cover
    if str(res.solver.termination_condition).lower() not in ('optimal','locallyoptimal','feasible'): return greedy_dispatch(f,cfg,'the solver did not reach an optimal solution')
    out=[]
    for t in range(T):
        out.append({'timestamp':f.loc[t,'timestamp'],'solar_kw':pyo.value(m.solar[t]),'wind_kw':pyo.value(m.wind[t]),'charge_kw':pyo.value(m.charge[t]),'discharge_kw':pyo.value(m.discharge[t]),'grid_import_kw':pyo.value(m.grid_import[t]),'grid_export_kw':pyo.value(m.grid_export[t]),'curtail_kw':max(0.0,max(0,float(f.loc[t,'solar_available_kw']))+max(0,float(f.loc[t,'wind_available_kw']))-pyo.value(m.solar[t])-pyo.value(m.wind[t])),'unserved_kw':pyo.value(m.unserved[t]),'soc':pyo.value(m.soc[t+1])})
    r=pd.DataFrame(out); r.attrs['method']='optimised'; r.attrs['fallback_reason']=None
    return r

def greedy_dispatch(f,cfg,reason='requested directly'):
    b=cfg['battery']; g=cfg['grid']; soc=b['soc_initial']; cap=b['capacity_kwh']; out=[]
    for _,r in f.iterrows():
        solar=max(0,float(r.solar_available_kw)); wind=max(0,float(r.wind_available_kw)); load=max(0,float(r.load_kw)); charge=dis=imp=exp=curt=un=0
        renewable=solar+wind
        if renewable>=load:
            used=load; surplus=renewable-load; charge=min(b['charge_kw'],surplus,max(0,(b['soc_max']-soc)*cap/b['eta_charge'])); soc+=b['eta_charge']*charge/cap; exp=min(g['export_kw'],surplus-charge); curt=max(0,surplus-charge-exp)
        else:
            deficit=load-renewable; dis=min(b['discharge_kw'],deficit,max(0,(soc-b['soc_min'])*cap*b['eta_discharge'])); soc-=dis/(b['eta_discharge']*cap); imp=min(g['import_kw'],deficit-dis); un=max(0,deficit-dis-imp)
        # Fill demand, charging and export with solar first and wind next; whatever neither serves is spilled.
        need=load+charge+exp-dis-imp-un
        s_used=min(solar,max(0,need)); w_used=min(wind,max(0,need-s_used)); curt=(solar+wind)-s_used-w_used
        out.append({'timestamp':r.timestamp,'solar_kw':s_used,'wind_kw':w_used,'charge_kw':charge,'discharge_kw':dis,
                    'grid_import_kw':imp,'grid_export_kw':exp,'curtail_kw':curt,'unserved_kw':un,'soc':soc})
    r=pd.DataFrame(out); r.attrs['method']='rule-based fallback'; r.attrs['fallback_reason']=reason
    return r

def kpis(f,dispatch):
    d=dispatch; load=f['load_kw'].sum(); renewable=(d.solar_kw+d.wind_kw).sum(); offered=float((f.solar_available_kw+f.wind_available_kw).sum()); spilled=max(0.0,offered-float(renewable)); imp=d.grid_import_kw.sum(); exp=d.grid_export_kw.sum(); un=d.unserved_kw.sum(); curt=d.curtail_kw.sum(); cost=float((d.grid_import_kw*f.grid_price_rs_kwh).sum()); co2=float((d.grid_import_kw*f.grid_carbon_kgco2_kwh).sum());
    return {'load_kwh':float(load),'renewable_used_kwh':float(renewable),'renewable_offered_kwh':offered,'renewable_spilled_kwh':spilled,'renewable_utilization_pct':float(100*renewable/(offered+1e-9)),'grid_import_kwh':float(imp),'grid_dependency_pct':float(100*imp/(load+1e-9)),'grid_export_kwh':float(exp),'curtailment_kwh':float(curt),'unserved_kwh':float(un),'grid_cost_rs':cost,'grid_co2_kg':co2,'critical_load_coverage_pct':float(100*(1-un/(load+1e-9)))}
