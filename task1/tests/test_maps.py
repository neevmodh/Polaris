import math
import pytest
from src.maps import project, world_paths, selected_station

def test_world_geometry_renders_both_poles_without_clipping():
    assert project(-180,90)==(0,0)
    assert project(180,-90)==(1000,500)
    x,y=project(-24.8,-89.98)
    assert 0<x<1000 and 499<y<500
    paths=world_paths()
    assert len(paths)>200 and all(path.startswith('M') and path.endswith('Z') for path in paths)

@pytest.mark.parametrize('lon,lat',[(181,0),(0,91),(-181,0),(0,-91),(math.nan,0),(0,math.inf)])
def test_invalid_coordinates_rejected(lon,lat):
    with pytest.raises(ValueError,match='Coordinates'):project(lon,lat)

def test_map_events_only_select_available_stations_for_current_gas():
    entries=[{'gas':'co2','station':'MLO','eligible':True},
             {'gas':'co2','station':'SPO','eligible':True},
             {'gas':'ch4','station':'BRW','eligible':False}]
    assert selected_station({'gas':'co2','station':'SPO'},entries,'co2')=='SPO'
    assert selected_station({'gas':'ch4','station':'BRW'},entries,'ch4') is None
    assert selected_station({'gas':'co2','station':'SPO'},entries,'ch4') is None
    assert selected_station({'gas':'co2','station':'unknown'},entries,'co2') is None
    assert selected_station(None,entries,'co2') is None
