'use client';
import {useEffect,useState} from 'react';
import {LineChart,Line,CartesianGrid,XAxis,YAxis,Tooltip,ResponsiveContainer,ComposedChart,Area} from 'recharts';
const API=process.env.NEXT_PUBLIC_API_URL||'http://127.0.0.1:8000';
type Row={timestamp:string,solar_available_kw:number,wind_available_kw:number,load_kw:number,grid_price_rs_kwh:number,grid_carbon_kgco2_kwh:number};
type Disp={timestamp:string,solar_kw:number,wind_kw:number,discharge_kw:number,grid_import_kw:number,charge_kw:number,unserved_kw:number,soc:number};
const C={solar:'#f2b84b',wind:'#4fc3b0',batt:'#8aa7ff',grid:'#ef7d57',load:'#e8f1ec'};
const SCEN:[string,string][]=[['','Normal day'],['cloud_event','Cloud event'],['wind_drop','Wind drop'],['load_spike','Evening load spike'],['battery_low','Battery low'],['grid_outage','Grid outage']];
const ASK=['Why was this dispatch chosen?','What is the biggest risk in this scenario?','How could we cut grid import?'];
const hour=(x:string)=>new Date(x).getHours()+':00';
const tip={contentStyle:{background:'#111c18',border:'1px solid #25382f',borderRadius:8,fontSize:13},labelFormatter:(x:any)=>hour(String(x))};
const fmt=(v:any,d=0)=>typeof v==='number'?v.toLocaleString('en-IN',{maximumFractionDigits:d}):'–';

export default function Home(){
 const [rows,setRows]=useState<Row[]>([]);const [res,setRes]=useState<any>();const [scen,setScen]=useState('');
 const [up,setUp]=useState<boolean|null>(null);const [llm,setLlm]=useState(false);const [met,setMet]=useState<any>({});
 const [busy,setBusy]=useState(false);const [err,setErr]=useState('');
 const [q,setQ]=useState(ASK[0]);const [ans,setAns]=useState('');const [asking,setAsking]=useState(false);const [bad,setBad]=useState(false);

 async function run(name:string,fc:Row[]){
  setBusy(true);setErr('');
  try{
   const r=name?await fetch(`${API}/scenario/${name}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({hours:24})})
                :await fetch(`${API}/optimize`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({forecast:fc})});
   if(!r.ok)throw new Error(`The planner returned ${r.status}`);
   setRes(await r.json());setAns('');
  }catch(e:any){setErr(e.message||'Could not reach the API')}
  setBusy(false);
 }
 useEffect(()=>{(async()=>{
  try{
   const h=await fetch(`${API}/health`).then(r=>r.json());setUp(h.status==='ok');
   fetch(`${API}/ask/status`).then(r=>r.json()).then(j=>setLlm(j.enabled));
   fetch(`${API}/metrics`).then(r=>r.json()).then(setMet);
   const f:Row[]=await fetch(`${API}/forecast?hours=24`).then(r=>r.json());setRows(f);
   await run('',f);
  }catch{setUp(false);setErr('Could not reach the API. Start it with: uvicorn api.main:app')}
 })()},[]);// eslint-disable-line react-hooks/exhaustive-deps

 function pick(n:string){setScen(n);run(n,rows)}
 async function ask(question:string){
  setQ(question);setAsking(true);setAns('');setBad(false);
  try{
   const r=await fetch(`${API}/ask`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question,scenario:scen||'normal',kpis:res?.kpis||{},method:res?.method||'',fallback_reason:res?.fallback_reason||'',dispatch:(res?.dispatch||[]).map((x:Disp)=>({solar_kw:x.solar_kw,wind_kw:x.wind_kw,discharge_kw:x.discharge_kw,charge_kw:x.charge_kw,grid_import_kw:x.grid_import_kw,unserved_kw:x.unserved_kw,soc:x.soc}))})});
   const j=await r.json();setBad(!r.ok);setAns(r.ok?String(j.answer).replace(/\*\*/g,'').replace(/^\* /gm,'• '):j.detail);
  }catch{setBad(true);setAns('Could not reach the API.')}
  setAsking(false);
 }
 const k=res?.kpis||{};const d:Disp[]=(res?.dispatch||[]).map((x:Disp,i:number)=>({...x,load:rows[i]?.load_kw,socPct:x.soc*100}));
 const avg=(key:keyof Row)=>rows.length?rows.reduce((a,b)=>a+(b[key] as number),0)/rows.length:0;
 return <div className="wrap">
  <div className="top"><div className="brand"><span className="logo">⚡</span>NetZeroAI</div>
   <div className="status"><span><i className={'dot '+(up?'on':'')}/>API {up===null?'…':up?'online':'offline'}</span><span><i className={'dot '+(llm?'on':'')}/>AI analyst {llm?'ready':'off'}</span></div></div>
  <section className="hero"><h1>Run a microgrid on sun and wind, and know why.</h1>
   <p>Forecast the next 24 hours, let an optimiser schedule the battery and grid, stress-test it against bad days, then ask the analyst to explain the plan in plain words.</p></section>

  {err&&<div className="panel" role="alert" style={{borderColor:'#ff6b6b'}}>{err}</div>}

  <div className="kpis">
   <div className="kpi" style={{['--c' as any]:C.solar}}><div className="l">Renewable used</div><div className="v">{fmt(k.renewable_used_kwh)}<span className="u">kWh</span></div><div className="s">{fmt(k.renewable_utilization_pct,1)}% of what sun and wind offered{k.renewable_spilled_kwh>1?` · ${fmt(k.renewable_spilled_kwh)} kWh spilled`:''}</div></div>
   <div className="kpi" style={{['--c' as any]:C.grid}}><div className="l">Grid import</div><div className="v">{fmt(k.grid_import_kwh)}<span className="u">kWh</span></div><div className="s">{fmt(k.grid_dependency_pct,1)}% of demand</div></div>
   <div className="kpi" style={{['--c' as any]:C.batt}}><div className="l">Grid CO₂</div><div className="v">{fmt(k.grid_co2_kg)}<span className="u">kg</span></div></div>
   <div className="kpi" style={{['--c' as any]:C.wind}}><div className="l">Critical load served</div><div className="v">{fmt(k.critical_load_coverage_pct,1)}<span className="u">%</span></div><div className="s">{k.unserved_kwh>0?'load was shed':'all demand met'}</div></div>
   <div className="kpi" style={{['--c' as any]: k.unserved_kwh>0?'#ff6b6b':'#8aa398'}}><div className="l">{k.unserved_kwh>0?'Unserved load':'Grid cost'}</div><div className="v">{k.unserved_kwh>0?<>{fmt(k.unserved_kwh)}<span className="u">kWh</span></>:<>₹{fmt(k.grid_cost_rs)}</>}</div></div>
  </div>

  <div className="panel"><div className="row"><div><h2>Scenario</h2><div className="sub">The optimiser re-plans the same day under each disturbance.</div></div>
   <div className="seg" role="group" aria-label="Scenario">{SCEN.map(([id,l])=><button key={id} className={scen===id?'on':''} onClick={()=>pick(id)} disabled={busy}>{l}</button>)}</div></div></div>

  <div className="two">
   <div className="panel"><h2>Next 24 hours · forecast</h2><div className="sub">Average solar {fmt(avg('solar_available_kw'))} kW · wind {fmt(avg('wind_available_kw'))} kW · load {fmt(avg('load_kw'))} kW</div>
    <div className="chart"><ResponsiveContainer width="100%" height="100%"><LineChart data={rows}><CartesianGrid stroke="#25382f" vertical={false}/><XAxis dataKey="timestamp" tickFormatter={hour} stroke="#8aa398" fontSize={12}/><YAxis stroke="#8aa398" fontSize={12} unit=" kW" width={64}/><Tooltip {...tip}/>
     <Line isAnimationActive={false} dataKey="solar_available_kw" name="Solar" stroke={C.solar} dot={false} strokeWidth={2}/><Line isAnimationActive={false} dataKey="wind_available_kw" name="Wind" stroke={C.wind} dot={false} strokeWidth={2}/><Line isAnimationActive={false} dataKey="load_kw" name="Load" stroke={C.load} dot={false} strokeWidth={2} strokeDasharray="5 4"/></LineChart></ResponsiveContainer></div>
    <div className="legend"><span><i style={{background:C.solar}}/>Solar</span><span><i style={{background:C.wind}}/>Wind</span><span><i style={{background:C.load}}/>Load</span></div></div>
   <div className="panel"><h2>Forecast accuracy</h2><div className="sub">Held-out error against a naive baseline.</div>
    <table><thead><tr><th>Signal</th><th>MAE kW</th><th>Baseline</th></tr></thead><tbody>
     {Object.entries(met).map(([n,m]:any)=><tr key={n}><td>{n.replace('_available_kw','').replace('_kw','')}</td><td className="mono good">{fmt(m.MAE,1)}</td><td className="mono">{fmt(m.baseline_MAE,1)}</td></tr>)}</tbody></table>
    <div className="note">Lower is better. The data are synthetic demo data, so these figures show the pipeline works, not field accuracy.</div></div>
  </div>

  <div className="panel"><div className="row"><h2>{res?.method==='rule-based fallback'?'Fallback dispatch':'Optimal dispatch'}{scen?` · ${SCEN.find(s=>s[0]===scen)?.[1]}`:''}</h2>{res?.method&&<span className={'tag'+(res.fallback_reason?' warn':'')}>{res.fallback_reason?'rule-based':'HiGHS optimal'}</span>}</div>
   <div className="sub">{res?.fallback_reason?`The optimiser found ${res.fallback_reason}, so this is the simple rule-based schedule, not a cost-optimal one.`:'Where each kilowatt comes from. The line is demand.'}</div>
   <div className="chart"><ResponsiveContainer width="100%" height="100%"><ComposedChart data={d}><CartesianGrid stroke="#25382f" vertical={false}/><XAxis dataKey="timestamp" tickFormatter={hour} stroke="#8aa398" fontSize={12}/><YAxis stroke="#8aa398" fontSize={12} unit=" kW" width={64}/><Tooltip {...tip}/>
    <Area isAnimationActive={false} dataKey="solar_kw" name="Solar" stackId="1" stroke={C.solar} fill={C.solar} fillOpacity={.75}/><Area isAnimationActive={false} dataKey="wind_kw" name="Wind" stackId="1" stroke={C.wind} fill={C.wind} fillOpacity={.75}/><Area isAnimationActive={false} dataKey="discharge_kw" name="Battery" stackId="1" stroke={C.batt} fill={C.batt} fillOpacity={.75}/><Area isAnimationActive={false} dataKey="grid_import_kw" name="Grid" stackId="1" stroke={C.grid} fill={C.grid} fillOpacity={.75}/>
    <Line isAnimationActive={false} dataKey="load" name="Load" stroke={C.load} dot={false} strokeWidth={2}/></ComposedChart></ResponsiveContainer></div>
   <div className="legend"><span><i style={{background:C.solar}}/>Solar</span><span><i style={{background:C.wind}}/>Wind</span><span><i style={{background:C.batt}}/>Battery</span><span><i style={{background:C.grid}}/>Grid</span><span><i style={{background:C.load}}/>Load</span></div></div>

  <div className="panel ask"><h2>Ask the AI analyst</h2><div className="sub">A Groq-hosted language model explains the numbers above. It sees only what the planner computed and cannot change it.</div>
   <div className="row"><input value={q} onChange={e=>setQ(e.target.value)} onKeyDown={e=>e.key==='Enter'&&q&&ask(q)} aria-label="Question"/><button className="btn primary" onClick={()=>ask(q)} disabled={asking||!llm||!q}>{asking?'Thinking…':'Ask'}</button></div>
   <div className="chips">{ASK.map(a=><button key={a} onClick={()=>ask(a)} disabled={asking||!llm}>{a}</button>)}</div>
   {ans&&<div className={'answer'+(bad?' err':'')} role="status">{ans}</div>}
   {!llm&&up&&<div className="note">Add GROQ_API_KEY to .env and restart the API to enable this.</div>}
   <div className="note">AI-generated explanation; the planner and KPIs are the source of truth.</div></div>
  <footer>NetZeroAI · forecasting with XGBoost, dispatch with a Pyomo/HiGHS optimiser, explanations via Groq.</footer>
 </div>
}
