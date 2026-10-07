import os, requests, pandas as pd
from io import StringIO
URL='https://re.jrc.ec.europa.eu/api/v5_3/seriescalc'
params={'lat':23.0225,'lon':72.5714,'startyear':2018,'endyear':2022,'pvcalculation':1,'peakpower':1000,'pvtechchoice':'crystSi','mountingplace':'free','angle':23,'aspect':0,'loss':14,'outputformat':'csv','localtime':1}
os.makedirs('data/raw',exist_ok=True)
r=requests.get(URL,params=params,timeout=120); r.raise_for_status()
open('data/raw/pvgis.csv','wb').write(r.content)
print('saved data/raw/pvgis.csv',len(r.content),'bytes')
