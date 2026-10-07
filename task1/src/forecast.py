"""Direct multi-horizon ML with strictly chronological evaluation.

All fitted preprocessing sees training observations only. Missing historical
features are forward-filled for at most three days; labels are never imputed.
The holdout uses rolling origins and frozen models, consuming only observations
available at each origin. Model selection and interval widths use calibration,
never the final test. Deployment models are then refit on all available history.
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from .data import validate_series

HORIZONS = (1, 3, 7, 10, 14, 21, 30)
MODELS = ("Seasonal Ridge", "Lag Ridge", "Random forest", "Persistence", "Seasonal persistence")
FEATURES = ["lag_0", "lag_1", "lag_2", "lag_7", "lag_14", "lag_30", "lag_365",
            "mean_7", "mean_30", "std_7", "change_7", "horizon", "target_sin", "target_cos"]

def calendar(dates):
    days = (pd.DatetimeIndex(dates) - pd.Timestamp("2000-01-01")).days.to_numpy() / 365.25
    t = (days - 20) / 10
    return np.column_stack([t, t * t, np.sin(2*np.pi*days), np.cos(2*np.pi*days),
                            np.sin(4*np.pi*days), np.cos(4*np.pi*days)])

def base_fit(series, cutoff):
    fit = series.loc[(series.index < cutoff) & (series.index >= cutoff - pd.Timedelta(days=1461))].dropna()
    return make_pipeline(StandardScaler(), Ridge(alpha=1.0)).fit(calendar(fit.index), fit.to_numpy())

def historical_features(series, base):
    # Causal fill only: no interpolation, backfill or full-series scaling.
    residual = (series.ffill(limit=3) - base.predict(calendar(series.index)))
    f = pd.DataFrame(index=series.index)
    for lag in (0, 1, 2, 7, 14, 30, 365):
        f[f"lag_{lag}"] = residual.shift(lag)
    f["mean_7"] = residual.rolling(7, min_periods=5).mean()
    f["mean_30"] = residual.rolling(30, min_periods=20).mean()
    f["std_7"] = residual.rolling(7, min_periods=5).std()
    f["change_7"] = residual - residual.shift(7)
    # Annual lag is useful when present; zero means fitted seasonal expectation.
    f["lag_365"] = f["lag_365"].fillna(0.0)
    return f

def design(series, base, horizons=HORIZONS):
    origins = historical_features(series, base)
    blocks = []
    for h in horizons:
        block = origins.copy()
        target = block.index + pd.Timedelta(days=h)
        block["origin"] = block.index
        block["target"] = target
        block["horizon"] = h
        cyc = calendar(target)
        block["target_sin"], block["target_cos"] = cyc[:, 2], cyc[:, 3]
        block["actual"] = series.reindex(target).to_numpy()
        block["baseline"] = base.predict(cyc)
        block["current"] = series.reindex(block.index).to_numpy()
        block["base_origin"] = base.predict(calendar(block.index))
        blocks.append(block)
    return pd.concat(blocks, ignore_index=True).dropna(subset=FEATURES + ["actual", "current"])

def fit_models(rows):
    if len(rows) < 700:
        raise ValueError("Not enough contiguous recent observations after lag construction. Use a denser daily dataset.")
    x = rows[FEATURES].to_numpy()
    y = (rows.actual - rows.baseline).to_numpy()
    ridge = make_pipeline(StandardScaler(), Ridge(alpha=50.0)).fit(x, y)
    forest = RandomForestRegressor(n_estimators=100, max_depth=14, min_samples_leaf=10,
                                   max_samples=0.8, random_state=42, n_jobs=2).fit(x, y)
    return {"Lag Ridge": ridge, "Random forest": forest}

def predict_rows(rows, fitted):
    x = rows[FEATURES].to_numpy()
    result = {"Seasonal Ridge": rows.baseline.to_numpy(), "Persistence": rows.current.to_numpy(),
              "Seasonal persistence": (rows.current + rows.baseline - rows.base_origin).to_numpy()}
    for name, estimator in fitted.items():
        result[name] = rows.baseline.to_numpy() + estimator.predict(x)
    return result

def interval_width(errors):
    # Finite-sample absolute residual quantile; temporal dependence still limits guarantees.
    n = len(errors)
    q = min(1.0, np.ceil((n + 1) * 0.90) / n)
    return float(np.quantile(np.abs(errors), q, method="higher"))

def train_and_forecast(frame, horizon=14, requested="Auto (validation winner)"):
    if not isinstance(horizon, int) or not 1 <= horizon <= 30:
        raise ValueError("Forecast horizon must be between 1 and 30 days.")
    if requested not in (*MODELS, "Auto (validation winner)"):
        raise ValueError("Unknown forecasting model.")
    validate_series(frame)
    recent = frame[frame.date >= frame.date.max() - pd.Timedelta(days=365*8)]
    series = recent.set_index("date").value.asfreq("D")
    n = len(series)
    train_end = series.index[int(n * .72)]
    test_start = series.index[int(n * .86)]
    base = base_fit(series, train_end)
    rows = design(series, base)
    # A training label must occur before the calibration boundary. Purge forecast windows
    # across both boundaries; calibration/test origins themselves start at the boundary.
    train = rows[rows.target < train_end]
    cal = rows[(rows.origin >= train_end) & (rows.target < test_start)]
    test = rows[rows.origin >= test_start]
    if len(cal) < 70 or len(test) < 70:
        raise ValueError("Too few observations in the calibration/test periods. Check recent data coverage.")
    fitted = fit_models(train)
    cal_predictions = predict_rows(cal, fitted)
    test_predictions = predict_rows(test, fitted)
    cal_scores = {name: float(np.sqrt(np.mean((cal.actual.to_numpy() - values)**2)))
                  for name, values in cal_predictions.items()}
    # Auto selects an actual trained ML estimator; baselines remain visible for comparison.
    winner = min(MODELS[:3], key=cal_scores.get)
    selected = winner if requested == "Auto (validation winner)" else requested
    widths = {}
    metrics, traces = [], []
    for name in MODELS:
        for h in HORIZONS:
            cmask, tmask = (cal.horizon == h).to_numpy(), (test.horizon == h).to_numpy()
            if cmask.sum() < 10 or tmask.sum() < 10:
                raise ValueError("Each horizon needs at least 10 calibration and 10 holdout targets.")
            cerrors = cal.loc[cmask, "actual"].to_numpy() - cal_predictions[name][cmask]
            width = interval_width(cerrors)
            widths[name, h] = width
            errors = test.loc[tmask, "actual"].to_numpy() - test_predictions[name][tmask]
            metrics.append({"model": name, "horizon_days": h, "mae": float(np.abs(errors).mean()),
                            "rmse": float(np.sqrt(np.mean(errors**2))),
                            "coverage_90": float((np.abs(errors) <= width).mean()),
                            "test_targets": int(tmask.sum()), "calibration_targets": int(cmask.sum()),
                            "calibration_rmse": float(np.sqrt(np.mean(cerrors**2)))})
            trace = test.loc[tmask, ["origin", "target", "actual", "horizon"]].copy()
            trace["model"], trace["predicted"] = name, test_predictions[name][tmask]
            trace["lower"], trace["upper"] = trace.predicted - width, trace.predicted + width
            traces.append(trace)
    # Refit for deployment, after unbiased holdout metrics are fixed.
    final_base = base_fit(series, series.index.max() + pd.Timedelta(days=1))
    final_rows = design(series, final_base)
    final_models = fit_models(final_rows)
    features = historical_features(series, final_base)
    origin = series.index.max()
    if features.loc[origin].isna().any():
        raise ValueError("Missing recent lag values prevent forecasting. Add valid observations for the last month.")
    future_dates = pd.date_range(origin + pd.Timedelta(days=1), periods=horizon, freq="D")
    future = pd.DataFrame(np.tile(features.loc[origin].to_numpy(), (horizon, 1)), columns=features.columns)
    future["horizon"] = np.arange(1, horizon + 1)
    c = calendar(future_dates)
    future["target_sin"], future["target_cos"] = c[:, 2], c[:, 3]
    future["baseline"] = final_base.predict(c)
    future["current"] = float(series.iloc[-1])
    future["base_origin"] = final_base.predict(calendar([origin]))[0]
    predictions = predict_rows(future, final_models)
    forecast = pd.DataFrame({"date": future_dates})
    for name, values in predictions.items():
        forecast[name] = values
    forecast["predicted"] = predictions[selected]
    # Conservative next evaluated horizon avoids underestimating interpolated widths.
    band = np.array([widths[selected, next(h for h in HORIZONS if h >= d)]
                     for d in range(1, horizon + 1)])
    forecast["lower"], forecast["upper"] = forecast.predicted - band, forecast.predicted + band
    importance = pd.DataFrame({"feature": FEATURES, "importance": final_models["Random forest"].feature_importances_})
    return {"forecast": forecast, "metrics": pd.DataFrame(metrics), "backtest": pd.concat(traces, ignore_index=True),
            "importance": importance.sort_values("importance", ascending=False), "selected": selected,
            "validation_winner": winner, "validation_scores": cal_scores,
            "split": {"train_start": str(series.index.min().date()), "train_end_exclusive": str(train_end.date()),
                      "test_start": str(test_start.date()), "last_observation": str(origin.date()),
                      "training_rows": len(train), "calibration_rows": len(cal), "test_rows": len(test)},
            "interval_widths": widths, "models": {"base": final_base, **final_models}}

def forecast_view(result, horizon=14, requested="Auto (validation winner)"):
    """Switch presentation without retraining or mixing model-specific intervals."""
    if horizon not in (7, 14, 30):
        raise ValueError("Choose a 7-, 14- or 30-day horizon.")
    selected = result['validation_winner'] if requested == "Auto (validation winner)" else requested
    if selected not in MODELS:
        raise ValueError("Unknown forecasting model.")
    forecast = result['forecast'].iloc[:horizon].copy()
    if len(forecast) != horizon:
        raise ValueError("Train a 30-day result before selecting a shorter forecast view.")
    forecast['predicted'] = forecast[selected]
    band = np.array([result['interval_widths'][selected, next(h for h in HORIZONS if h >= d)]
                     for d in range(1, horizon + 1)])
    forecast['lower'], forecast['upper'] = forecast.predicted - band, forecast.predicted + band
    return {**result, 'selected': selected, 'forecast': forecast}
