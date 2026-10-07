import os
import numpy as np
import pandas as pd

OUT='data/processed/master_hourly.csv'
os.makedirs(os.path.dirname(OUT), exist_ok=True)
rng=np.random.default_rng(42)
t=pd.date_range('2024-01-01', periods=24*180, freq='h', tz='Asia/Kolkata')
h=t.hour.values
# Synthetic Ahmedabad-like weather
season=np.sin(2*np.pi*(t.dayofyear.values-80)/365)
solar_shape=np.maximum(0, np.sin(np.pi*(h-6)/12))
cloud=np.clip(35+25*np.sin(2*np.pi*t.dayofyear.values/17)+rng.normal(0,15,len(t)),0,100)
temp=28+8*season+6*np.maximum(0,np.sin(np.pi*(h-6)/12))+rng.normal(0,1.8,len(t))
humidity=np.clip(65-0.8*(temp-25)+rng.normal(0,6,len(t)),20,95)
pressure=1010-3*season+rng.normal(0,2,len(t))
wind=np.clip(5+2*np.sin(2*np.pi*(h+3)/24)+1.5*season+rng.normal(0,1.5,len(t)),0,18)
# available generation
solar=1000*solar_shape*(1-cloud/140)*np.clip(1-0.004*(temp-25),0.75,1.05)+rng.normal(0,15,len(t))
solar=np.clip(solar,0,1000)
wind_kw=500*np.clip((wind-3)/(12-3),0,1)
wind_kw=np.where(wind>=25,0,wind_kw)
# demand with morning/evening peaks
load=420+70*((h>=7)&(h<=10))+150*((h>=18)&(h<=23))+35*np.sin(2*np.pi*t.dayofweek.values/7)+20*(temp>34)+rng.normal(0,25,len(t))
load=np.clip(load,280,850)
price=np.where((h>=18)&(h<=22),11,np.where((h>=10)&(h<=16),5.5,7.5))
carbon=np.where((h>=18)&(h<=22),0.9,0.65)
df=pd.DataFrame({'timestamp':t,'temperature_c':temp,'humidity_pct':humidity,'cloud_cover_pct':cloud,'pressure_msl_hpa':pressure,'wind_speed_100m_ms':wind,'wind_direction_100m_deg':(180+50*np.sin(h/24*2*np.pi)+rng.normal(0,20,len(t)))%360,'shortwave_radiation_wm2':1000*solar_shape*(1-cloud/100),'solar_available_kw':solar,'wind_available_kw':wind_kw,'load_kw':load,'grid_price_rs_kwh':price,'grid_carbon_kgco2_kwh':carbon})
df.to_csv(OUT,index=False)
print(f'wrote {OUT}: {len(df)} rows')
