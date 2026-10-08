from pathlib import Path
from html import escape
from hashlib import sha256
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
from src.data import GASES, load_upload, validate_series
from src.forecast import MODELS, HORIZONS, train_and_forecast, forecast_view
from src.reports import forecast_csv, export_bundle, html_report
from src.maps import world_paths, project, selected_station
from src.cities import city_catalog, read_city, anomalies
from io import BytesIO
import joblib
from src import llm

st.set_page_config(page_title="Atmos · Local greenhouse gas forecasts", page_icon="🌐", layout="wide")
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Instrument+Serif:ital@0;1&display=swap');
html,body,[class*="css"],.stApp{font-family:'DM Sans',sans-serif}
.block-container{padding:2.5rem 3.5rem 3rem;max-width:1600px}
[data-testid="stSidebar"]{border-right:1px solid #26383c}
[data-testid="stSidebar"] .block-container{padding:2rem 1.5rem}
h1,h2,h3{letter-spacing:-.03em}h1{font-family:'Instrument Serif',Georgia,serif!important;font-weight:400!important}
.brand{font-size:34px;font-family:'Instrument Serif',Georgia;color:#c7ed9f;margin:0 0 6px}
.eyebrow{font-size:11px;letter-spacing:.16em;color:#9eafa8;text-transform:uppercase;margin-bottom:18px}
.hero{display:flex;justify-content:space-between;gap:30px;align-items:flex-start;border-bottom:1px solid #293b40;padding-bottom:24px;margin-bottom:24px}
.hero h1{font-size:52px;line-height:1.05;margin:0 0 12px}.hero p{color:#a5b8b0;font-size:15px;max-width:620px;line-height:1.7;margin:0}
.pill{background:#1c3029;color:#c7ed9f;border:1px solid #355047;border-radius:30px;padding:9px 14px;font-size:11px;white-space:nowrap;margin-top:10px}
.section-label{font-size:11px;letter-spacing:.12em;color:#a3b8aa;margin-top:14px;text-transform:uppercase}
[data-testid="stMetric"]{border:1px solid #2a3b40;border-radius:12px;padding:18px 20px;background:#122127}
[data-testid="stMetricValue"]{font-family:'Instrument Serif',Georgia;font-size:34px;color:#eaf2ee}
[data-testid="stMetricValue"]>div{white-space:normal!important;text-overflow:clip!important;overflow:visible!important;font-size:30px}
[data-testid="stMetricLabel"]{font-size:12px;color:#a5b8b0}
.ai-card{border:1px solid #2a3b40;border-left:3px solid #c7ed9f;border-radius:0 12px 12px 0;background:#122127;padding:20px 24px;margin:18px 0 6px}
.ai-card p{margin:0 0 12px;font-size:15px;line-height:1.75;color:#dbe8e1}.ai-card p:last-child{margin-bottom:0}
.ai-meta{font-size:10px;letter-spacing:.14em;color:#8ca89a;text-transform:uppercase;margin-bottom:12px}
.ai-empty{border:1px dashed #2a3b40;border-radius:12px;padding:26px;text-align:center;color:#8ca89a;font-size:14px;margin:18px 0}
.note{padding:13px 17px;border-left:2px solid #c7ed9f;background:#15232a;color:#b8c9c0;font-size:12px;margin:20px 0;line-height:1.7}
.station-card{padding:18px;border:1px solid #2a3b40;border-radius:12px;min-height:132px}.station-card h3{font-size:16px;margin:0 0 8px}.station-card p{font-size:12px;color:#a5b8b0;margin:0}
[data-testid="stMetricDelta"] svg{display:none}
button[data-baseweb="tab"]{padding:12px 16px}footer{visibility:hidden}.stButton>button{border-radius:9px}
@media(max-width:900px){.block-container{padding:1.5rem}.hero h1{font-size:44px}.hero{display:block}.pill{display:inline-block}}
</style>""", unsafe_allow_html=True)

@st.cache_data
def station_data(gas, station):
    return read_city(station)

@st.cache_data
def catalog():
    return city_catalog()

@st.cache_data(show_spinner=False, max_entries=24)
def analysis(frame):
    return train_and_forecast(frame, 30)

@st.cache_data(show_spinner=False, max_entries=64)
def ask_llm(question, context, system):
    """Cached so the same question on the same figures is answered once."""
    return llm.ask(question, context, system)

@st.cache_data
def map_paths():
    return world_paths()

@st.cache_resource
def map_component():
    assets=Path(__file__).parent/'assets'
    return st.components.v2.component('atmos_city_map',
        html=(assets/'station_map.html').read_text(encoding="utf-8"),
        css=(assets/'station_map.css').read_text(encoding="utf-8"),
        js=(assets/'station_map.js').read_text(encoding="utf-8"))

def use_station(code):
    st.session_state['source']='Regional CO₂ history'
    st.session_state['station']=code
    st.session_state['gas']='co2'

def map_changed():
    event=st.session_state.get('city_atlas',{}).get('selected')
    code=selected_station(event,catalog(),'co2')
    if code:
        use_station(code)

def open_forecast():
    st.session_state['workspace']='01  Forecast'

def chart_style(fig, height=390):
    fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      height=height, margin=dict(l=0,r=15,t=15,b=0), font=dict(family="DM Sans",color="#b9c9c2"),
                      legend=dict(orientation="h", y=1.1, x=0), hovermode="x unified")
    fig.update_xaxes(gridcolor="#213238", zeroline=False)
    fig.update_yaxes(gridcolor="#213238", zeroline=False)
    return fig

TABS = ('01  Forecast','02  City map & comparison','03  Model lab','04  History & alerts','05  Inputs & sources','06  Ask the analyst')
entries = catalog()
# Reset obsolete observatory selections from earlier app sessions.
if st.session_state.get('source') not in ('Regional CO₂ history','Upload local CSV'):
    st.session_state['source']='Regional CO₂ history'
if st.session_state.get('station') not in ('NOIDA','AHMEDABAD'):
    st.session_state['station']='NOIDA'
if st.session_state.get('workspace') not in TABS:
    st.session_state['workspace']='01  Forecast'
with st.sidebar:
    st.markdown('<div class="brand">Atmos<span style="color:#eaf2ee">.</span></div><div class="eyebrow">POLARIS / Task 01</div>', unsafe_allow_html=True)
    st.caption("Machine learning · Noida & Ahmedabad")
    station = st.selectbox('City', [e['station'] for e in entries],
        format_func=lambda code: next(e['name'] for e in entries if e['station']==code),key='station')
    source = st.radio('Training data', ['Regional CO₂ history','Upload local CSV'],key='source')
    if source=='Regional CO₂ history':
        st.session_state['gas']='co2'
    gas = st.selectbox('Greenhouse gas',list(GASES),format_func=lambda g:f"{GASES[g]['label']} · {GASES[g]['name']}",
                       disabled=source=='Regional CO₂ history',key='gas')
    horizon = st.select_slider('Forecast horizon',[7,14,30],value=14,format_func=lambda d:f'{d} days')
    model = st.selectbox('Forecast model',['Auto (validation winner)',*MODELS],key='model')
    st.divider()
    st.caption('Regional dataset: real NOAA CarbonTracker CT2026 estimates of boundary-layer CO₂. 3° × 2° grid; daily UTC means.')
    st.caption('CO₂ in ppm · Methane in ppb with your local CSV')
    if st.button('Retrain models',help='Clear trained-model caches and fit again from the current local data.'):
        analysis.clear();st.rerun()
    if st.button('Reload city data',help='Use after running scripts/fetch_cities.py to refresh the downloaded extraction.'):
        st.cache_data.clear();st.rerun()

if source == "Upload local CSV":
    st.markdown("### Bring your local measurements")
    st.write(f"Upload one daily mean per UTC date, with **date,value** columns. Values must be in **{GASES[gas]['unit']}**. Minimum: 900 valid days spanning 3 years.")
    uploaded = st.file_uploader("Daily greenhouse gas observations", type=["csv"], max_upload_size=10)
    station_name = st.text_input("Site name", next(e["name"] for e in entries if e["station"]==station)+" local sensor", max_chars=100)
    locate_site = st.checkbox('Place my station on the map', key='locate_site')
    if locate_site:
        lat_col,lon_col=st.columns(2)
        local_lat=lat_col.number_input('Latitude',min_value=-90.,max_value=90.,value=next(e['latitude'] for e in entries if e['station']==station),format='%.4f',key='local_lat')
        local_lon=lon_col.number_input('Longitude',min_value=-180.,max_value=180.,value=next(e['longitude'] for e in entries if e['station']==station),format='%.4f',key='local_lon')
    st.caption("Hourly data must be aggregated to daily means first. The file stays on this local app.")
    example, _ = station_data("co2", station)
    template = example.tail(1461).copy()
    template["unit"] = "ppm"
    st.download_button("Download regional CO₂ example CSV", template.to_csv(index=False), f"{station.lower()}_regional_co2_example.csv", "text/csv")
    st.caption("The example is modeled regional CO₂ in ppm; it is not local sensor data or a methane example.")
    if uploaded is None:
        st.info("Choose a CSV to train models for your own station. Regional CO₂ history is ready to explore.")
        st.stop()
    try:
        content = uploaded.getvalue()
        frame = load_upload(content, gas)
    except ValueError as exc:
        st.error(str(exc)); st.stop()
    info = {"name": station_name or "Local monitoring station", "gas":gas,"unit":GASES[gas]["unit"],
            "station":"LOCAL","origin":"User-supplied daily concentration data", "sha256":sha256(content).hexdigest(),
            "source_rows":len(frame),"rejected_rows":0,"scope":"User-supplied daily concentrations. Measurement origin, calibration and spatial representativeness are not independently verified."}
    if locate_site:
        info.update(latitude=local_lat,longitude=local_lon)
else:
    frame, info = station_data(gas, station)

try:
    quality = validate_series(frame)
    with st.spinner("Training models and checking the chronological holdout…"):
        result = forecast_view(analysis(frame), horizon, model)
except ValueError as exc:
    st.error(str(exc)); st.stop()

forecast = result["forecast"]
unit, label = info["unit"], GASES[gas]["label"]
last_date = quality["last"].strftime("%d %b %Y")
final = forecast.iloc[-1]
safe_name = escape(info["name"])
st.markdown(f'''<div class="hero"><div><div class="eyebrow">MEASURE · MODEL · ANTICIPATE</div>
<h1>{safe_name}.<br>Forecast the air ahead.</h1><p>Machine learning predicts daily {label} levels from this location’s own historical data. Compare Ridge regression and random forest against simple forecasting baselines.</p></div>
<div class="pill">● &nbsp; {'Regional CO₂ · NOAA CT2026' if source=='Regional CO₂ history' else 'Uploaded concentration data'}</div></div>''', unsafe_allow_html=True)

a,b,c,d = st.columns(4)
a.metric(f"Latest {label} estimate · {unit}", f"{frame.iloc[-1].value:.2f}", last_date, delta_color="off")
b.metric(f"Day {horizon} forecast · {unit}", f"{final.predicted:.2f}", f"{final.predicted-frame.iloc[-1].value:+.2f} from latest", delta_color="off")
eval_h = min(HORIZONS, key=lambda h:abs(h-horizon))
selected_metrics = result["metrics"][result["metrics"].model == result["selected"]]
m = selected_metrics[selected_metrics.horizon_days == eval_h].iloc[0]
c.metric(f"Holdout MAE · {unit}", f"{m.mae:.2f}", f"{eval_h}-day horizon · {int(m.test_targets)} targets", delta_color="off")
d.metric("Model in use", result["selected"], "Chosen on calibration" if model.startswith("Auto") else "Selected manually", delta_color="off")
scope_note='Regional boundary-layer CO₂ in a 3° × 2° cell extending beyond the city. Historical model estimates; not live city sensor readings.' if source=='Regional CO₂ history' else 'Forecast from the last uploaded data point. Data origin and calibration are unverified; not a live reading.'
st.markdown(f'<div class="note">Forecast origin: <b>{last_date}</b> → {final["date"].strftime("%d %b %Y")}. {scope_note} Forecasts start from the data date, not today. Shaded bands are nominal 90% ranges calibrated on past errors.</div>', unsafe_allow_html=True)
forecast_tab, atlas_tab, lab_tab, data_tab, method_tab, ask_tab = st.tabs(list(TABS),key='workspace',on_change='rerun')

with forecast_tab:
    baseline_mae=result['metrics'].query('model == "Persistence" and horizon_days == @eval_h').mae.iloc[0]
    if m.mae>baseline_mae:
        st.warning(f'This model underperformed persistence on the {eval_h}-day holdout: MAE {m.mae:.2f} versus {baseline_mae:.2f} {unit}. Use the model selector to compare the Persistence benchmark. Nominal interval coverage is {m.coverage_90:.0%}.')
    left,right=st.columns([3,1],gap="large")
    with left:
        st.markdown("### From observation to outlook")
        f=go.Figure()
        history=frame.tail(100)
        f.add_trace(go.Scatter(x=history.date,y=history.value,name="Regional daily estimate" if source=="Regional CO₂ history" else "Sensor daily mean",line=dict(color="#a4bbb2",width=2)))
        f.add_trace(go.Scatter(x=forecast.date,y=forecast.upper,mode="lines",name="90% band",line=dict(width=0),showlegend=False,hoverinfo="skip"))
        f.add_trace(go.Scatter(x=forecast.date,y=forecast.lower,mode="lines",fill="tonexty",fillcolor="rgba(199,237,159,.15)",line=dict(width=0),name="Nominal 90% band",hoverinfo="skip"))
        f.add_trace(go.Scatter(x=[frame.date.iloc[-1],*forecast.date],y=[frame.value.iloc[-1],*forecast.predicted],
                              name=result['selected']+" forecast",line=dict(color="#c7ed9f",width=3)))
        f.add_vline(x=quality["last"].timestamp()*1000,line_dash="dot",line_color="#5c8174")
        f.update_yaxes(title=f"{label} / {unit}")
        st.plotly_chart(chart_style(f),width="stretch",key="forecast_chart")
    with right:
        st.markdown("### The outlook")
        st.write(f"**{final['date'].strftime('%d %B %Y')}**")
        st.markdown(f"## {final.predicted:.2f} {unit}")
        st.caption(f"Nominal band: {final.lower:.2f}–{final.upper:.2f} {unit}")
        st.caption(f"Actual holdout coverage: {m.coverage_90:.0%}. Coverage can shift with new conditions.")
        st.download_button("↓ Forecast CSV",forecast_csv(info,result),f"{gas}_{info['station']}_forecast.csv","text/csv",width="stretch")
        st.download_button("↓ Analysis bundle",export_bundle(info,result,frame),f"{gas}_{info['station']}_analysis.zip","application/zip",width="stretch")
        st.download_button("↓ Portable report",html_report(info,result),"atmos_report.html","text/html",width="stretch")
    st.markdown('### Forecast review level')
    review=st.number_input(f'User-defined {label} review level ({unit})',min_value=0.01,value=float(round(frame.value.quantile(.95),2)),step=1.,key='review_'+info['station']+'_'+gas)
    days=forecast[forecast.predicted>review]
    st.write(f'**{len(days)} of {horizon} forecast days** have a central estimate above {review:.2f} {unit}.')
    st.caption('The initial review level is the historical 95th percentile. Change it for your analysis; it is not a health or regulatory limit. Forecast uncertainty is shown in the chart.')
    with st.expander("Compare the five model trajectories"):
        compare=go.Figure()
        for name in MODELS:
            compare.add_trace(go.Scatter(x=forecast.date,y=forecast[name],name=name))
        compare.update_yaxes(title=f"{label} / {unit}")
        st.plotly_chart(chart_style(compare,330),width="stretch",key="model_trajectories")
    with st.expander("Daily forecast table"):
        st.dataframe(forecast[["date","predicted","lower","upper"]].rename(columns={"lower":"90% lower","upper":"90% upper"}),hide_index=True,width="stretch")

with atlas_tab:
    st.markdown('### Noida & Ahmedabad · geographic coverage')
    st.caption('Select a city marker or button to switch its forecast. Shaded rectangles show the actual NOAA grid cells. Zoom, pan, and city selection work offline.')
    map_stations=[]
    for e in entries:
        sf,_=station_data('co2',e['station']);x,y=project(e['longitude'],e['latitude'])
        west,south,east,north=e['grid_bounds'];gx,gy=project(west,north);ex,ey=project(east,south)
        map_stations.append({'station':e['station'],'name':e['name'],'short_name':e['name'],
            'x':x,'y':y,'latitude':e['latitude'],'longitude':e['longitude'],
            'value':float(sf.value.iloc[-1]),'last':e['last'],'bounds':[gx,gy,ex-gx,ey-gy]})
    map_selected,map_gas,map_unit=station,'co2','ppm'
    if source=='Upload local CSV' and 'latitude' in info:
        x,y=project(info['longitude'],info['latitude'])
        local_marker={'station':'LOCAL','name':info['name'],'short_name':info['name'],
            'x':x,'y':y,'latitude':info['latitude'],'longitude':info['longitude'],
            'value':float(frame.value.iloc[-1]),'last':str(frame.date.max().date())}
        map_stations=[local_marker] if gas=='ch4' else [*map_stations,local_marker]
        map_selected,map_gas,map_unit='LOCAL',gas,unit
    if atlas_tab.open:
        map_component()(data={'paths':map_paths(),'stations':map_stations,'gas':map_gas,'unit':map_unit,
            'selected':map_selected,'view':[672,150,90,46.35]},key='city_atlas',on_selected_change=map_changed)
    st.button('View selected forecast',on_click=open_forecast,key='atlas_forecast')
    st.caption('Regional city values represent their entire shaded cells. An uploaded marker uses your supplied coordinates. No neighborhood concentration is inferred. Boundaries: Natural Earth public domain.')
    st.markdown('### Compare the two regional forecasts')
    if atlas_tab.open:
        comparison=go.Figure();summary=[]
        for e in entries:
            sf,si=station_data('co2',e['station'])
            with st.spinner('Checking '+e['name']+' models…'):
                sr=forecast_view(analysis(sf),horizon,model)
            sc=sr['forecast'];em=sr['metrics'];em=em[(em.model==sr['selected'])&(em.horizon_days==eval_h)].iloc[0]
            summary.append({'City':e['name'],'Latest (ppm)':sf.value.iloc[-1],f'Day {horizon} (ppm)':sc.predicted.iloc[-1],
                            'Model':sr['selected'],'Holdout MAE (ppm)':em.mae,'Data through':e['last']})
            comparison.add_trace(go.Scatter(x=sf.tail(60).date,y=sf.tail(60).value,name=e['name']+' history',line=dict(width=1)))
            comparison.add_trace(go.Scatter(x=sc.date,y=sc.predicted,name=e['name']+' forecast',line=dict(width=3,dash='dash')))
        comparison.update_yaxes(title='Regional boundary-layer CO₂ / ppm')
        st.plotly_chart(chart_style(comparison),width='stretch',key='city_comparison')
        st.dataframe(pd.DataFrame(summary),hide_index=True,width='stretch')
        st.download_button('↓ City comparison CSV',pd.DataFrame(summary).to_csv(index=False),'city_comparison.csv','text/csv')

with lab_tab:
    st.markdown("### Earn the forecast. Show the evidence.")
    st.write("Models learn from the earliest period. A later calibration period chooses the automatic model and interval widths. The final holdout stays separate from both decisions.")
    split=result['split']
    st.caption(f"Train: {split['train_start']} to before {split['train_end_exclusive']} · Calibration: {split['train_end_exclusive']} to before {split['test_start']} · Test: {split['test_start']} onwards")
    chosen_h=st.selectbox("Evaluation horizon",HORIZONS,index=HORIZONS.index(eval_h),format_func=lambda h:f"{h} days", key="evaluation_horizon")
    scores=result['metrics'][result['metrics'].horizon_days==chosen_h].copy().sort_values('mae')
    display=scores[['model','mae','rmse','coverage_90','test_targets']].rename(columns={'mae':f'MAE ({unit})','rmse':f'RMSE ({unit})','coverage_90':'90% band coverage','test_targets':'Holdout targets'})
    st.dataframe(display,hide_index=True,width="stretch",column_config={'90% band coverage':st.column_config.NumberColumn(format='percent')})
    persistence=scores[scores.model=='Persistence'].mae.iloc[0]
    selected=scores[scores.model==result['selected']].mae.iloc[0]
    skill=100*(1-selected/persistence) if persistence else 0
    st.caption(f"Selected model's MAE improvement over persistence: {skill:+.1f}%. Negative means persistence performed better on this holdout.")
    a,b=st.columns([2,1],gap="large")
    with a:
        traces=result['backtest']
        trace=traces[(traces.model==result['selected'])&(traces.horizon==chosen_h)]
        bt=go.Figure()
        bt.add_trace(go.Scatter(x=trace.target,y=trace.actual,name='Actual',line=dict(color='#a4bbb2')))
        bt.add_trace(go.Scatter(x=trace.target,y=trace.predicted,name='Held-out prediction',line=dict(color='#c7ed9f')))
        bt.update_yaxes(title=f'{label} / {unit}')
        st.plotly_chart(chart_style(bt,330),width="stretch",key="backtest_chart")
    with b:
        st.markdown("#### What the forest uses")
        imp=result['importance'].head(8).sort_values('importance')
        fig=px.bar(imp,x='importance',y='feature',orientation='h',color_discrete_sequence=['#c7ed9f'])
        st.plotly_chart(chart_style(fig,300),width="stretch",key="importance")
        st.caption("Tree split importance describes this model; it does not establish physical causes.")
    st.caption(f"Training examples: {split['training_rows']:,} · Calibration examples: {split['calibration_rows']:,} · Holdout examples: {split['test_rows']:,}. These are pooled forecast windows, not independent measurements.")
    model_buffer=BytesIO();joblib.dump(result['models'],model_buffer)
    st.download_button('↓ Trained ML models',model_buffer.getvalue(),f"{info['station'].lower()}_{gas}_models.joblib",'application/octet-stream')
    st.download_button('↓ All benchmark results',result['metrics'].to_csv(index=False),'holdout_metrics.csv','text/csv')

with data_tab:
    st.markdown("### Historical greenhouse gas levels & review alerts")
    q1,q2,q3=st.columns(3)
    q1.metric('Valid daily data points',f"{len(frame):,}")
    q2.metric('Calendar-day coverage',f"{quality['coverage']:.1%}")
    q3.metric('Unavailable extraction days' if source=='Regional CO₂ history' else 'Rows excluded',f"{info['rejected_rows']:,}")
    st.caption(f"Available history: {quality['first'].date()} – {quality['last'].date()}. Modelling uses at most the latest 8 years.")
    years=st.slider('Years of history to plot',1,min(20,max(1,quality['span']//365)),min(5,max(1,quality['span']//365)))
    hist=frame[frame.date>=frame.date.max()-pd.Timedelta(days=years*365)]
    history=px.line(hist,x='date',y='value',color_discrete_sequence=['#a4bbb2'])
    history.update_yaxes(title=f'{label} / {unit}')
    st.plotly_chart(chart_style(history,320),width="stretch",key="history")
    season=frame.assign(year=frame.date.dt.year,month=frame.date.dt.month)
    season=season[season.year>=frame.date.max().year-5].groupby(['year','month']).value.mean().reset_index()
    heat=season.pivot(index='year',columns='month',values='value')
    hm=px.imshow(heat,aspect='auto',color_continuous_scale=['#15232a','#588d73','#c7ed9f'],labels={'color':unit,'x':'Month','y':'Year'})
    st.plotly_chart(chart_style(hm,280),width="stretch",key="seasonality")
    with st.expander('Preview cleaned observations'):
        st.dataframe(frame.tail(200),hide_index=True,width='stretch')
    st.download_button('↓ Clean daily observations',frame.to_csv(index=False),f'{gas}_{info["station"]}_observations.csv','text/csv')
    if source=='Regional CO₂ history':
        st.write(f"[Open NOAA source archive]({info['url']})")
        st.caption(f"Retrieved: {info['retrieved_at']} · Release: {info['release']}")
        st.code(info['sha256'],language=None)
    else:
        st.caption('User CSV: values are validated structurally; sensor calibration and representativeness remain the data provider’s responsibility.')

    st.markdown('### Unusually high historical levels')
    sigma=st.slider('Review sensitivity (standard deviations)',1.5,4.0,2.5,.5)
    flagged=anomalies(frame,sigma=sigma).tail(180)
    af=go.Figure()
    af.add_trace(go.Scatter(x=flagged.date,y=flagged.value,name='Daily value',line=dict(color='#a4bbb2')))
    af.add_trace(go.Scatter(x=flagged.date,y=flagged.review_level,name='Historical review level',line=dict(color='#92a69d',dash='dot')))
    hits=flagged[flagged.flag]
    af.add_trace(go.Scatter(x=hits.date,y=hits.value,name='Flagged high value',mode='markers',marker=dict(color='#f0ba76',size=8)))
    af.update_yaxes(title=f'{label} / {unit}')
    st.plotly_chart(chart_style(af,300),width='stretch',key='anomalies')
    st.caption(f'{len(hits)} high-value days in the latest 180 days. Each threshold uses only the preceding 90 days (minimum 60 observations). These are statistical review flags, not health warnings or proof of a local emission source.')
    st.download_button('↓ Historical review flags',flagged.to_csv(index=False),'historical_review.csv','text/csv')

with method_tab:
    st.markdown('### Train on your local sensor data')
    st.write('Choose **Upload local CSV** in the sidebar to train on Noida or Ahmedabad daily CO₂ (ppm) or CH₄ (ppb) sensor measurements. Provide date,value and optionally unit columns. Minimum 900 valid daily values spanning 3 years. Place the sensor using its actual coordinates; do not relabel regional estimates as sensor measurements.')
    st.markdown('### Source & spatial footprint')
    st.json({k:info.get(k) for k in ('name','origin','variable','unit','latitude','longitude','grid_bounds','scope','citation','license')})
    st.markdown('[NOAA CarbonTracker CT2026](https://gml.noaa.gov/ccgg/carbontracker/CT2026/) · [Dataset DOI](https://doi.org/10.25925/hqp0-rk68) · [Source files](https://gml.noaa.gov/aftp/products/carbontracker/co2/CT2026/molefractions/co2_total/)')
    st.write('The bundled data are real NOAA model estimates, not direct city sensor observations. Each daily value averages the eight three-hourly pbl_co2 values in the nearest native cell. pbl_co2 is the dry-air CO₂ mole fraction pressure-averaged through the planetary boundary layer. No spatial upsampling or invented city offsets are used.')
    st.markdown('### How the machine learning works')
    st.write('Seasonal Ridge learns trend and annual cycles. Lag Ridge and random forest learn residual changes from past concentration lags, rolling statistics and forecast horizon. Persistence and seasonal persistence are benchmarks. Automatic selection chooses the lowest calibration RMSE among the three trained ML models; the holdout shows whether they beat the benchmarks.')
    st.write('The chronological split is 72% training, 14% calibration and 14% test. Targets crossing split boundaries are excluded. Missing feature inputs use at most 3 days of causal forward filling; target labels are never imputed. Model choice and nominal 90% bands use calibration only. Test results are fixed before final models are refit on the available history. Accuracy is measured against the regional source estimates; it does not validate ground-level accuracy in the city.')
    st.markdown('### GitHub references')
    st.markdown('- [scikit-learn](https://github.com/scikit-learn/scikit-learn): the actual Ridge and random-forest implementations used here (BSD-3-Clause).\n- [MGGTSP-CAT](https://github.com/Changbin-Z/MGGTSP-CAT): related localized methane forecasting research. Reviewed as a reference; unlicensed code is not copied.\n- [Stanford methane-gapfill-ml](https://github.com/stanfordmlgroup/methane-gapfill-ml): an attributed Apache-2.0 research snapshot; its flux gap filling is a different task from future concentration forecasting.')
    st.markdown('### Finer regional data')
    st.markdown('[CAMS greenhouse gas forecasts](https://ads.atmosphere.copernicus.eu/datasets/cams-global-greenhouse-gas-forecasts?tab=overview) offer a 0.1° output grid for CO₂ and CH₄. Download access requires a Copernicus account and accepted dataset terms. This app does not claim that the coarser bundled NOAA fields have that resolution. Local sensor CSVs can be used now.')
    st.caption('CarbonTracker CT2026 results provided by NOAA GML, Boulder, Colorado, USA from carbontracker.noaa.gov. NOAA permits unrestricted non-commercial use with attribution; retain its usage policy for reuse.')

with ask_tab:
    st.markdown("### Ask the analyst")
    st.write("A language model reads the figures this app computed and explains them in plain words. "
             "It is given the numbers only — it cannot recompute, change or improve them.")
    persistence_mae = result["metrics"].query('model == "Persistence" and horizon_days == @eval_h').mae.iloc[0]
    beat = m.mae < persistence_mae
    ctx = "\n".join([
        f"Site: {info['name']} · {label} in {unit} · data through {last_date}",
        f"Latest observed value: {frame.iloc[-1].value:.2f} {unit}",
        f"Day-{horizon} forecast: {final.predicted:.2f} {unit} (nominal 90% band {final.lower:.2f}–{final.upper:.2f}), a change of {final.predicted-frame.iloc[-1].value:+.2f}",
        f"Model in use: {result['selected']} ({'chosen automatically on calibration' if model.startswith('Auto') else 'chosen by the user'})",
        f"Holdout MAE at the {eval_h}-day horizon: {m.mae:.2f} {unit} over {int(m.test_targets)} targets; nominal 90% band actually covered {m.coverage_90:.0%}",
        f"Persistence benchmark MAE: {persistence_mae:.2f} {unit}",
        f"VERDICT (computed by the app, not by you): the selected model {'BEAT' if beat else 'DID NOT BEAT'} persistence on this holdout.",
        "Holdout scores for every model at this horizon:\n" + result['metrics'][result['metrics'].horizon_days == eval_h][['model','mae','rmse','coverage_90']].round(3).to_string(index=False),
        f"Data scope and caveat: {info.get('scope','')}"])
    system = ("You explain greenhouse-gas forecasts to a non-specialist. Use ONLY the APP DATA given. "
              "Quote its numbers exactly and never invent any. Never contradict the VERDICT line. "
              "Say plainly when the model did not beat persistence. Unless the data is a user sensor upload, remind the reader "
              "that city values are regional model estimates, not street-level measurements. "
              "Plain prose, no markdown, no asterisks, under 150 words.")

    PRESETS = [("Explain the forecast", "Explain this forecast in plain words and say how much I should trust it."),
               ("Is the model any good?", "Is this model actually better than the simple benchmark, and what do the error numbers mean?"),
               ("What are the limits?", "What are the main limitations and caveats of this result?"),
               ("What should I do next?", "Based only on these numbers, what would be a sensible next step for a city air-quality team?")]

    if not llm.available():
        st.info("Add GROQ_API_KEY to the .env file beside app.py, then restart, to enable this tab.")
    else:
        if "llm_q" not in st.session_state:
            st.session_state["llm_q"] = PRESETS[0][1]
        chips = st.columns(len(PRESETS))
        for i, (chip, text) in enumerate(PRESETS):
            if chips[i].button(chip, key=f"llm_p{i}", width="stretch"):
                st.session_state["llm_q"] = text
                st.session_state["llm_run"] = True
                st.rerun()
        question = st.text_input("Your question", key="llm_q", label_visibility="collapsed",
                                 placeholder="Ask anything about the numbers on this page")
        go, meta = st.columns([1, 3], vertical_alignment="center")
        if go.button("Ask the analyst", key="llm_go", type="primary", width="stretch"):
            st.session_state["llm_run"] = True
        meta.caption(f"Answers come from {llm.model_name()} hosted on Groq. Repeated questions are cached.")

        if st.session_state.pop("llm_run", False) and question.strip():
            try:
                with st.spinner("Reading the figures…"):
                    st.session_state["llm_a"] = ask_llm(question.strip(), ctx, system)
                    st.session_state["llm_err"] = None
            except RuntimeError as exc:
                st.session_state["llm_a"] = None
                st.session_state["llm_err"] = str(exc)

        if st.session_state.get("llm_err"):
            st.error(st.session_state["llm_err"])
        elif st.session_state.get("llm_a"):
            st.markdown(
                f'<div class="ai-card"><div class="ai-meta">ANALYST · {escape(llm.model_name())} · {escape(info["name"])} · {escape(result["selected"])}</div>'
                f'<p>{escape(st.session_state["llm_a"]).replace(chr(10)+chr(10), "</p><p>").replace(chr(10), "<br>")}</p></div>',
                unsafe_allow_html=True)
            st.caption("Generated text. The figures above and the Model lab tab remain the source of truth; "
                       "check any claim against them before quoting it.")
        else:
            st.markdown('<div class="ai-empty">Pick a question above, or write your own, to get a plain-language reading of this forecast.</div>',
                        unsafe_allow_html=True)

        with st.expander("Exactly what the model was shown"):
            st.code(ctx, language=None)
            st.caption("Nothing else is sent. No raw data file, no API key and no personal information leaves this machine.")

st.markdown('<div class="eyebrow" style="margin-top:35px;border-top:1px solid #293b40;padding-top:22px">ATMOS / POLARIS &nbsp; · &nbsp; NOIDA & AHMEDABAD. TRAINED MODELS. TESTABLE FORECASTS.</div>',unsafe_allow_html=True)
