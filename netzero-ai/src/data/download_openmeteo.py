import os, requests, pandas as pd
URL='https://archive-api.open-meteo.com/v1/archive'
params={'latitude':23.0225,'longitude':72.5714,'start_date':'2018-01-01','end_date':'2022-12-31','hourly':'temperature_2m,relative_humidity_2m,pressure_msl,cloud_cover,wind_speed_100m,wind_direction_100m,shortwave_radiation','wind_speed_unit':'ms','timezone':'Asia/Kolkata'}
r=requests.get(URL,params=params,timeout=120); r.raise_for_status(); j=r.json()
os.makedirs('data/raw',exist_ok=True)
df=pd.DataFrame(j['hourly']); df.to_csv('data/raw/openmeteo.csv',index=False)
print('saved data/raw/openmeteo.csv',len(df),'rows')
