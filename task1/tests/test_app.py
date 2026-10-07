from pathlib import Path
from streamlit.testing.v1 import AppTest
from src.cities import read_city

ROOT=Path(__file__).resolve().parents[1]

def test_dashboard_city_models_horizons_tabs_and_upload():
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=60).run()
    assert not app.exception
    assert [t.label for t in app.tabs][-1]=='06  Ask the analyst'
    assert len(app.tabs)==6
    assert app.selectbox(key='station').value=='NOIDA'
    assert app.metric[0].value==f"{read_city('NOIDA')[0].value.iloc[-1]:.2f}"
    assert app.metric[3].value in ('Seasonal Ridge','Lag Ridge','Random forest')
    app.selectbox(key='station').set_value('AHMEDABAD').run()
    assert not app.exception
    assert app.metric[0].value==f"{read_city('AHMEDABAD')[0].value.iloc[-1]:.2f}"
    app.session_state['workspace']='02  City map & comparison';app.run()
    assert not app.exception
    next(b for b in app.button if b.label=='View selected forecast').click().run()
    assert app.session_state['workspace']=='01  Forecast'
    app.selectbox(key='model').set_value('Persistence').run()
    assert not app.exception and app.metric[3].value=='Persistence'
    app.select_slider[0].set_value(30).run()
    assert not app.exception and 'Day 30' in app.metric[1].label
    assert app.metric[1].value==app.metric[0].value
    app.select_slider[0].set_value(7).run()
    assert not app.exception and 'Day 7' in app.metric[1].label
    for tab in ['03  Model lab','04  History & alerts','05  Inputs & sources']:
        app.session_state['workspace']=tab;app.run()
        assert not app.exception
    app.radio[0].set_value('Upload local CSV').run()
    assert not app.exception
    assert any('Choose a CSV' in i.value for i in app.info)
    app.selectbox(key='gas').set_value('ch4').run()
    assert not app.exception
    app.radio[0].set_value('Regional CO₂ history').run()
    assert not app.exception and app.selectbox(key='gas').value=='co2'
