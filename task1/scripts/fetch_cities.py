"""Extract real CT2026 boundary-layer CO2 for two Indian city grid cells.

HTTP byte ranges read HDF5 metadata and the small pbl_co2 chunk, rather than
downloading the ~100 MB global atmosphere file. No spatial interpolation.
Resumable: each daily extraction is retained before building the city CSVs.
"""
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import argparse
import io
import json
import time
import h5py
import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://gml.noaa.gov/aftp/products/carbontracker/co2/CT2026/molefractions/co2_total/'
CITIES = {'NOIDA': {'name': 'Noida', 'latitude': 28.5355, 'longitude': 77.3910},
          'AHMEDABAD': {'name': 'Ahmedabad', 'latitude': 23.0225, 'longitude': 72.5714}}

class RangeFile(io.RawIOBase):
    def __init__(self, url):
        self.url, self.position, self.blocks = url, 0, []
        self.session = requests.Session()
        response = self.session.get(url, headers={'Range': 'bytes=0-65535'}, timeout=40)
        response.raise_for_status()
        if response.status_code != 206:
            raise ValueError('Server must support byte ranges; refusing a global download.')
        self.size = int(response.headers['Content-Range'].split('/')[-1])
        self.blocks.append((0, response.content))
        self.bytes_read = len(response.content)
    def readable(self): return True
    def seekable(self): return True
    def tell(self): return self.position
    def seek(self, offset, whence=0):
        self.position = offset if whence == 0 else self.position + offset if whence == 1 else self.size + offset
        return self.position
    def read(self, length=-1):
        length = self.size-self.position if length < 0 else min(length,self.size-self.position)
        if length <= 0: return b''
        start, end = self.position, self.position + length
        for offset, content in self.blocks:
            if offset <= start and end <= offset+len(content):
                self.position = end
                return content[start-offset:end-offset]
        # Cache a small window for neighboring HDF5 metadata reads.
        stop = min(self.size, max(end, start+16384))
        r = self.session.get(self.url, headers={'Range': f'bytes={start}-{stop-1}'}, timeout=40)
        r.raise_for_status()
        if r.status_code != 206 or len(r.content) != stop-start:
            raise ValueError('Invalid byte-range response.')
        self.blocks.append((start,r.content)); self.bytes_read += len(r.content)
        self.position = end
        return r.content[:length]
    def readinto(self, buffer):
        content=self.read(len(buffer)); buffer[:len(content)]=content; return len(content)
    def close(self):
        self.session.close(); super().close()

def extract(date):
    cache=ROOT/'data/cities/raw'; cache.mkdir(parents=True,exist_ok=True)
    path=cache/f'{date}.json'
    if path.exists(): return json.loads(path.read_text(encoding="utf-8"))
    url=BASE+f'CT2026.molefrac_glb3x2_{date}.nc'
    for attempt in range(3):
        try:
            with RangeFile(url) as remote, h5py.File(remote,'r') as h:
                values=h['pbl_co2'][:]
                lat,lon=h['latitude'][:],h['longitude'][:]
                unit=h['pbl_co2'].attrs['units'].decode()
                if values.shape!=(8,90,120) or unit!='micromol mol-1':
                    raise ValueError('Unexpected NOAA layout/units.')
                record={'date':date,'url':url,'retrieved_at':datetime.now(timezone.utc).isoformat(),
                        'variable':'pbl_co2','unit':'ppm','downloaded_bytes':remote.bytes_read,'cities':{}}
                for code,city in CITIES.items():
                    i=int(np.argmin(abs(lat-city['latitude']))); j=int(np.argmin(abs(lon-city['longitude'])))
                    v=values[:,i,j].astype(float)
                    if not np.isfinite(v).all() or (v<=0).any(): raise ValueError('Invalid concentration.')
                    record['cities'][code]={'values_3hourly':v.tolist(),'value':float(v.mean()),
                        'grid_latitude':float(lat[i]),'grid_longitude':float(lon[j]),
                        'grid_bounds':[float(lon[j]-1.5),float(lat[i]-1),float(lon[j]+1.5),float(lat[i]+1)]}
                path.write_text(json.dumps(record,indent=2)+'\n')
                return record
        except (requests.RequestException,OSError,ValueError):
            if attempt==2: raise
            time.sleep(attempt+1)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--start',default='2022-01-01')
    parser.add_argument('--end',default='2025-12-30');parser.add_argument('--workers',type=int,default=6)
    args=parser.parse_args();dates=pd.date_range(args.start,args.end).strftime('%Y-%m-%d').tolist()
    records=[]; failures=[]
    # h5py serializes file operations within a process. Processes let independent
    # HTTP reads run concurrently; threads would hold its global lock during I/O.
    with ProcessPoolExecutor(max_workers=min(8,max(1,args.workers))) as pool:
        pending={pool.submit(extract,date):date for date in dates}
        for future in as_completed(pending):
            try: records.append(future.result())
            except Exception as exc: failures.append({'date':pending[future],'error':str(exc)})
            if (len(records)+len(failures))%50==0: print(f'{len(records)}/{len(dates)} extracted; {len(failures)} failed',flush=True)
    records.sort(key=lambda r:r['date']);manifest=[]
    for code,city in CITIES.items():
        if not records: raise RuntimeError('No source files downloaded.')
        frame=pd.DataFrame([{'date':r['date'],'value':r['cities'][code]['value']} for r in records])
        file=ROOT/'data/cities'/f'co2_{code.lower()}.csv';frame.to_csv(file,index=False)
        grid=records[-1]['cities'][code]
        manifest.append({**city,'station':code,'gas':'co2','unit':'ppm','file':str(file.relative_to(ROOT)),
            'sha256':sha256(file.read_bytes()).hexdigest(),'source_rows':len(frame),'rejected_rows':len(failures),
            'origin':'NOAA CarbonTracker CT2026 · regional model estimates','variable':'pbl_co2',
            'scope':'Daily pressure-averaged boundary-layer CO₂ in a 3° longitude × 2° latitude grid cell. Not a city sensor or street-level measurement.',
            'grid_latitude':grid['grid_latitude'],'grid_longitude':grid['grid_longitude'],'grid_bounds':grid['grid_bounds'],
            'url':BASE,'retrieved_at':datetime.now(timezone.utc).isoformat(),'release':'CT2026',
            'citation':'Jacobson et al. (2026), CarbonTracker CT2026, doi:10.25925/hqp0-rk68.',
            'license':'NOAA CarbonTracker usage policy: unrestricted non-commercial use with attribution. See https://gml.noaa.gov/ccgg/carbontracker/CT2026/citation.php',
            'last':str(frame.date.iloc[-1]),'eligible':len(frame)>=900})
    (ROOT/'data/cities/manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (ROOT/'data/cities/download_failures.json').write_text(json.dumps(failures,indent=2)+'\n')
    print(f'Saved {len(records)} real daily estimates per city; {len(failures)} failures.',flush=True)

if __name__=='__main__':main()
