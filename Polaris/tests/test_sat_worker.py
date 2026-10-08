"""End-to-end tests of the satellite worker over its real JSON-lines protocol.
Run with Task3's interpreter:  ../Task3/.venv/bin/python -m pytest -q tests"""
import base64, json, os, subprocess, sys, threading, time, zipfile
from io import BytesIO
from pathlib import Path
import pytest

HERE = Path(__file__).resolve().parents[1]
TASK3 = HERE.parent / "Task3"
pytestmark = pytest.mark.skipif(not (TASK3 / ".venv/bin/python").exists(), reason="Task3 environment not found")


class Client:
    def __init__(self, data_dir):
        env = {**os.environ, "POLARIS_DATA": str(data_dir)}
        self.p = subprocess.Popen([str(TASK3 / ".venv/bin/python"), str(HERE / "engines/sat_worker.py")], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, env=env, cwd=TASK3)
        assert json.loads(self.p.stdout.readline())["ready"]
        self.n, self.lock, self.out, self.ev = 0, threading.Lock(), {}, {}
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self.p.stdout:
            m = json.loads(line); self.out[m["id"]] = m; self.ev[m["id"]].set()

    def call(self, cmd, args=None, timeout=300, raw=False):
        with self.lock: self.n += 1; i = self.n; self.ev[i] = threading.Event()
        self.p.stdin.write(json.dumps({"id": i, "cmd": cmd, "args": args or {}}) + "\n"); self.p.stdin.flush()
        assert self.ev[i].wait(timeout), f"{cmd} timed out"
        m = self.out[i]
        return m if raw else (m["result"] if m["ok"] else pytest.fail(m["error"]))

    def close(self): self.p.kill()


@pytest.fixture(scope="module")
def w(tmp_path_factory):
    c = Client(tmp_path_factory.mktemp("polaris-data")); yield c; c.close()


def test_cases_and_model_availability(w):
    m = w.call("meta")
    ids = {c["id"] for c in m["cases"]}; assert ids == {"forest", "lake"} and all("error" not in c for c in m["cases"])
    assert m["forest_model"] and m["metrics"]["rf"]["f1"] > m["metrics"]["ndvi_baseline"]["f1"]
    assert m["review_states"][0] == "Needs review"


def test_forest_matches_the_project_validation_file(w):
    r = w.call("analyze", {"kind": "forest", "case": "forest", "layer": "alerts"})
    s = r["summary"]
    assert s["method"] == "Trained random forest" and s["candidate_loss_area_ha"] == 245.43 and s["alert_regions"] == 84
    assert s["observed_pair_pct"] == 99.79 and r["scores_available"] and r["prior_used"]
    assert r["image"].startswith("data:image/png;base64,") and r["size"] == [295, 297]


def test_baseline_differs_from_forest_and_params_matter(w):
    rf = w.call("analyze", {"kind": "forest", "case": "forest"})["summary"]["candidate_loss_area_ha"]
    nd = w.call("analyze", {"kind": "forest", "case": "forest", "detector": "NDVI screening baseline"})["summary"]
    assert nd["method"] == "NDVI screening baseline" and nd["candidate_loss_area_ha"] != rf
    strict = w.call("analyze", {"kind": "forest", "case": "forest", "threshold": 0.9})["summary"]["candidate_loss_area_ha"]
    loose = w.call("analyze", {"kind": "forest", "case": "forest", "threshold": 0.2})["summary"]["candidate_loss_area_ha"]
    assert strict < rf < loose                                           # a higher score threshold can only remove loss


def test_every_layer_renders_and_bad_layer_is_rejected(w):
    for layer in ("alerts", "rgb", "ndvi_change", "ml_score"):
        r = w.call("analyze", {"kind": "forest", "case": "forest", "layer": layer}); assert r["image"].startswith("data:image/png")
    assert w.call("analyze", {"kind": "forest", "case": "forest", "layer": "ndvi_change"})["legend"]["min"] == -0.4
    bad = w.call("analyze", {"kind": "forest", "case": "forest", "layer": "nonsense"}, raw=True); assert not bad["ok"] and bad["kind"] == "input"
    nb = w.call("analyze", {"kind": "forest", "case": "forest", "detector": "NDVI screening baseline", "layer": "ml_score"}, raw=True)
    assert not nb["ok"] and "random forest" in nb["error"]


def test_lake_spectral_and_unet_differ_and_unet_is_cached(w):
    sp = w.call("analyze", {"kind": "lake", "case": "lake", "layer": "algae_change"})["summary"]
    t0 = time.time(); un = w.call("analyze", {"kind": "lake", "case": "lake", "water": "Pretrained U-Net", "layer": "water"}, timeout=900)
    first = time.time() - t0
    s = un["summary"]
    assert "U-Net" in s["method"] and sp["common_water_ha"] != s["common_water_ha"]
    assert s["common_water_ha"] == 703.17 and s["algae_proxy_increase_ha"] == 319.41 and s["observed_pair_pct"] == 93.0   # VALIDATION.md
    t0 = time.time(); w.call("analyze", {"kind": "lake", "case": "lake", "water": "Pretrained U-Net", "layer": "algae", "mndwi": 0.05}); second = time.time() - t0
    assert second < max(5, first * 0.5) or first < 5                  # masks come from the disk cache the second time


def test_regions_review_roundtrip_and_export(w):
    a = {"kind": "forest", "case": "forest"}
    r = w.call("analyze", a); top = r["regions"][0]
    assert top["status"] == "Needs review" and 0 <= top["x"] <= 1 and 0 <= top["y"] <= 1 and top["area_ha"] >= max(x["area_ha"] for x in r["regions"])
    w.call("review", {**a, "region": top["region"], "status": "False positive", "note": "cloud edge"})
    again = w.call("analyze", a)
    assert again["regions"][0]["status"] == "False positive" and again["regions"][0]["note"] == "cloud edge" and again["reviewed"] == 1
    bad = w.call("review", {**a, "region": top["region"], "status": "Bogus"}, raw=True); assert not bad["ok"]
    csv = w.call("export", {**a, "what": "csv"}); assert "False positive" in csv["text"]
    geo = json.loads(w.call("export", {**a, "what": "geojson"})["text"]); assert geo["features"] and "status" in geo["features"][0]["properties"]
    z = zipfile.ZipFile(BytesIO(base64.b64decode(w.call("export", a)["b64"])))
    assert {"summary.json", "report.md", "review_regions.geojson", "ml_score.tif", "review_queue.csv"} <= set(z.namelist())
    c = w.call("crop", {**a, "region": top["region"]}); assert c["before"].startswith("data:image/png") and c["after"].startswith("data:image/png")


def test_upload_roundtrip_with_the_prepared_rasters(w):
    f = lambda n: base64.b64encode((TASK3 / "outputs/forest" / n).read_bytes()).decode()
    up = w.call("upload", {"before_b64": f("before_8band.tif"), "after_b64": f("after_8band.tif"), "before_date": "2019-07-08", "after_date": "2024-07-21", "encoding": "float", "_owner": "aaaaaaaaaaaaaaaa", "name": "Prepared pair"})
    r = w.call("analyze", {"kind": "forest", "case": up["case"], "detector": "NDVI screening baseline", "_owner": "aaaaaaaaaaaaaaaa"})
    assert r["summary"]["region"] == "Prepared pair" and r["summary"]["candidate_loss_area_ha"] > 0 and r["prior_used"] is False
    wrong = w.call("upload", {"before_b64": f("before_8band.tif"), "after_b64": f("after_8band.tif"), "before_date": "2024-07-21", "after_date": "2019-07-08", "_owner": "aaaaaaaaaaaaaaaa"}, raw=True)
    assert not wrong["ok"] and "later" in wrong["error"]
    junk = w.call("upload", {"before_b64": base64.b64encode(b"not a tiff").decode(), "after_b64": base64.b64encode(b"x").decode(), "before_date": "2019-01-01", "after_date": "2024-01-01", "_owner": "aaaaaaaaaaaaaaaa"}, raw=True)
    assert not junk["ok"]


def test_input_validation(w):
    for args in ({"kind": "forest", "case": "nope"}, {"kind": "forest", "case": "forest", "patches": 0}, {"kind": "forest", "case": "custom:../../etc"}):
        r = w.call("analyze", args, raw=True); assert not r["ok"]
    r = w.call("fetch_start", {"bbox": [0, 0, 5, 5], "before": ["2020-01-01", "2020-02-01"], "after": ["2024-01-01", "2024-02-01"]}, raw=True)
    assert not r["ok"] and "0.3" in r["error"]                          # box too large for this prototype
    assert not w.call("fetch_status", {"job": "missing"}, raw=True)["ok"]


# ---------------------------------------------------------------- regressions for the QA audit
OWNER_A, OWNER_B = "aaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbb"


def _pair(w, owner, **over):
    f = lambda n: base64.b64encode((TASK3 / "outputs/forest" / n).read_bytes()).decode()
    args = {"before_b64": f("before_8band.tif"), "after_b64": f("after_8band.tif"), "before_date": "2019-07-08", "after_date": "2024-07-21",
            "encoding": "float", "name": "Pair", "_owner": owner, **over}
    return w.call("upload", args, raw=True)


def test_upload_requires_a_session(w):
    r = _pair(w, None)
    assert not r["ok"] and "session" in r["error"]


def test_upload_identity_covers_every_interpretation_choice(w):
    """The case id used to hash only the first 4 KB, so payloads differing later, or read differently, collided."""
    a = _pair(w, OWNER_A); b = _pair(w, OWNER_A, after_date="2024-08-01"); c = _pair(w, OWNER_A, name="Other label")
    assert a["ok"] and b["ok"] and c["ok"]
    ids = {a["result"]["case"], b["result"]["case"], c["result"]["case"]}
    assert len(ids) == 3, "dates and labels are part of the identity"
    assert _pair(w, OWNER_A)["result"]["case"] == a["result"]["case"], "identical input reuses its own case"


def test_another_session_cannot_see_or_use_a_private_case(w):
    mine = _pair(w, OWNER_A)["result"]["case"]
    other = w.call("analyze", {"kind": "forest", "case": mine, "detector": "NDVI screening baseline", "_owner": OWNER_B}, raw=True)
    assert not other["ok"] and "not available" in other["error"]
    none = w.call("analyze", {"kind": "forest", "case": mine, "detector": "NDVI screening baseline"}, raw=True)
    assert not none["ok"], "no session at all is treated the same way"
    assert all(c["id"] != mine for c in w.call("meta", {"_owner": OWNER_B})["custom"])
    # the same bytes uploaded by another visitor become a separate case with a separate review store
    theirs = _pair(w, OWNER_B)["result"]["case"]
    assert theirs != mine


def test_concurrent_reviews_are_both_kept(w):
    case = _pair(w, OWNER_A, name="Review race")["result"]["case"]
    r = w.call("analyze", {"kind": "forest", "case": case, "detector": "NDVI screening baseline", "_owner": OWNER_A})
    regions = [x["region"] for x in r["regions"][:2]]
    assert len(regions) == 2
    outs = []

    def save(rid):
        outs.append(w.call("review", {"kind": "forest", "case": case, "detector": "NDVI screening baseline", "region": rid,
                                      "status": "False positive", "note": f"note {rid}", "_owner": OWNER_A}, raw=True))
    ts = [threading.Thread(target=save, args=(rid,)) for rid in regions]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert all(o["ok"] for o in outs)
    after = w.call("review", {"kind": "forest", "case": case, "detector": "NDVI screening baseline", "region": regions[0],
                              "status": "False positive", "note": f"note {regions[0]}", "_owner": OWNER_A})
    assert after["reviewed"] == 2, "saving one review must not erase a concurrent one"
    assert after["scope"] == "private"


def test_demo_cases_say_their_reviews_are_public(w):
    r = w.call("analyze", {"kind": "forest", "case": "forest", "detector": "NDVI screening baseline"})
    assert r["review_scope"] == "public demo"


def test_the_effective_water_method_is_reported(w):
    r = w.call("analyze", {"kind": "lake", "case": "lake", "water": "Pretrained U-Net"})
    assert r["method"] in ("Pretrained U-Net", "Spectral open-water mask")
    if r["method"] == "Spectral open-water mask":
        assert "not installed" in r["fallback"], "a fallback must say why the requested method was not used"
    else:
        assert r["fallback"] is None
