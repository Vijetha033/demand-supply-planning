PY ?= .venv/bin/python
export PYTHONPATH := src

.PHONY: starter full test repro docs all
starter:            ## generate + plan + validate + evaluate + export (starter scale)
	$(PY) -m supply_planning run --scale starter
full:               ## same pipeline at the brief's baseline volume
	$(PY) -m supply_planning run --scale full
test:
	$(PY) -m pytest -q
repro:              ## regenerate twice with the same seed and compare checksums
	$(PY) -m supply_planning repro --scale starter
	$(PY) -m supply_planning repro --scale full
docs:
	$(PY) -m supply_planning docs
all: docs starter full repro test
