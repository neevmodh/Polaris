import json, os, yaml, pandas as pd, numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from src import llm
from pydantic import BaseModel, Field
from datetime import datetime
from src.optimization.model import optimize_dispatch,kpis
from src.simulation.scenarios import SCENARIOS, run_scenario
from src.forecasting.predict import forecast_all

app=FastAPI(title='NetZeroAI Microgrid API',version='1.0.0')
app.add_middleware(CORSMiddleware,allow_origins=['http://localhost:3000','http://127.0.0.1:3000'],allow_methods=['*'],allow_headers=['*'])
CFG=yaml.safe_load(open('configs/config.yaml'))
DATA='data/processed/master_hourly.csv'

def data():
    if not os.path.exists(DATA): raise HTTPException(500,'Run python -m src.data.generate_demo_data first.')
    return pd.read_csv(DATA,parse_dates=['timestamp'])

@app.get('/health')
def health(): return {'status':'ok','data_exists':os.path.exists(DATA),'models_exist':all(os.path.exists(f'models/{x}_xgb.joblib') for x in ['solar_available_kw','wind_available_kw','load_kw'])}

@app.get('/forecast')
def forecast(hours:int=24):
    df=data()
    if all(os.path.exists(f'models/{x}_xgb.joblib') for x in ['solar_available_kw','wind_available_kw','load_kw']):
        out=forecast_all(df.tail(200),hours)
    else:
        last=df.tail(1).copy(); out=pd.concat([last]*hours,ignore_index=True); out['timestamp']=[last.timestamp.iloc[0]+pd.Timedelta(hours=i+1) for i in range(hours)]
    out['grid_price_rs_kwh']=out['timestamp'].dt.hour.map(lambda h: 11 if 18<=h<=22 else (5.5 if 10<=h<=16 else 7.5))
    out['grid_carbon_kgco2_kwh']=out['timestamp'].dt.hour.map(lambda h: .9 if 18<=h<=22 else .65)
    return out.to_dict(orient='records')

class ForecastPoint(BaseModel):
    timestamp: datetime
    solar_available_kw: float=Field(ge=0)
    wind_available_kw: float=Field(ge=0)
    load_kw: float=Field(ge=0)
    grid_price_rs_kwh: float=0
    grid_carbon_kgco2_kwh: float=0.75

class OptimizeRequest(BaseModel):
    forecast: list[ForecastPoint]

@app.post('/optimize')
def optimize(req:OptimizeRequest):
    f=pd.DataFrame([x.model_dump() for x in req.forecast]);
    if len(f)==0: raise HTTPException(400,'forecast cannot be empty')
    d=optimize_dispatch(f,CFG)
    return {'kpis':kpis(f,d),'method':d.attrs.get('method'),'fallback_reason':d.attrs.get('fallback_reason'),'dispatch':d.to_dict(orient='records')}

class ScenarioRequest(BaseModel):
    hours:int=24

@app.post('/scenario/{name}')
def scenario(name:str,req:ScenarioRequest):
    df=data().tail(req.hours).reset_index(drop=True)
    if name not in SCENARIOS: raise HTTPException(400,f'Unknown scenario. Choose one of: {", ".join(SCENARIOS)}')
    return run_scenario(df,CFG,name)

@app.post('/simulate')
def simulate(req:OptimizeRequest):
    f=pd.DataFrame([x.model_dump() for x in req.forecast]); d=optimize_dispatch(f,CFG)
    return {'summary':kpis(f,d),'method':d.attrs.get('method'),'fallback_reason':d.attrs.get('fallback_reason'),'dispatch':d.to_dict(orient='records')}

class AskRequest(BaseModel):
    question: str=Field(min_length=1,max_length=500)
    scenario: str='normal'
    kpis: dict={}
    hours: int=24
    method: str=''
    fallback_reason: str=''
    dispatch: list[dict]=[]

SYSTEM=('You are an energy-operations assistant for a solar + wind + battery microgrid. Use ONLY the APP DATA. '
        'Quote numbers exactly, never invent values or units, say so if the data does not answer the question, and keep answers under 140 words. Plain text only: no markdown, no asterisks.')

@app.get('/ask/status')
def ask_status(): return {'enabled':llm.available()}

@app.post('/ask')
def ask(req:AskRequest):
    df=data().tail(req.hours)
    ctx=[f'Scenario: {req.scenario}',f'Window: last {len(df)} hours of data',
         f'Average solar available {df.solar_available_kw.mean():.1f} kW, wind {df.wind_available_kw.mean():.1f} kW, load {df.load_kw.mean():.1f} kW',
         f'Peak load {df.load_kw.max():.1f} kW']
    if req.dispatch:
        d=pd.DataFrame(req.dispatch).apply(pd.to_numeric,errors='ignore') if False else pd.DataFrame(req.dispatch)
        g=lambda c: float(pd.to_numeric(d.get(c,0),errors='coerce').fillna(0).sum()) if c in d else 0.0
        ctx.append(f"Dispatch totals: battery discharge {g('discharge_kw'):.0f} kWh, battery charge {g('charge_kw'):.0f} kWh, grid import {g('grid_import_kw'):.0f} kWh, unserved {g('unserved_kw'):.0f} kWh")
        if 'grid_import_kw' in d: ctx.append(f"Peak grid import {float(pd.to_numeric(d['grid_import_kw']).max()):.0f} kW at hour {int(pd.to_numeric(d['grid_import_kw']).idxmax())}")
        if 'soc' in d: ctx.append(f"Battery state of charge ranged {float(d.soc.min())*100:.0f}% to {float(d.soc.max())*100:.0f}%")
    ctx+= [f'{k}: {v:.3f}' if isinstance(v,(int,float)) else f'{k}: {v}' for k,v in req.kpis.items()]
    if req.method: ctx.append(f'Plan type: {req.method}'+(f' because {req.fallback_reason}; it is NOT a cost-optimal plan and you must say so' if req.fallback_reason else ''))
    ctx.append('Battery/grid limits from config: '+str({k:v for k,v in CFG.items() if not isinstance(v,(list,dict)) or k in ('battery','grid')}))
    try: return {'answer':llm.ask(req.question,'\n'.join(ctx),SYSTEM)}
    except RuntimeError as e: raise HTTPException(502,str(e))

@app.get('/metrics')
def metrics():
    p='models/metrics.json'
    return json.load(open(p)) if os.path.exists(p) else {}
