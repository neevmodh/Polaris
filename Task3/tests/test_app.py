from pathlib import Path
import json
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


def test_real_case_studies_and_ui_controls():
    assert (ROOT / "models" / "forest_rf.joblib").exists(), "Train the model before validating the complete app."
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=45).run()
    assert not app.exception
    assert len(app.metric) == 4
    first = app.metric[0].value
    app.sidebar.selectbox[1].select("NDVI screening baseline").run()
    assert not app.exception
    assert app.metric[0].value != first
    app.sidebar.radio[0].set_value("Lake water quality").run()
    assert not app.exception
    assert app.metric[0].label == "Comparable open water"
    app.sidebar.selectbox[1].select("Pretrained U-Net").run()
    assert not app.exception
    assert len(app.metric) == 4


def test_training_evidence_is_present_and_held_out():
    m = json.loads((ROOT / "models" / "metrics.json").read_text())
    assert m["holdout_positive_samples"] >= 20
    assert m["rf"]["confusion_matrix"]["tp"] + m["rf"]["confusion_matrix"]["fn"] == m["holdout_positive_samples"]
    assert "reference" in m and "spatial_split" in m


def test_new_viewers_and_rgb_studio():
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=45).run()
    assert not app.exception
    assert [t.label for t in app.tabs] == ["Observation workspace", "Timeline & trends", "Review queue", "Model & evidence", "Sources & exports"]
    viewer = next(x for x in app.radio if x.label == "Viewer")
    viewer.set_value("Swipe comparison").run()
    assert not app.exception
    next(x for x in app.radio if x.label == "Viewer").set_value("Geographic map").run()
    assert not app.exception
    app.sidebar.selectbox[0].select("Upload PNG / JPEG images").run()
    assert not app.exception
    assert app.metric[0].label == "Visible change"
    assert len(app.metric) == 3
