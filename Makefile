.PHONY: install dev lint test help

.DEFAULT_GOAL := help

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  %-10s %s\n", $$1, $$2}'

install: ## Install the package
	pip install .

dev: ## Editable install with dev dependencies
	pip install -e . pytest ruff

lint: ## Run ruff
	ruff check .

test: ## Run pytest
	pytest -q
