import os, glob, pandas as pd, numpy as np

def first_existing(patterns):
    for p in patterns:
        hits=glob.glob(p,recursive=True)
        if hits: return hits[0]
    return None

def build():
    pvg=first_existing(['data/raw/pvgis.csv'])
    om=first_existing(['data/raw/openmeteo.csv'])
    uci=first_existing(['data/raw/uci/**/*household_power_consumption.txt'])
    if not (pvg and om and uci):
        raise FileNotFoundError('Run download_pvgis, download_openmeteo and download_uci first, or use generate_demo_data.')
    # PVGIS has metadata/header rows; detect the actual header containing time.
    raw=open(pvg,encoding='utf-8',errors='ignore').read().splitlines()
    header_idx=next(i for i,x in enumerate(raw) if x.lower().startswith('time'))
    pv=pd.read_csv(pvg,skiprows=header_idx)
    pv.columns=[c.strip().split('[')[0].strip() for c in pv.columns]
    pv=pv.rename(columns={'time':'timestamp','P':'solar_available_kw','G(i)':'shortwave_radiation_wm2','T2m':'temperature_c','WS10m':'wind_speed_10m_ms'})
    pv['solar_available_kw']=pd.to_numeric(pv['solar_available_kw'],errors='coerce')/1000
    pv['timestamp']=pd.to_datetime(pv['timestamp'],errors='coerce')
    omdf=pd.read_csv(om); omdf['timestamp']=pd.to_datetime(omdf['time']); omdf=omdf.drop(columns=['time'])
    omdf=omdf.rename(columns={'temperature_2m':'temperature_c','relative_humidity_2m':'humidity_pct','pressure_msl':'pressure_msl_hpa','cloud_cover':'cloud_cover_pct','wind_speed_100m':'wind_speed_100m_ms','wind_direction_100m':'wind_direction_100m_deg','shortwave_radiation':'shortwave_radiation_wm2'})
    for c in ['temperature_c','humidity_pct','pressure_msl_hpa','cloud_cover_pct','wind_speed_100m_ms','wind_direction_100m_deg','shortwave_radiation_wm2']: omdf[c]=pd.to_numeric(omdf[c],errors='coerce')
    u=pd.read_csv(uci,sep=';',na_values=['?'],low_memory=False)
    u['timestamp']=pd.to_datetime(u['Date'].astype(str)+' '+u['Time'].astype(str),dayfirst=False,errors='coerce')
    u['Global_active_power']=pd.to_numeric(u['Global_active_power'],errors='coerce')
    u=u.dropna(subset=['timestamp']).set_index('timestamp')
    load=u['Global_active_power'].resample('h').mean()*1000 # kW? dataset is kW, *1000 -> W then normalize below
    load=load.rename('raw_load_w').reset_index(); load['load_kw']=load['raw_load_w']/1000
    base=pv.merge(omdf,on='timestamp',how='outer',suffixes=('','_om')).merge(load[['timestamp','load_kw']],on='timestamp',how='left')
    # Prefer Open-Meteo weather where available.
    for c in ['temperature_c','shortwave_radiation_wm2']:
        omc=c+'_om';
        if omc in base: base[c]=base[omc].combine_first(base[c]); base.drop(columns=[omc],inplace=True)
    base=base.sort_values('timestamp').set_index('timestamp').resample('h').mean(numeric_only=True).interpolate(limit=3).reset_index()
    # Scale UCI household profile to 850 kW peak microgrid demand.
    scale=850/base['load_kw'].quantile(.99); base['load_kw']=(base['load_kw']*scale).clip(280,850)
    base['wind_available_kw']=500*np.clip((base['wind_speed_100m_ms']-3)/9,0,1)
    base['grid_price_rs_kwh']=np.where(base.timestamp.dt.hour.between(18,22),11,np.where(base.timestamp.dt.hour.between(10,16),5.5,7.5))
    base['grid_carbon_kgco2_kwh']=np.where(base.timestamp.dt.hour.between(18,22),.9,.65)
    os.makedirs('data/processed',exist_ok=True); base.to_csv('data/processed/master_hourly.csv',index=False)
    print('wrote data/processed/master_hourly.csv',len(base))
if __name__=='__main__': build()
