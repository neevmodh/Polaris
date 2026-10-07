import yaml, pandas as pd
from src.optimization.model import optimize_dispatch

def test_energy_balance():
    cfg=yaml.safe_load(open('configs/config.yaml'))
    f=pd.DataFrame({'timestamp':pd.date_range('2025-01-01',periods=24,freq='h'),'solar_available_kw':[500]*24,'wind_available_kw':[200]*24,'load_kw':[600]*24,'grid_price_rs_kwh':[8]*24,'grid_carbon_kgco2_kwh':[.7]*24})
    d=optimize_dispatch(f,cfg)
    # Unserved energy is a supply-side slack: it stands in for power the system could not deliver.
    lhs=d.solar_kw+d.wind_kw+d.grid_import_kw+d.discharge_kw+d.unserved_kw
    rhs=f.load_kw+d.charge_kw+d.grid_export_kw
    assert (abs(lhs-rhs)<1e-5).all()
    assert d.soc.between(cfg['battery']['soc_min']-1e-6,cfg['battery']['soc_max']+1e-6).all()
