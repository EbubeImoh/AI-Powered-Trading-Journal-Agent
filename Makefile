.PHONY: install lint test fmt ci venv

VENV := .venv

venv:
	python3 -m venv $(VENV)

install: venv
	$(VENV)/bin/python -m pip install --upgrade pip
	$(VENV)/bin/pip install -r requirements.txt

lint:
	ruff check .

fmt:
	ruff format .
	ruff check --fix-only .

test:
	pytest

ci: lint test
