"""Interactive workspace panels; scientific calculations stay in separate modules."""
from datetime import date
from pathlib import Path
import hashlib
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit_folium import st_folium
from rasterio.warp import transform_bounds
from .scenes import Scene, from_geotiff, assert_aligned, validate_bbox
from .exports import rgb, overlay, json_text, png_bytes
from .views import swipe_html, selection_map, scene_map
from .workspace import (drawn_bbox, analysis_key, region_records, load_reviews, save_review,
                        reviewed_geojson, REVIEW_STATES, timeline_frame, timeline_key)
from .image_inputs import read_rgb, compare_rgb, rgb_package


def map_input(preset, kind):
    st.subheader("Draw your observation region")
    st.caption("Zoom or pan to a location, select the rectangle tool, and draw a compact area. The displayed bounds update only when you apply the selection.")
    try:
        bounds = list(map(float, st.session_state.get(f"bounds_{kind}", ",".join(map(str, preset["bbox"]))).split(",")))
        validate_bbox(bounds)
    except ValueError:
        bounds = preset["bbox"]
    state = st_folium(selection_map(bounds), height=380, use_container_width=True,
                      returned_objects=["all_drawings"], key=f"aoi_{kind}") or {}
    drawings = state.get("all_drawings") or []
    if drawings:
        try:
            bounds = drawn_bbox(drawings[-1])
            st.caption("Drawn bounds: " + ", ".join(f"{x:.5f}" for x in bounds))
            if st.button("Use this map selection", type="primary"):
                st.session_state[f"bounds_{kind}"] = ", ".join(f"{x:.6f}" for x in bounds)
                st.rerun()
        except ValueError as exc:
            st.error(str(exc))
    st.caption("Basemap: OpenStreetMap contributors. Basemap tiles need internet access; satellite calculations use the selected imagery.")


def rgb_input(root, kind):
    st.subheader("Image comparison studio")
    st.caption("Upload two aligned views of the same area. PNG and JPEG support visible-color screening; multispectral GeoTIFFs enable the satellite models.")
    a, b = st.columns(2)
    with a:
        first = st.file_uploader("Before image", type=["png", "jpg", "jpeg"], key="rgb_before")
    with b:
        second = st.file_uploader("After image", type=["png", "jpg", "jpeg"], key="rgb_after")
    demo = st.toggle("Try the prepared satellite RGB example", value=True) if not (first or second) else False
    if first or second:
        unreadable = False
        for col, uploaded in [(a, first), (b, second)]:
            if uploaded:
                with col:
                    try:
                        st.image(uploaded.getvalue(), caption=uploaded.name, width="stretch")
                    except Exception:      # Pillow raises its own error type for corrupt or non-image bytes
                        st.error(f"{uploaded.name} could not be read as a PNG or JPEG image.")
                        unreadable = True
        if unreadable:
            return
        if not (first and second):
            st.info("Add the second image to compare the pair.")
            return
        raw = [first.getvalue(), second.getvalue()]
        names = [first.name, second.name]
    elif demo:
        raw = [(root / "outputs" / kind / name).read_bytes() for name in ["before.png", "after.png"]]
        names = ["Prepared baseline RGB", "Prepared comparison RGB"]
    else:
        st.info("Add both images or enable the prepared example.")
        return
    try:
        (before, vb), (after, va) = [read_rgb(x) for x in raw]
        if before.shape != after.shape:
            raise ValueError("The images have different dimensions. Align and crop them to the same view before comparing.")
        st.caption(f"Input preview · {before.shape[1]} × {before.shape[0]} pixels · {names[0]} → {names[1]}")
        identity = hashlib.sha256(raw[0] + raw[1]).hexdigest()[:16]
        mode = "upload" if first or second else "example"
        aligned = st.checkbox("These images cover the same aligned view", value=not (first or second), key=f"alignment_{mode}_{identity}")
        if not aligned:
            st.info("Confirm that the views are aligned before interpreting pixel changes.")
            st.iframe(swipe_html(before, after, *names), height=425)
            return
        c1, c2 = st.columns(2)
        threshold = c1.slider("Visible-color change sensitivity", .04, .35, .12, .01)
        patch = c2.slider("RGB minimum patch · pixels", 1, 100, 8)
        result = compare_rgb(before, after, vb & va, threshold, patch)
        s = result["summary"]
        cols = st.columns(3)
        cols[0].metric("Visible change", f"{s['changed_pct']:.1f}%")
        cols[1].metric("Before green pixels", f"{s['green_before_pct']:.1f}%")
        cols[2].metric("After green pixels", f"{s['green_after_pct']:.1f}%")
        show = st.toggle("Overlay visible-change candidates", value=True)
        st.iframe(swipe_html(before, result["overlay"] if show else after, *names), height=425)
        st.info(s["interpretation"])
        st.download_button("Download RGB comparison", rgb_package(before, after, result),
                           "polaris_rgb_comparison.zip", "application/zip", type="primary")
    except (ValueError, OSError) as exc:
        st.error(f"Could not compare these images: {exc}")


def input_preview(before, after, root, kind):
    with st.expander("Input images & band inspector"):
        key = st.selectbox("Preview band", ["True color", "B02 · Blue", "B03 · Green", "B04 · Red", "B08 · Near infrared", "B11 · SWIR 1", "B12 · SWIR 2", "B05 · Red edge", "SCL · Quality classes"])
        for col, scene, title in zip(st.columns(2), [before, after], ["Baseline", "Comparison"]):
            with col:
                if key == "True color":
                    st.image(rgb(scene), caption=f"{title} · {scene.metadata['id']}", width="stretch")
                else:
                    idx = ["B02", "B03", "B04", "B08", "B11", "B12", "B05", "SCL"].index(key.split(" · ")[0])
                    values = scene.data[idx] if idx == 7 else np.where(scene.valid, scene.data[idx], np.nan)
                    fig = go.Figure(go.Heatmap(z=values, colorscale="Viridis"))
                    fig.update_layout(height=270, margin=dict(l=0, r=0, t=20, b=0), title=title)
                    st.plotly_chart(fig, width="stretch", key=f"input_band_{title}")
                st.caption(f"{scene.shape[1]} × {scene.shape[0]} · 8 bands · {100 * scene.valid.mean():.1f}% clear pixels")
        st.caption("For uploaded GeoTIFFs, dates, CRS, band order, reflectance encoding and pixel alignment are checked before analysis.")
        for col, name in zip(st.columns(2), ["before_8band.tif", "after_8band.tif"]):
            path = root / "outputs" / kind / name
            if path.exists():
                col.download_button("Download example " + name, path.read_bytes(), name, "image/tiff")


def review_panel(before, after, result, kind, root):
    st.subheader("Review the regions that matter")
    mask = result["loss"] if kind == "forest" else result["alerts"]
    rows, groups = region_records(mask, after, result["delta"], result.get("scores"))
    key = analysis_key(before, after, mask)
    path = root / "data" / "reviews" / f"{key}.json"
    reviews = load_reviews(path)
    if st.session_state.get("review_notice"):
        st.success(st.session_state.pop("review_notice"))
    if rows.empty:
        st.info("No candidate regions meet the current thresholds.")
        return None
    statuses = [reviews.get(str(int(i)), {}).get("status", "Needs review") for i in rows.region]
    queue = rows.assign(status=statuses)
    count = sum(s != "Needs review" for s in statuses)
    st.caption(f"{len(rows)} regions · {count} reviewed · {len(rows) - count} pending. Decisions are human screening notes, not independently verified findings.")
    status_filter = st.selectbox("Review status filter", ["All"] + REVIEW_STATES)
    available = queue if status_filter == "All" else queue[queue.status == status_filter]
    if available.empty:
        st.info("No regions have this review status.")
    else:
        rid = st.selectbox("Select a region", available.region.astype(int).tolist(),
                           format_func=lambda i: f"Region {i} · {float(queue.loc[queue.region == i, 'area_ha'].iloc[0]):.2f} ha", key=f"rid_{key}")
        selected = queue.loc[queue.region == rid].iloc[0]
        st.caption(f"{selected.latitude:.5f}°, {selected.longitude:.5f}° · mean index change {selected.mean_index_change:.3f}" +
                   (f" · mean model score {selected.mean_model_score:.2f} (uncalibrated)" if result.get("scores") is not None else ""))
        old = reviews.get(str(rid), {})
        with st.form(f"review_{key}_{rid}"):
            state = st.selectbox("Review decision", REVIEW_STATES, index=REVIEW_STATES.index(old.get("status", "Needs review")))
            note = st.text_area("Review notes", old.get("note", ""), max_chars=2000, placeholder="Record what you see, possible confounders, and evidence needed.")
            if st.form_submit_button("Save review", type="primary"):
                save_review(path, reviews, rid, state, note)
                st.session_state["review_notice"] = f"Review saved for Region {rid}."
                st.rerun()
        geo = reviewed_geojson(groups, after, rows, reviews)
        st_folium(scene_map(after, rgb(after), geo, rid), height=370, use_container_width=True,
                  returned_objects=[], key=f"review_map_{key}_{rid}")
        with st.expander("Selected region · image detail", expanded=True):
            rr, cc = np.where(groups == rid)
            ys = slice(max(0, rr.min()-8), min(after.shape[0], rr.max()+9))
            xs = slice(max(0, cc.min()-8), min(after.shape[1], cc.max()+9))
            a, b = st.columns(2)
            a.image(rgb(before)[ys, xs], caption="Before", width="stretch")
            b.image(overlay(after, groups == rid)[ys, xs], caption="After / selected region", width="stretch")
    geo = reviewed_geojson(groups, after, rows, reviews)
    queue["note"] = [reviews.get(str(int(i)), {}).get("note", "") for i in queue.region]
    st.dataframe(queue.round(4), hide_index=True, width="stretch")
    c1, c2 = st.columns(2)
    c1.download_button("Export reviewed regions", json_text(geo), "polaris_reviewed_regions.geojson", "application/geo+json")
    c2.download_button("Export review queue CSV", queue.to_csv(index=False), "polaris_review_queue.csv", "text/csv")
    return {"regions": geo, "table_csv": queue.to_csv(index=False), "analysis_key": key}


def timeline_panel(before, after, kind, root, vegetation=.6, mndwi=0, forest_prior=None):
    st.subheader("Follow change across observations")
    key = timeline_key(before, kind)
    folder = root / "data" / "timeline" / key
    extras = [Scene.load(p) for p in sorted(folder.glob("*.npz"))] if folder.exists() else []
    with st.expander("Add a dated satellite observation"):
        method = st.radio("Add observation using", ["Upload GeoTIFF", "Fetch date window"], horizontal=True)
        if method == "Upload GeoTIFF":
            st.caption("Use the same eight-band order, projection and pixel grid as the current pair.")
            upload = st.file_uploader("Timeline GeoTIFF", type=["tif", "tiff"], key=f"timeline_upload_{key}")
            day = st.date_input("Timeline acquisition date", date(2022, 2, 1))
            encoding = st.selectbox("Timeline reflectance encoding", ["Surface reflectance (float)", "Harmonized reflectance × 10,000"])
            if st.button("Add uploaded observation", disabled=upload is None):
                try:
                    scene = from_geotiff(upload.getvalue(), 1 if encoding.startswith("Surface") else .0001, str(day), upload.name)
                    _store_observation(scene, before, after, folder)
                    st.rerun()
                except (ValueError, OSError) as exc:
                    st.error(str(exc))
        else:
            x, y = st.columns(2)
            start = x.date_input("Extra observation start", date(2022, 1, 1))
            end = y.date_input("Extra observation end", date(2022, 3, 31))
            if st.button("Fetch extra observation", type="primary"):
                try:
                    scene = acquire_extra(before, str(start), str(end))
                    _store_observation(scene, before, after, folder)
                    st.rerun()
                except Exception as exc:
                    st.error(f"Could not add this observation: {exc}")
    active = [s for s in extras if before.metadata["datetime"][:10] < s.metadata["datetime"][:10] < after.metadata["datetime"][:10]]
    if active:
        chosen = st.multiselect("Additional dates to include", [s.metadata["datetime"][:10] for s in active],
                                default=[s.metadata["datetime"][:10] for s in active], key=f"dates_{key}")
        active = [s for s in active if s.metadata["datetime"][:10] in chosen]
    try:
        table, indicators = timeline_frame([before, *active, after], kind, vegetation, mndwi, forest_prior)
    except ValueError as exc:
        st.info(str(exc))
        return None
    support = float(table.matched_support_ha.iloc[0])
    st.caption(f"{len(table)} real acquisitions · {support:,.2f} ha observed on the same support at every date. Lines connect observations; they do not establish the timing of a change between dates.")
    if len(table) == 2:
        st.info("Two observations are available. Add an intermediate acquisition to investigate when the change occurred.")
    if kind == "lake":
        st.caption("Timeline support uses the spectral open-water mask at every date, independently of the two-date U-Net option.")
    indicator = st.selectbox("Timeline indicator", indicators)
    fig = go.Figure(go.Scatter(x=table.date, y=table[indicator], mode="lines+markers", line=dict(color="#afff6b", width=3), marker=dict(size=10),
                              customdata=table[["scene", "clear_coverage_pct"]], hovertemplate="%{x}<br>Median %{y:.3f}<br>%{customdata[0]}<br>Clear %{customdata[1]:.1f}%<extra></extra>"))
    fig.update_layout(height=300, margin=dict(l=10, r=10, t=15, b=10), yaxis_title=f"Median {indicator} (unitless)", xaxis_title="Acquisition date", paper_bgcolor="#0b1110", plot_bgcolor="#141e1b")
    st.plotly_chart(fig, width="stretch", key="timeline_plot")
    st.dataframe(table.round(4), hide_index=True, width="stretch")
    chosen_scene = st.select_slider("Inspect acquisition", options=table.date.tolist())
    scene = next(s for s in [before, *active, after] if s.metadata["datetime"][:10] == chosen_scene)
    st.image(rgb(scene), caption=scene.metadata["id"], width=420)
    st.download_button("Export timeline CSV", table.to_csv(index=False), "polaris_observation_timeline.csv", "text/csv")
    return table.to_csv(index=False)


def _store_observation(scene, before, after, folder):
    assert_aligned(before, scene)
    if not before.metadata["datetime"][:10] < scene.metadata["datetime"][:10] < after.metadata["datetime"][:10]:
        raise ValueError("Choose an acquisition strictly between the baseline and comparison dates.")
    scene.save(folder / f"{scene.metadata['datetime'][:10]}.npz")


def acquire_extra(before, start, end):
    from .catalog import search, fetch_scene
    bbox = list(transform_bounds(before.crs, "EPSG:4326", *before.bounds))
    validate_bbox(bbox)
    grid = before.crs, before.transform, before.shape[1], before.shape[0]
    with st.status("Fetching a real intermediate observation…", expanded=True) as status:
        for item in search(bbox, start, end)[:3]:
            candidate = fetch_scene(item, grid, log=st.write)
            if candidate.valid.mean() >= .7:
                candidate.metadata["region"] = before.metadata.get("region", "Custom region")
                status.update(label="Observation downloaded", state="complete", expanded=False)
                return candidate
    raise ValueError("The available acquisitions have insufficient clear pixels.")
