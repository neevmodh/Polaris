"""Train reproducibly outside Streamlit; write models, metrics and reports."""
import argparse
from pathlib import Path
import json
import sys
import joblib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data import manifest, read_noaa, validate_series
from src.cities import read_city, city_catalog
from src.forecast import train_and_forecast
from src.reports import export_bundle, metadata, forecast_csv

def train_one(gas, station, horizon):
    frame, info = read_city(station) if station in ('NOIDA','AHMEDABAD') else read_noaa(gas, station)
    validate_series(frame)
    result = train_and_forecast(frame, horizon)
    output = ROOT / "outputs" / f"{gas}_{station.lower()}"
    output.mkdir(parents=True, exist_ok=True)
    (output / "forecast.csv").write_bytes(forecast_csv(info, result))
    result['metrics'].to_csv(output / "metrics.csv", index=False)
    result['backtest'].to_csv(output / "backtest.csv", index=False)
    (output / "provenance.json").write_text(json.dumps(metadata(info,result),indent=2))
    (output / "analysis.zip").write_bytes(export_bundle(info,result,frame))
    joblib.dump({"models":result['models'],"metadata":metadata(info,result)},output / "models.joblib")
    score = result['metrics'][(result['metrics'].model==result['selected'])&(result['metrics'].horizon_days==horizon)]
    print(f"{gas.upper()} {station}: {result['selected']}; {horizon}-day MAE {score.mae.iloc[0]:.3f} {info['unit']}; holdout coverage {score.coverage_90.iloc[0]:.1%}", flush=True)
    return result

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--gas', choices=['co2','ch4'],default='co2')
    parser.add_argument('--station',default='NOIDA')
    parser.add_argument('--horizon',type=int,choices=[7,14,30],default=14)
    parser.add_argument('--all',action='store_true')
    args=parser.parse_args()
    if args.all:
        for entry in city_catalog():
            try:
                train_one(entry['gas'],entry['station'],args.horizon)
            except ValueError as exc:
                print(f"SKIP {entry['gas']} {entry['station']}: {exc}",flush=True)
    else:
        train_one(args.gas,args.station.upper(),args.horizon)
