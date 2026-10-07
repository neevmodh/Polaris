"""Small interactive map and swipe views with escaped labels and local image data."""
import base64
import html
import math
import numpy as np
import folium
from folium.plugins import Draw, Fullscreen
from rasterio.warp import transform_bounds, calculate_default_transform, reproject, Resampling
from .exports import png_bytes


def swipe_html(before, after, left_label="Before", right_label="After"):
    a, b = [base64.b64encode(png_bytes(x)).decode() for x in (before, after)]
    return f'''<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<style>*{{box-sizing:border-box}}body{{margin:0;background:#0b1110;color:#ecf4e9;font:14px sans-serif}}
.scene{{position:relative;width:100%;height:360px;overflow:hidden;background:#141e1b;border-radius:10px}}
.scene img{{position:absolute;inset:0;width:100%;height:100%;object-fit:contain}}
#top{{clip-path:inset(0 50% 0 0)}}#divider{{position:absolute;left:50%;height:100%;width:2px;background:#afff6b}}
.tag{{position:absolute;top:14px;background:#0b1110dc;padding:8px 12px;border-radius:6px}}
.left{{left:14px}}.right{{right:14px}}.controls{{display:flex;align-items:center;gap:12px;margin:14px 0}}
input{{width:100%;accent-color:#afff6b}}output{{min-width:40px}}</style></head><body>
<div class="scene"><img src="data:image/png;base64,{b}" alt="{html.escape(right_label, quote=True)}">
<img id="top" src="data:image/png;base64,{a}" alt="{html.escape(left_label, quote=True)}"><div id="divider"></div>
<span class="tag left">{html.escape(left_label)}</span><span class="tag right">{html.escape(right_label)}</span></div>
<div class="controls"><label for="swipe">Swipe</label><input id="swipe" type="range" min="0" max="100" value="50" aria-label="Before and after image divider"><output id="position">50%</output></div>
<script>document.getElementById('swipe').addEventListener('input',function(){{
document.getElementById('top').style.clipPath='inset(0 '+(100-this.value)+'% 0 0)';
document.getElementById('divider').style.left=this.value+'%';document.getElementById('position').textContent=this.value+'%';}});</script></body></html>'''


def selection_map(bbox):
    w, s, e, n = bbox
    m = folium.Map(location=[(s+n)/2, (w+e)/2], zoom_start=12, tiles="OpenStreetMap", control_scale=True, scroll_wheel_zoom=False)
    folium.Rectangle([[s, w], [n, e]], color="#83cb49", fill=False, tooltip="Current analysis bounds").add_to(m)
    Draw(export=False, draw_options={"rectangle": True, "polygon": False, "polyline": False,
                                    "circle": False, "marker": False, "circlemarker": False},
         edit_options={"edit": True, "remove": True}).add_to(m)
    Fullscreen().add_to(m)
    m.fit_bounds([[s, w], [n, e]])
    return m


def scene_map(scene, image, geojson=None, selected=None):
    w, s, e, n = transform_bounds(scene.crs, "EPSG:4326", *scene.bounds)
    focus = next((f for f in (geojson or {}).get("features", []) if f["properties"]["region"] == selected), None)
    if focus:
        coords = np.asarray(focus["geometry"]["coordinates"][0])
        padding = max(.001, float(np.ptp(coords, axis=0).max()) * .12)
        w, s = coords.min(axis=0) - padding
        e, n = coords.max(axis=0) + padding
    # FitBounds runs while inactive Streamlit tabs have zero width and selects
    # zoom 0. An explicit geographic view works even before the tab is visible.
    span = max(float(e-w), float(n-s), .0001)
    zoom = max(4, min(18, int(math.log2(360 / span))))
    m = folium.Map(location=[float((s+n)/2), float((w+e)/2)], zoom_start=zoom, tiles="OpenStreetMap", control_scale=True, scroll_wheel_zoom=False)
    # Reproject rather than stretching a UTM image into a geographic rectangle.
    dst, width, height = calculate_default_transform(scene.crs, "EPSG:3857", scene.shape[1], scene.shape[0], *scene.bounds)
    image = np.asarray(image)
    alpha = np.where(scene.valid, 255, 0).astype(np.uint8)
    rgba = np.dstack([image, alpha])
    projected = np.zeros((height, width, 4), dtype=np.uint8)
    for band in range(4):
        reproject(rgba[..., band], projected[..., band], src_transform=scene.transform, src_crs=scene.crs,
                  dst_transform=dst, dst_crs="EPSG:3857", resampling=Resampling.nearest)
    from rasterio.transform import array_bounds
    w, s, e, n = transform_bounds("EPSG:3857", "EPSG:4326", *array_bounds(height, width, dst))
    folium.raster_layers.ImageOverlay(projected, bounds=[[s, w], [n, e]], name="Satellite observation", opacity=.9).add_to(m)
    if geojson and geojson["features"]:
        folium.GeoJson(geojson, name="Candidate regions", style_function=lambda f: {
            "color": "#afff6b" if f["properties"]["region"] == selected else "#ff6855",
            "weight": 3 if f["properties"]["region"] == selected else 1, "fillOpacity": .1},
            tooltip=folium.GeoJsonTooltip(fields=["region", "area_ha", "status"], aliases=["Region", "Area (ha)", "Review"])).add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)
    Fullscreen().add_to(m)
    return m
