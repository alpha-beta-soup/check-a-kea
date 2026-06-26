QGIS_PYTHON = $(HOME)/miniforge3/envs/qgis_latest/share/qgis/python

test:
	pytest

test-qgis:
	PYTHONPATH=$(QGIS_PYTHON) pytest
