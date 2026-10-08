"""Verified geographic extractions; no substitution of distant station data."""
from hashlib import sha256
import json
import pandas as pd
from .data import ROOT

def city_catalog():
    return json.loads((ROOT/'data/cities/manifest.json').read_text(encoding="utf-8"))

def read_city(code):
    info=next(e for e in city_catalog() if e['station']==code)
    path=ROOT/info['file']
    if sha256(path.read_bytes()).hexdigest()!=info['sha256']:
        raise ValueError('City data checksum failed. Run scripts/fetch_cities.py to regenerate the verified extraction.')
    return pd.read_csv(path,parse_dates=['date']),info

def anomalies(frame, window=90, sigma=2.5):
    """Flag high historical values relative to preceding observations only."""
    out=frame.copy()
    prior=out.value.shift(1)
    out['prior_mean']=prior.rolling(window,min_periods=60).mean()
    out['prior_std']=prior.rolling(window,min_periods=60).std()
    out['review_level']=out.prior_mean+sigma*out.prior_std
    out['flag']=out.value>out.review_level
    return out
