.PHONY: setup data train predict test app all stress
PY=.venv/bin/python
setup:
	python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt
data:
	$(PY) -m carbon.data_synth        # SYNTHETIC. For real data: $(PY) -m carbon.prepare_brsr data/raw/brsr_ghg.csv
train:
	$(PY) -m carbon.train
stress:
	$(PY) -m carbon.stress
predict:
	$(PY) -m carbon.predict
test:
	$(PY) -m pytest -q
app:
	.venv/bin/streamlit run app.py
all: data train predict test

