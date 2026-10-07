"""Microgrid profiles and physics: weather -> solar and wind power, and a transparent simulated demand.
Equipment capacities, demand and generator curves are EXPLICIT ASSUMPTIONS (the proposal says so); only the weather is real (ERA5)."""
from dataclasses import dataclass, field, replace
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Profile:
    key: str
    name: str
    lat: float
    lon: float
    tz_hours: float                   # local time offset used for the daily demand pattern
    # generation and storage
    pv_kwp: float; wind_kw: float
    battery_kwh: float; battery_kw: float
    gen_kw: float
    tank_l: float
    # demand (SIMULATED): kW = (base + heat * max(0, hdd_base - T)) * daily pattern * weekly pattern * noise
    base_kw: float; heat_kw_per_c: float; hdd_base_c: float = 5.0
    essential_frac: float = 0.70      # must always be served
    flexible_frac: float = 0.20       # may move within flex_window_h; the rest is "normal" load that cannot move
    flex_window_h: int = 12
    # economics and equipment behaviour
    fuel_price: float = 80.0          # INR per litre
    start_cost: float = 400.0         # INR per generator start (wear)
    battery_wear: float = 2.0         # INR per kWh of throughput
    gen_min_frac: float = 0.30
    fuel_a: float = 0.246             # L per kWh generated (Willans line slope)
    fuel_b: float = 0.0815            # L per hour per kW rated (no-load consumption)
    eta_c: float = 0.95; eta_d: float = 0.95
    soc_min: float = 0.20; soc_max: float = 0.95
    pv_pr: float = 0.80; pv_temp_coeff: float = -0.004
    wind_hub_m: float = 30.0; wind_cut_in: float = 3.0; wind_rated_ms: float = 12.0; wind_cut_out: float = 25.0; wind_avail: float = 0.95
    seed: int = 7

    @property
    def gen_min_kw(self) -> float: return self.gen_min_frac * self.gen_kw

    @property
    def normal_frac(self) -> float: return max(1.0 - self.essential_frac - self.flexible_frac, 0.0)


POLAR = Profile(key="polar", name="Polar research station (illustrative, Maitri coordinates)", lat=-70.77, lon=11.73, tz_hours=0.0,
                pv_kwp=60, wind_kw=40, battery_kwh=300, battery_kw=80, gen_kw=80, tank_l=60000, base_kw=20, heat_kw_per_c=0.9)
COMMUNITY = Profile(key="community", name="Remote Himalayan community facility (illustrative, Ladakh coordinates)", lat=34.15, lon=77.58, tz_hours=5.5,
                    pv_kwp=120, wind_kw=20, battery_kwh=400, battery_kw=100, gen_kw=60, tank_l=30000, base_kw=14, heat_kw_per_c=0.55,
                    essential_frac=0.60, flexible_frac=0.25)
PROFILES = {p.key: p for p in (POLAR, COMMUNITY)}


# ------------------------------------------------------------------ solar geometry (NOAA approximations)
def solar_zenith_cos(times: pd.DatetimeIndex, lat: float, lon: float) -> np.ndarray:
    doy = times.dayofyear.values.astype(float)
    hour = times.hour.values + times.minute.values / 60.0 + 0.5            # hourly mean sits mid-hour
    g = 2 * np.pi / 365.25 * (doy - 1 + (hour - 12) / 24)
    decl = (0.006918 - 0.399912 * np.cos(g) + 0.070257 * np.sin(g) - 0.006758 * np.cos(2 * g) + 0.000907 * np.sin(2 * g)
            - 0.002697 * np.cos(3 * g) + 0.00148 * np.sin(3 * g))
    eqt = 229.18 * (0.000075 + 0.001868 * np.cos(g) - 0.032077 * np.sin(g) - 0.014615 * np.cos(2 * g) - 0.040849 * np.sin(2 * g))
    tst = hour * 60 + eqt + 4 * lon                                          # true solar time, minutes (times are UTC)
    ha = np.radians(tst / 4 - 180)
    la = np.radians(lat)
    return np.sin(la) * np.sin(decl) + np.cos(la) * np.cos(decl) * np.cos(ha)


def clearsky_ghi(times: pd.DatetimeIndex, lat: float, lon: float) -> np.ndarray:
    """Simple clear-sky global horizontal irradiance (W/m2). Astronomy only: not a weather forecast."""
    c = np.clip(solar_zenith_cos(times, lat, lon), 0, None)
    return np.where(c > 0.02, 1098 * c * np.exp(-0.057 / np.maximum(c, 0.02)), 0.0)


# ------------------------------------------------------------------ physics
def pv_kw(p: Profile, ghi: np.ndarray, t2m: np.ndarray) -> np.ndarray:
    cell = t2m + 0.03 * ghi
    return np.clip(p.pv_kwp * ghi / 1000 * p.pv_pr * (1 + p.pv_temp_coeff * (cell - 25)), 0, p.pv_kwp)


def wind_power_kw(p: Profile, v100: np.ndarray) -> np.ndarray:
    v = v100 * (p.wind_hub_m / 100.0) ** 0.14                                # power-law shear from the 100 m reanalysis level to hub height
    frac = np.clip((v - p.wind_cut_in) / (p.wind_rated_ms - p.wind_cut_in), 0, 1) ** 3
    frac = np.where(v >= p.wind_cut_out, 0.0, frac)
    return p.wind_kw * frac * p.wind_avail


def simulated_demand_kw(p: Profile, times: pd.DatetimeIndex, t2m: np.ndarray) -> np.ndarray:
    """SIMULATED: heating-driven base load with a daily and weekly pattern and persistent noise. Replace with metered data when available."""
    rng = np.random.default_rng(p.seed)
    local = times + pd.Timedelta(hours=p.tz_hours)
    hod = local.hour.values; dow = local.dayofweek.values
    daily = 0.90 + 0.25 * np.exp(-0.5 * ((hod - 13) / 4.0) ** 2) + 0.12 * np.exp(-0.5 * ((hod - 19) / 2.5) ** 2)
    weekly = np.where(dow >= 5, 0.92, 1.0)
    noise = np.empty(len(times)); e = rng.normal(0, 0.035, len(times)); noise[0] = 0
    for i in range(1, len(times)): noise[i] = 0.9 * noise[i - 1] + e[i]
    heat = p.heat_kw_per_c * np.maximum(0, p.hdd_base_c - t2m)
    return np.maximum((p.base_kw + heat) * daily * weekly * (1 + noise), 0.3 * p.base_kw)


@dataclass
class World:
    """Aligned hourly arrays for one profile. All series share `times` (UTC)."""
    profile: Profile
    times: pd.DatetimeIndex
    t2m: np.ndarray; ghi: np.ndarray; wind100: np.ndarray
    demand: np.ndarray; pv: np.ndarray; wind: np.ndarray; csky: np.ndarray
    solar_cf: np.ndarray = field(init=False); wind_cf: np.ndarray = field(init=False)

    def __post_init__(self):
        self.solar_cf = self.pv / max(self.profile.pv_kwp, 1e-9); self.wind_cf = self.wind / max(self.profile.wind_kw, 1e-9)

    def idx(self, date: str) -> int:
        return int(self.times.get_indexer([pd.Timestamp(date)], method="nearest")[0])


def build_world(p: Profile, weather: pd.DataFrame) -> World:
    t = weather.index
    return World(p, t, weather["t2m"].values, weather["ghi"].values, weather["wind100"].values,
                 simulated_demand_kw(p, t, weather["t2m"].values), pv_kw(p, weather["ghi"].values, weather["t2m"].values),
                 wind_power_kw(p, weather["wind100"].values), clearsky_ghi(t, p.lat, p.lon))
