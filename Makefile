.PHONY: install lint test fmt ci venv env-check env-record env-verify

VENV := .venv
ENV_FILE ?= .env
ENV_HASH ?= .env.sha256

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

env-check:
	python -m scripts.check_env check --env-file $(ENV_FILE)

env-record:
	python -m scripts.check_env record --env-file $(ENV_FILE) --hash-file $(ENV_HASH)

env-verify:
	python -m scripts.check_env verify --env-file $(ENV_FILE) --hash-file $(ENV_HASH)
