.PHONY: install dev lint test

install:
	pip install .

dev:
	pip install -e . pytest ruff

lint:
	ruff check .

test:
	pytest -q
