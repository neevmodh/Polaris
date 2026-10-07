"""Portable analysis exports, with units, dates, provenance and model limitations."""
from html import escape
from io import BytesIO
import json
from zipfile import ZipFile, ZIP_DEFLATED

def metadata(info, result):
    return {"site": info["name"], "gas": info["gas"], "unit": info["unit"],
            "source": info.get("url", "User CSV"), "sha256": info.get("sha256"),
            "retrieved_at": info.get("retrieved_at"), "selected_model": result["selected"],
            "latitude": info.get("latitude"), "longitude": info.get("longitude"),
            "validation_winner": result["validation_winner"], "split": result["split"],
            "interval": "Nominal 90% absolute-error bands calibrated before test; temporal coverage is not guaranteed.",
            "scope": info.get("scope", "Daily dry-air concentration at one station; not emissions, street-level exposure or a spatial interpolation."),
            "source_kind": info.get("origin"), "source_variable": info.get("variable"),
            "grid_bounds": info.get("grid_bounds"), "license": info.get("license"),
            "citation": info.get("citation", "User-supplied daily observations.")}

def forecast_csv(info, result):
    f = result["forecast"].copy()
    f.insert(1, "gas", info["gas"])
    f.insert(2, "unit", info["unit"])
    f.insert(3, "station", info["name"])
    f.insert(4, "forecast_origin", result["split"]["last_observation"])
    f.insert(5, "model", result["selected"])
    if info.get('variable'):
        f['source_variable']=info['variable']
        f['source_kind']=info['origin']
        f['grid_latitude']=info['grid_latitude']
        f['grid_longitude']=info['grid_longitude']
    return f.to_csv(index=False).encode()

def html_report(info, result):
    meta = metadata(info, result)
    end = result["forecast"].iloc[-1]
    metrics = result["metrics"].copy()
    metrics["coverage_90"] = (metrics.coverage_90 * 100).round(1).astype(str) + "%"
    return f"""<!doctype html><html><head><meta charset='utf-8'><title>Atmos / {escape(info['name'])}</title>
    <style>body{{max-width:1000px;margin:60px auto;padding:24px;background:#0c151a;color:#eaf2ee;font:15px/1.6 system-ui}}
    h1{{font:56px Georgia}}h2{{color:#c7ed9f}}table{{border-collapse:collapse;width:100%;font-size:12px}}
    td,th{{padding:9px;border-bottom:1px solid #33444b}}.card{{padding:24px;background:#15232a;border-radius:16px}}
    a{{color:#c7ed9f}}pre{{white-space:pre-wrap}}</style></head><body><p>POLARIS / TASK 01 / ATMOSPHERIC INTELLIGENCE</p>
    <h1>Atmos. Forecast report</h1><div class='card'><h2>{escape(info['name'])} · {escape(info['gas'].upper())}</h2>
    <p>Model: {escape(result['selected'])} · Forecast origin: {meta['split']['last_observation']}</p>
    <p>On {end['date'].date()}: <strong>{end['predicted']:.2f} {info['unit']}</strong><br>
    Nominal 90% band: {end['lower']:.2f}–{end['upper']:.2f} {info['unit']}</p></div>
    <h2>Forecast</h2>{result['forecast'][['date','predicted','lower','upper']].round(3).to_html(index=False)}
    <h2>Chronological holdout</h2>{metrics.round(3).to_html(index=False)}
    <h2>Reproducibility & scope</h2><pre>{escape(json.dumps(meta, indent=2))}</pre></body></html>"""

def export_bundle(info, result, observations):
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as z:
        z.writestr("forecast.csv", forecast_csv(info, result))
        z.writestr("holdout_metrics.csv", result["metrics"].to_csv(index=False))
        z.writestr("backtest.csv", result["backtest"].to_csv(index=False))
        z.writestr("observations.csv", observations.to_csv(index=False))
        z.writestr("provenance.json", json.dumps(metadata(info, result), indent=2))
        z.writestr("report.html", html_report(info, result))
    return output.getvalue()
