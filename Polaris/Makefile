.PHONY: install build run dev test test-sat test-air test-grid test-carbon e2e
install:
	cd web && npm install
build:
	cd web && npm run build
run: build
	cd web && npm run start:prod
dev:
	cd web && npm run dev
test-sat:            # satellite bridge, run with Task3's interpreter
	cd ../Task3 && .venv/bin/python -m pytest -q -p no:cacheprovider ../Polaris/tests/test_sat_worker.py
test-air:            # air bridge, run with task1's interpreter
	cd ../task1 && .venv/bin/python -m pytest -q -p no:cacheprovider ../Polaris/tests/test_air_worker.py
test-grid:           # microgrid bridge, run with netzero-ai's interpreter
	cd ../netzero-ai && .venv/bin/python -m pytest -q -p no:cacheprovider ../Polaris/tests/test_grid_worker.py
test-carbon:         # carbon engine
	cd ../SCOPE && .venv/bin/python -m pytest -q -p no:warnings
e2e:                 # needs the site running on :3100 and Chrome
	cd web && npm run e2e
test: test-sat test-air test-grid test-carbon e2e
