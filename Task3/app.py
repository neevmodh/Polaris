"""Polaris: satellite forest-loss and lake water-quality screening dashboard."""
from pathlib import Path
from datetime import date
import hashlib
import json
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from monitor.catalog import PRESETS, fetch_pair
from monitor.scenes import Scene, from_geotiff, assert_aligned
from monitor.analysis import forest_analysis, lake_analysis
from monitor.learning import baseline_forest_prior
from monitor.exports import rgb, overlay, bundle, json_text
from monitor import water_model
from monitor.ui_features import map_input, rgb_input, input_preview, review_panel, timeline_panel
from monitor.views import swipe_html, scene_map
from streamlit_folium import st_folium

ROOT = Path(__file__).resolve().parent
st.set_page_config(page_title="Polaris · Satellite Monitor", page_icon="◈", layout="wide")
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Libre+Caslon+Display&display=swap');
html, body, [class*="css"], .stApp {font-family:'DM Sans',sans-serif;}
.block-container{padding-top:4.5rem;max-width:1500px;padding-bottom:3rem;}
[data-testid="stSidebar"]{border-right:1px solid #29372e;}
h1,h2,h3{letter-spacing:-.025em;}
.brand{font-size:22px;font-weight:700;letter-spacing:6px;}
.eyebrow{font-size:11px;letter-spacing:2.4px;color:#b0c0b4;text-transform:uppercase;}
.hero{font-family:'Libre Caslon Display',Georgia,serif;font-size:clamp(44px,5vw,76px);line-height:1.02;letter-spacing:-2px;margin:20px 0 14px;}
.hero em{color:#afff6b;font-style:normal;}
.intro{color:#a6b7ac;max-width:670px;font-size:15px;line-height:1.7;margin-bottom:25px;}
.rule{height:1px;background:#2b3931;margin:20px 0;}
.chip{display:inline-block;background:#1b2b1c;border:1px solid #486239;border-radius:20px;padding:6px 12px;color:#c5f2a8;font-size:11px;letter-spacing:1px;}
[data-testid="stMetric"]{background:#141e1b;border:1px solid #2b3931;padding:14px;border-radius:9px;min-height:106px;}
[data-testid="stMetricValue"]{font-family:Georgia,serif;font-weight:400;font-size:clamp(21px,2.3vw,38px);}
[data-testid="stMetricLabel"]{color:#a4b5a9;}
[data-testid="stMetricLabel"] p{white-space:normal;font-size:12px;}
.footer{color:#84978a;font-size:12px;border-top:1px solid #29372e;margin-top:28px;padding-top:18px;}
</style>""", unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def load_cached(path, before_mtime, after_mtime):
    return Scene.load(Path(path) / "before.npz"), Scene.load(Path(path) / "after.npz")


def image_map(image, scene, title):
    t = scene.transform
    fig = go.Figure(go.Image(z=image, x0=t.c + t.a / 2, y0=t.f + t.e / 2, dx=t.a, dy=t.e,
                             hovertemplate="Easting %{x:.0f} m<br>Northing %{y:.0f} m<extra></extra>"))
    fig.update_layout(height=350, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="#0b1110",
                      xaxis=dict(visible=False), yaxis=dict(visible=False, scaleanchor="x"), dragmode="pan")
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, key=title)


def heatmap(values, scene, title, colorscale="RdYlGn", zmin=-0.4, zmax=0.4):
    t = scene.transform
    h, w = scene.shape
    fig = go.Figure(go.Heatmap(z=values, x=t.c + (np.arange(w) + .5) * t.a,
                               y=t.f + (np.arange(h) + .5) * t.e, colorscale=colorscale,
                               zmin=zmin, zmax=zmax, colorbar=dict(thickness=10, len=.8, orientation="h", x=.5, y=-.06),
                               hovertemplate="Value %{z:.3f}<br>E %{x:.0f} / N %{y:.0f}<extra></extra>"))
    fig.update_layout(height=350, margin=dict(l=0, r=0, t=0, b=30), paper_bgcolor="#0b1110",
                      plot_bgcolor="#101a15", xaxis=dict(visible=False),
                      yaxis=dict(visible=False, scaleanchor="x"), dragmode="pan")
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, key=title)


with st.sidebar:
    st.markdown('<div class="brand">◈ POLARIS</div>', unsafe_allow_html=True)
    st.caption("SATELLITE MONITOR / TEAM CARBONIQ")
    st.markdown('<div class="rule"></div>', unsafe_allow_html=True)
    task = st.radio("Observe", ["Forest loss", "Lake water quality"])
    kind = "forest" if task == "Forest loss" else "lake"
    preset = PRESETS[kind]
    source = st.selectbox("Imagery source", ["Cached real case study", "Fetch a custom region", "Upload aligned GeoTIFFs", "Upload PNG / JPEG images"])
    st.caption("Real observations. No generated satellite data.")

pair = None
if source == "Cached real case study":
    folder = ROOT / "data" / kind
    if (folder / "before.npz").exists() and (folder / "after.npz").exists():
        pair = load_cached(str(folder), (folder / "before.npz").stat().st_mtime,
                           (folder / "after.npz").stat().st_mtime)
    else:
        st.info("The real case-study imagery has not been cached yet. Run `python scripts/bootstrap_data.py` or fetch a custom region.")
elif source == "Fetch a custom region":
    map_input(preset, kind)
    bounds_key = f"bounds_{kind}"
    if bounds_key not in st.session_state:
        st.session_state[bounds_key] = ", ".join(map(str, preset["bbox"]))
    with st.sidebar:
        st.caption("Enter a compact region. Each side must be under 0.3°.")
        bounds_text = st.text_input("West, south, east, north", key=bounds_key)
        region_name = st.text_input("Region name", "My observation region")
        bstart = st.date_input("Baseline start", date.fromisoformat(preset["before"][0]))
        bend = st.date_input("Baseline end", date.fromisoformat(preset["before"][1]))
        astart = st.date_input("Comparison start", date.fromisoformat(preset["after"][0]))
        aend = st.date_input("Comparison end", date.fromisoformat(preset["after"][1]))
        acquire = st.button("Fetch satellite imagery", type="primary", width="stretch")
    if acquire:
        try:
            try:
                bounds = [float(x) for x in bounds_text.split(",")]
            except ValueError:
                raise ValueError("Enter four numbers separated by commas: west, south, east, north (for example 93.77, 24.47, 93.83, 24.53).") from None
            key = hashlib.sha256(json.dumps([bounds, str(bstart), str(bend), str(astart), str(aend)]).encode()).hexdigest()[:16]
            folder = ROOT / "data" / "custom" / key
            with st.status("Fetching real Sentinel-2 scenes…", expanded=True) as status:
                if (folder / "before.npz").exists() and (folder / "after.npz").exists():
                    st.write("This exact request is already cached; reusing the downloaded scenes.")
                    scenes = [Scene.load(folder / "before.npz"), Scene.load(folder / "after.npz")]
                else:
                    scenes = fetch_pair(bounds, [str(bstart), str(bend)], [str(astart), str(aend)], folder, log=st.write)
                for label, scene in zip(["before", "after"], scenes):
                    scene.metadata["region"] = region_name
                    scene.save(folder / f"{label}.npz")
                status.update(label="Imagery cached. Ready to inspect.", state="complete", expanded=False)
            st.session_state["custom_folder"] = str(folder)
        except Exception as exc:
            st.error(f"Could not fetch this observation: {exc}")
    if st.session_state.get("custom_folder"):
        folder = Path(st.session_state["custom_folder"])
        pair = load_cached(str(folder), (folder / "before.npz").stat().st_mtime,
                           (folder / "after.npz").stat().st_mtime)
elif source == "Upload aligned GeoTIFFs":
    with st.sidebar:
        st.caption("Band order: B02, B03, B04, B08, B11, B12, B05, SCL. Same projected grid in metres.")
        calibration = st.selectbox("Reflectance encoding", ["Surface reflectance (float)", "Harmonized reflectance × 10,000"])
        upb = st.file_uploader("Baseline GeoTIFF", type=["tif", "tiff"], key="upload_before")
        upa = st.file_uploader("Comparison GeoTIFF", type=["tif", "tiff"], key="upload_after")
        db = st.date_input("Baseline acquisition date", date(2020, 2, 1))
        da = st.date_input("Comparison acquisition date", date(2024, 2, 1))
    if upb and upa:
        try:
            scale = 1 if calibration.startswith("Surface") else 0.0001
            pair = (from_geotiff(upb.getvalue(), scale, str(db), upb.name),
                    from_geotiff(upa.getvalue(), scale, str(da), upa.name))
            assert_aligned(*pair)
        except Exception as exc:
            st.error(str(exc))

with st.sidebar:
    st.markdown('<div class="rule"></div>', unsafe_allow_html=True)
    if source == "Upload PNG / JPEG images":
        st.caption("Visible-color screening · sensitivity controls appear beside your images.")
    elif kind == "forest":
        model_path = ROOT / "models" / "forest_rf.joblib"
        options = ["Trained random forest", "NDVI screening baseline"] if model_path.exists() else ["NDVI screening baseline"]
        detector = st.selectbox("Detection method", options)
        threshold = st.slider("ML score threshold", .1, .9, .5, .05)
        drop = st.slider("NDVI decline threshold", .05, .6, .2, .05)
        vegetation = st.slider("Baseline vegetation threshold", .3, .85, .6, .05)
        patches = st.slider("Minimum patch · pixels", 1, 30, 4)
    else:
        water_options = ["Spectral open-water mask"]
        if water_model.available():
            water_options.append("Pretrained U-Net")
        water_method = st.selectbox("Water segmentation", water_options)
        mndwi = st.slider("Open-water MNDWI threshold", -.2, .4, .0, .05)
        algae_change = st.slider("Algae proxy increase threshold", .02, .4, .1, .02)
    st.markdown('<div class="rule"></div>', unsafe_allow_html=True)
    st.caption("Greenovators 2026 · Track 3\n\nCandidate environmental changes for review.")

st.markdown('<div class="eyebrow">EARTH OBSERVATION &nbsp; / &nbsp; 03 &nbsp; / &nbsp; POLARIS</div>', unsafe_allow_html=True)
if kind == "forest":
    st.markdown('<div class="hero">See the forest.<br><em>Spot the change.</em></div>', unsafe_allow_html=True)
    st.markdown('<div class="intro">Compare satellite observations, find possible tree-cover loss, and turn changes into georeferenced regions for review.</div>', unsafe_allow_html=True)
else:
    st.markdown('<div class="hero">Look beneath<br><em>the surface.</em></div>', unsafe_allow_html=True)
    st.markdown('<div class="intro">Track optical changes in lakes using clear-water observations. Explore algae and turbidity indicators across two dates.</div>', unsafe_allow_html=True)

if source == "Upload PNG / JPEG images":
    rgb_input(ROOT, kind)
    st.stop()
if pair is None:
    st.stop()
before, after = pair
region = before.metadata.get("region", before.metadata.get("id", "Custom region"))
st.markdown('<span class="chip">REAL SATELLITE OBSERVATIONS</span>', unsafe_allow_html=True)
st.subheader(region)
st.caption(f"{before.metadata.get('datetime', '')[:10]} → {after.metadata.get('datetime', '')[:10]} · "
           f"{int(abs(before.transform.a))} m analysis grid · {before.crs}")
input_preview(before, after, ROOT, kind)
try:
    if kind == "forest":
        prior = None
        if source == "Cached real case study" and (ROOT / "data" / "forest" / "reference.npz").exists():
            with np.load(ROOT / "data" / "forest" / "reference.npz", allow_pickle=False) as z:
                prior = baseline_forest_prior(before, {k: z[k] for k in z.files})
        with st.spinner("Comparing forest observations…"):
            result = forest_analysis(before, after, drop, vegetation, patches,
                                     model_path if detector == "Trained random forest" else None, threshold, prior)
    else:
        wm = None
        if water_method == "Pretrained U-Net":
            with st.spinner("Segmenting water with the pretrained U-Net…"):
                wm = (water_model.segment(before), water_model.segment(after))
        result = lake_analysis(before, after, mndwi, algae_change, wm)
except Exception as exc:
    st.error(f"This pair could not be analyzed: {exc}")
    st.stop()

s = result["summary"]
cols = st.columns(4)
if kind == "forest":
    cols[0].metric("Candidate forest loss", f"{s['candidate_loss_area_ha']:,.1f} ha")
    cols[1].metric("Regions to review", s["alert_regions"])
    cols[2].metric("Clear paired coverage", f"{s['observed_pair_pct']:.1f}%")
    cols[3].metric("Baseline forest support" if prior is not None else "Baseline vegetation", f"{s['baseline_vegetation_area_ha']:,.0f} ha")
else:
    cols[0].metric("Comparable open water", f"{s['common_water_ha']:,.1f} ha")
    cols[1].metric("Algae proxy increase", f"{s['algae_proxy_increase_ha']:,.1f} ha")
    cols[2].metric("Clear paired coverage", f"{s['observed_pair_pct']:.1f}%")
    cols[3].metric("Observed water area", f"{s['after_open_water_ha']:,.0f} ha")
st.caption("Areas describe the clear pixels analyzed. Dark pixels are excluded observations.")
if kind == "forest":
    st.caption("Forest support: " + s["baseline_support"] + ".")
overview, timeline, review, evidence, provenance = st.tabs(["Observation workspace", "Timeline & trends", "Review queue", "Model & evidence", "Sources & exports"])
with overview:
    display = st.radio("Viewer", ["Side by side", "Swipe comparison", "Geographic map"], horizontal=True)
    if display == "Side by side":
        if kind == "forest":
            layer = st.selectbox("Comparison layer", ["Loss alerts", "True-color imagery", "NDVI change"] + (["ML score"] if result["scores"] is not None else []))
        else:
            layer = st.selectbox("Comparison layer", ["Algae proxy change", "True-color imagery", "Algae proxy", "Turbidity proxy", "Water mask"])
        left, right = st.columns(2, gap="medium")
        with left:
            st.markdown("**BASELINE / " + before.metadata.get("datetime", "")[:10] + "**")
            image_map(rgb(before), before, "baseline_rgb")
        with right:
            st.markdown("**COMPARISON / " + after.metadata.get("datetime", "")[:10] + "**")
            if layer == "Loss alerts":
                image_map(overlay(after, result["loss"]), after, "forest_overlay")
            elif layer == "True-color imagery":
                image_map(rgb(after), after, "after_rgb")
            elif layer in ["NDVI change", "Algae proxy change"]:
                heatmap(result["delta"], after, "change_map")
            elif layer == "ML score":
                heatmap(result["scores"], after, "score_map", "YlOrRd", 0, 1)
            elif layer == "Algae proxy":
                heatmap(result["after"]["NDCI"], after, "algae_map", "YlGn", -.2, .4)
            elif layer == "Turbidity proxy":
                heatmap(result["after"]["NDTI"], after, "turbidity_map", "YlOrBr", -.3, .3)
            else:
                image_map(overlay(after, result["after"]["water"], (98, 211, 234)), after, "water_map")
    elif display == "Swipe comparison":
        show_alerts = st.toggle("Show candidate changes on the comparison image", value=True)
        alert_mask = result["loss"] if kind == "forest" else result["alerts"]
        st.iframe(swipe_html(rgb(before), overlay(after, alert_mask) if show_alerts else rgb(after),
                                   before.metadata["datetime"][:10], after.metadata["datetime"][:10]), height=425)
        st.caption("Move the divider to inspect the same pixels across dates. The same reflectance stretch is used for both observations.")
    else:
        map_date = st.radio("Map observation", ["Baseline", "Comparison"], horizontal=True)
        map_scene = before if map_date == "Baseline" else after
        alert_mask = result["loss"] if kind == "forest" else result["alerts"]
        st_folium(scene_map(map_scene, rgb(map_scene) if map_date == "Baseline" else overlay(map_scene, alert_mask)),
                  height=420, use_container_width=True, returned_objects=[], key=f"geo_{kind}_{map_date}")
        st.caption("Satellite observation reprojected to the map grid. Toggle the observation layer to inspect the OpenStreetMap context; tiles require internet access.")
    st.info(s["interpretation"])
    if kind == "forest":
        st.markdown("**Largest candidate loss regions**")
        st.dataframe(result["alerts"].head(25), hide_index=True, width="stretch")
    else:
        st.markdown("**Water indicators / same clear-water pixels at both dates**")
        st.dataframe(result["table"].round(4), hide_index=True, width="stretch")
        st.caption("NDCI uses Sentinel-2 B05/B04. Turbidity indicators are ratios, not calibrated concentrations.")

with timeline:
    timeline_csv = timeline_panel(before, after, kind, ROOT, vegetation if kind == "forest" else .6,
                                  mndwi if kind == "lake" else 0, prior if kind == "forest" else None)
with review:
    reviewed = review_panel(before, after, result, kind, ROOT)

with evidence:
    if kind == "forest" and result["metrics"]:
        m = result["metrics"]
        st.subheader("A trained model, with an explicit holdout")
        st.write("The random forest learns changes in vegetation, moisture, burn indices and reflectance from Hansen tree-cover loss labels. It is evaluated on the eastern strip, separated from training pixels by a six-column gap.")
        table = pd.DataFrame([{ "Method": name, **{k: v for k, v in stats.items() if isinstance(v, (float, int))}}
                              for name, stats in [("Random forest", m["rf"]), ("NDVI baseline", m["ndvi_baseline"])]])
        st.dataframe(table.round(3), hide_index=True, width="stretch")
        st.caption(f"{m['trained_samples']:,} training samples · {m['holdout_samples']:,} held-out pixels · "
                   f"{m['holdout_positive_samples']:,} reference loss pixels in holdout · label years {m['label_interval']}")
        st.warning("This measures agreement with a satellite-derived reference in one region. It is not field accuracy or evidence that the model generalizes to another region. Scores are uncalibrated.")
        importance = pd.DataFrame({"Feature": list(m["feature_importance"]), "Importance": list(m["feature_importance"].values())}).sort_values("Importance")
        fig = go.Figure(go.Bar(x=importance["Importance"], y=importance["Feature"], orientation="h", marker_color="#afff6b"))
        fig.update_layout(height=430, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor="#0b1110", plot_bgcolor="#0b1110")
        st.plotly_chart(fig, width="stretch")
        if source != "Cached real case study":
            st.warning("This model was trained on the bundled Brazilian case study. Validate its predictions before applying it to your custom region.")
    elif kind == "forest":
        st.write("The NDVI baseline flags a vegetation-index decline in previously vegetated pixels. It is a transparent screening rule, not a trained machine-learning model.")
    else:
        st.subheader("What these observations can establish")
        st.write("A clear-water mask isolates open-water pixels. NDCI and visible-band ratios provide optical screening indicators. The optional U-Net is an upstream pretrained water-segmentation model; it does not detect pollutants.")
        st.write("Locally calibrated chlorophyll or turbidity estimates require paired field samples. No water-quality accuracy score is claimed for Loktak Lake.")
        st.caption("Water indicators are adapted from RAJohansen/waterquality. Segmentation is adapted from Iulia-plesu/lake-detection-water-quality.")

with provenance:
    st.subheader("Every observation has a source")
    for title, scene in [("Baseline", before), ("Comparison", after)]:
        with st.expander(f"{title} · {scene.metadata['id']}"):
            st.json({k: v for k, v in scene.metadata.items() if k != "stac_item"})
    mask = result["loss"] if kind == "forest" else result["alerts"]
    arrays = {"index_change": result["delta"], "review_mask": np.where(before.valid & after.valid, mask.astype(float), np.nan)}
    if kind == "forest" and result["scores"] is not None:
        arrays["ml_score"] = result["scores"]
    if kind == "lake":
        arrays.update({"ndci_after": result["after"]["NDCI"], "ndti_after": result["after"]["NDTI"]})
    extras = {}
    if timeline_csv:
        extras["observation_timeline.csv"] = timeline_csv
    if reviewed:
        extras["reviewed_regions.geojson"] = json_text(reviewed["regions"])
        extras["review_queue.csv"] = reviewed["table_csv"]
    archive = bundle(s, before, after, arrays, mask, result.get("metrics"),
                     result["table"].to_csv(index=False) if kind == "lake" else result["alerts"].to_csv(index=False), extras)
    st.download_button("Download analysis package ↗", archive, f"polaris_{kind}_analysis.zip", "application/zip", type="primary")
    st.caption("Includes report, GeoTIFF layers, GeoJSON review regions, images, calculations and source metadata.")
    st.download_button("Download summary JSON", json_text(s), f"polaris_{kind}_summary.json", "application/json")
    st.markdown("**Repository attribution**")
    st.markdown("[TerraVision](https://github.com/AwasthiAshutosh/TerraVision) · [Forest-CD](https://github.com/NightSongs/Forest-CD) · [Lake Detection](https://github.com/Iulia-plesu/lake-detection-water-quality) · [waterquality](https://github.com/RAJohansen/waterquality)")
    st.caption("See THIRD_PARTY_NOTICES.md for exact revisions, licenses, changes and which components are used. Forest-CD is a research reference; the forest model here is our own random-forest baseline.")

st.markdown('<div class="footer">POLARIS / TEAM CARBONIQ &nbsp; · &nbsp; COPERNICUS SENTINEL-2 &nbsp; · &nbsp; ENVIRONMENTAL SCREENING, WITH TRACEABLE EVIDENCE</div>', unsafe_allow_html=True)
