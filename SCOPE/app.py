import json, pandas as pd, plotly.graph_objects as go, streamlit as st
from pathlib import Path
from carbon import calculator as C, scope3 as S3, abatement as A, factors as F

st.set_page_config(page_title="Polaris Carbon Estimator", layout="wide")
st.title("Carbon Footprint Estimator: Scope 1 / 2 / 3")
st.caption("Team CarbonIQ · Greenovators Hackathon 2026 · Track 3 Net Zero AI Architecture")

models_ok = Path("models/model_s1.joblib").exists()
if models_ok:
    from carbon.predict import predict, data_source, _load
    src = data_source()
    if src == "SYNTHETIC":
        st.warning("ML models were trained on SYNTHETIC data (illustrative). Metrics demonstrate the pipeline, not real accuracy.")

ml_est = None
tab1, tab2, tab3, tab4 = st.tabs(["1 · Calculator", "2 · ML gap-filler", "3 · Abatement & MACC", "4 · Model report"])

with tab1:
    c1, c2 = st.columns(2)
    diesel = c1.number_input("Diesel (L/yr)", 0, 50_000_000, 84_000, step=1000)
    kwh = c1.number_input("Grid electricity (kWh/yr)", 0, 500_000_000, 500_000, step=10_000)
    td = c2.slider("T&D loss gross-up (0 = published CEA figure)", 0.0, 0.25, 0.0, help="CEA factors are generation-side. ~17-20% India T&D losses if you want consumption-side.")
    st.markdown("**Purchased goods & services spend (₹ lakh/yr)**")
    spend = {}
    cols = st.columns(4)
    for i, (k, (_, label, cat)) in enumerate(S3.CATEGORIES.items()):
        spend[k] = cols[i % 4].number_input(label, 0, 10**7, {"steel": 50, "freight": 40, "it_services": 30}.get(k, 0), key=k, help=cat) * 1e5
    fp = C.footprint({"diesel_l": diesel}, kwh, spend, td)
    mc = C.monte_carlo({"diesel_l": diesel}, kwh, spend, td_loss=td)
    m = st.columns(4)
    pt = {"scope1": fp.scope1_t, "scope2": fp.scope2_t, "scope3": fp.scope3_t, "total": fp.total_t}
    for col, (lab, key) in zip(m, [("Scope 1", "scope1"), ("Scope 2", "scope2"), ("Scope 3", "scope3"), ("Total", "total")]):
        col.metric(f"{lab} tCO₂e/yr", f"{pt[key]:,.0f}", f"P5–P95: {mc[key]['p5']:,.0f}–{mc[key]['p95']:,.0f}", delta_color="off")
    bar = go.Figure(go.Bar(x=["Scope 1", "Scope 2", "Scope 3"], y=[pt[k] for k in ("scope1", "scope2", "scope3")],
                           error_y=dict(type="data", symmetric=False,
                                        array=[max(mc[k]["p95"] - pt[k], 0) for k in ("scope1", "scope2", "scope3")],
                                        arrayminus=[max(pt[k] - mc[k]["p5"], 0) for k in ("scope1", "scope2", "scope3")])))
    bar.update_layout(yaxis_title="tCO₂e / yr (point estimate, 5–95% Monte-Carlo range)")
    st.plotly_chart(bar, width="stretch")
    if sum(spend.values()):
        st.dataframe(S3.breakdown(spend).round(1), hide_index=True)
    st.caption("Scope 2: CEA v22 grid factor 0.675 kgCO₂/kWh (FY2025-26). Scope 3: EPA USEEIO v1.3 US factors applied to Indian spend (approximate, ±50% σ).")

with tab2:
    if not models_ok:
        st.info("Run `make train` first.")
    else:
        b = _load("s1")
        c1, c2, c3 = st.columns(3)
        sector = c1.selectbox("Sector", b["sectors"])
        acts = [a for a in b["activities"] if a.startswith(sector)] or b["activities"]
        act = c1.selectbox("Activity", acts)
        turn = c2.number_input("Turnover (₹ crore)", 1.0, 1e7, 2000.0)
        emp = c2.number_input("Employees (0 = unknown)", 0, 10**7, 0)
        ren = c3.slider("Renewable electricity share", 0.0, 0.95, 0.1)
        p = predict(sector, act, turn, emp or None, ren)
        ml_est = p
        for w in p["warnings"]: st.warning(w)
        k = st.columns(2)
        for col, (t, lab) in zip(k, (("s1", "Scope 1"), ("s2", "Scope 2"))):
            col.metric(f"{lab} (tCO₂e/yr)", f"{p[t]['point']:,.0f}", f"90% interval {p[t]['lo']:,.0f} – {p[t]['hi']:,.0f}", delta_color="off")
        st.caption(f"Models: Scope 1 = {p['s1']['model']}, Scope 2 = {p['s2']['model']}. Intervals are Mondrian split-conformal (per-sector, guaranteed ≈90% coverage on exchangeable data). "
                   "Use when a facility has no metered fuel/electricity data. Scope 3 is not ML-estimated (too little reported data).")

with tab3:
    base = st.radio("Baseline for Scope 1 and 2", ["Calculator inputs (tab 1)", "ML estimate (tab 2)"], horizontal=True, disabled=ml_est is None)
    use_ml = ml_est is not None and base.startswith("ML")
    st.caption("ML baseline assumes all Scope 1 is diesel and all Scope 2 is grid electricity." if use_ml else
               f"Baseline from tab 1: diesel {diesel:,} L, grid {kwh:,} kWh, Scope 3 {fp.scope3_t:,.0f} tCO₂e.")
    c = st.columns(4)
    saved = c[0].slider("Polaris diesel saving", 0.0, 0.5, 0.268, help="Illustrative 26.8% from the proposal; replace with the simulated result")
    sol = c[1].number_input("New solar (kWh/yr)", 0, 100_000_000, 150_000)
    ppa = c[2].slider("Green PPA share of remaining grid kWh", 0.0, 1.0, 0.2)
    sup = c[3].slider("Supplier-engagement cut of Scope 3", 0.0, 0.5, 0.10)
    fuelp = st.number_input("Diesel price ₹/L", 1, 500, 80)
    if use_ml:
        d_l = ml_est["s1"]["point"] * 1000 / F.FUEL_EF["diesel_l"]
        kwh2 = ml_est["s2"]["point"] * 1000 * (1 - td) / F.GRID_EF_KG_PER_KWH
    else:
        d_l, kwh2 = diesel, kwh
    s3t = fp.scope3_t
    lev = A.build_levers(d_l, kwh2, s3t, saved, fuelp, sol, 3.5, 8.0, ppa, 0.5, sup)
    mc_ = A.macc(lev)
    fig = go.Figure()
    x0 = 0
    for _, r in mc_.iterrows():
        fig.add_trace(go.Bar(x=[x0 + r.abatement_t / 2], y=[r.cost_inr_per_t], width=[r.abatement_t], name=r["name"]))
        x0 += r.abatement_t
    fig.update_layout(title="Marginal abatement cost curve (₹ per tCO₂e; below zero = saves money)", xaxis_title="Annual abatement tCO₂e", yaxis_title="₹/tCO₂e", barmode="overlay")
    st.plotly_chart(fig, width="stretch")
    st.dataframe(mc_.round(1), hide_index=True)
    s1b = d_l * F.FUEL_EF['diesel_l'] / 1000; s2b = C.scope2(kwh2, td_loss=td)
    path = A.pathway(s1b, s2b, s3t, lev)
    f2 = go.Figure()
    for col, nm, dash in (("bau", "Business as usual", "dot"), ("with_levers", "With levers", "solid")):
        f2.add_trace(go.Scatter(x=path.year, y=path[f"{col}_p50"], name=nm, line=dict(dash=dash)))
        f2.add_trace(go.Scatter(x=list(path.year) + list(path.year[::-1]), y=list(path[f"{col}_p90"]) + list(path[f"{col}_p10"][::-1]),
                                fill="toself", opacity=.15, line=dict(width=0), showlegend=False, hoverinfo="skip"))
    f2.add_trace(go.Scatter(x=path.year, y=path.sbti_1p5C_line, name="SBTi 1.5°C-aligned (−4.2%/yr)", line=dict(dash="dash", color="gray")))
    f2.update_layout(title="Pathway 2026–2050 (P10–P90 Monte Carlo)", yaxis_title="tCO₂e/yr")
    st.plotly_chart(f2, width="stretch")
    st.metric("Cumulative abated 2026–2030 (median)", f"{A.cumulative_abated(path):,.0f} tCO₂e")
    st.caption("All lever efficacies and costs are illustrative assumptions; grid decarbonisation drawn from triangular(1%, 2.5%, 4%)/yr.")

with tab4:
    if Path("results/metrics.json").exists():
        rep = json.load(open("results/metrics.json"))
        st.write(f"Data source: **{rep['data_source']}** · split by company (train / calibration / test, no company in two sets)")
        cmp_ = pd.read_csv("results/model_comparison.csv")
        st.markdown("**Model comparison** (log-space RMSE; `overfit_ratio` = test/train, flagged above 1.5)")
        st.dataframe(cmp_[[c for c in ["target","model","train_rmse_log","cv_rmse_log","rmse_log","overfit_ratio_test_over_train","r2_log","median_pct_error"] if c in cmp_]].round(3), hide_index=True)
        for t in ("s1", "s2"):
            r = rep[t]
            st.markdown(f"**{t.upper()}** best = `{r['best_model']}` · RMSE vs sector-median baseline {r['improvement_vs_baseline_rmse_pct']:+.1f}% · "
                        f"95% CI [{r['improvement_95ci_pct'][0]:.0f}%, {r['improvement_95ci_pct'][1]:.0f}%] · intervals: {r['interval_method']} · coverage {r['interval_coverage_test']:.2%} (target {r['target_coverage']:.0%}) · worst-sector {r['worst_sector_coverage']:.2%}"
                        + (f" · out-of-time RMSE {r['out_of_time_2024plus']['model_rmse_log']:.2f} vs baseline {r['out_of_time_2024plus']['baseline_rmse_log']:.2f}" if r.get('out_of_time_2024plus') else ""))
            a, b2 = st.columns(2)
            for p_, col in ((f"results/pred_vs_actual_{t}.png", a), (f"results/shap_{t}.png", b2)):
                if Path(p_).exists(): col.image(p_)
    else:
        st.info("Run `make train`.")
