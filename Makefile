.PHONY: install dev lint test help setup build run format analyze

.DEFAULT_GOAL := help

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  %-10s %s\n", $$1, $$2}'

install: ## Install the package
	pip install .

dev: ## Editable install with dev dependencies
	pip install -e . pytest ruff

lint: ## Run the whole gate — every hook, every file
	pre-commit run --all-files

test: ## Run pytest
	pytest -q

setup: ## Install the pre-commit hook
	pre-commit install

build: ## Build sdist and wheel
	python -m build

run: ## Run idle-hunter
	idle-hunter --help

format: ## Rewrite the sources to canonical form
	ruff format .

analyze: ## Type-check the package
	basedpyright
