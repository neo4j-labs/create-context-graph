# Create Context Graph — Development Makefile

.PHONY: install test test-slow test-matrix test-functional smoke-test lint build publish-pypi publish-npm \
        docs docs-build docs-serve scaffold clean help

## Setup

install:  ## Install dev dependencies
	uv venv && uv pip install -e ".[dev]"

install-all:  ## Install all optional dependencies (dev + generate + connectors)
	uv venv && uv pip install -e ".[all,dev]"

## Testing

test:  ## Run fast tests (602 tests, no Neo4j or API keys required)
	uv run pytest tests/ -v --tb=short

test-slow:  ## Run full suite including slow + functional vault tests (~2.7s extra)
	uv run --extra connectors pytest tests/ -v --tb=short --slow --functional

test-matrix:  ## Run domain x framework matrix only (176 combos)
	uv run pytest tests/test_matrix.py -v --tb=short --slow

test-coverage:  ## Run tests with coverage report
	uv run pytest tests/ -v --cov=create_context_graph --cov-report=html

test-functional:  ## Run optional functional tests (ingest the local-file vault fixture)
	uv run --extra connectors pytest tests/test_local_file_vault.py --functional -v --tb=short

smoke-test:  ## E2E smoke test: scaffold, start, and chat for 3 key frameworks (requires Neo4j + API keys)
	@echo "Running smoke tests for pydanticai, google-adk, and strands..."
	uv run python scripts/e2e_smoke_test.py --domain financial-services --framework pydanticai --quick
	uv run python scripts/e2e_smoke_test.py --domain real-estate --framework google-adk --quick
	uv run python scripts/e2e_smoke_test.py --domain trip-planning --framework strands --quick

## Linting

lint:  ## Run ruff linter
	uv run ruff check src/ tests/

lint-fix:  ## Auto-fix lint issues
	uv run ruff check src/ tests/ --fix

## Build & Publish

build:  ## Build Python package (sdist + wheel)
	uv build

publish-pypi: build  ## Publish to PyPI
	uv publish

publish-npm:  ## Publish npm wrapper to npmjs
	cd npm-wrapper && npm publish --access public

## Documentation

docs:  ## Start Docusaurus dev server
	cd docs && npm run start

docs-build:  ## Build Docusaurus site
	cd docs && npm install && npm run build

docs-serve:  ## Serve built docs locally
	cd docs && npm run serve

docs-install:  ## Install docs dependencies
	cd docs && npm install

## Scaffold Testing

scaffold:  ## Scaffold a test project (healthcare/pydanticai)
	uv run create-context-graph /tmp/test-scaffold \
		--domain healthcare --framework pydanticai --demo-data \
		--output-dir /tmp/test-scaffold

scaffold-clean:  ## Remove test scaffold
	rm -rf /tmp/test-scaffold

## Data

regenerate-fixtures:  ## Regenerate all 23 fixture files with Claude API (requires ANTHROPIC_API_KEY)
	uv run python scripts/regenerate_fixtures.py

## Cleanup

clean:  ## Remove build artifacts, caches, and temp files
	rm -rf dist/ build/ *.egg-info
	rm -rf .pytest_cache .ruff_cache htmlcov .coverage
	rm -rf docs/build docs/.docusaurus
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

## Help

help:  ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
