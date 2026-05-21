# Create Context Graph — Development Makefile

.PHONY: install test test-slow test-matrix test-functional smoke-test smoke-render \
        smoke-render-nams smoke-render-bolt smoke-render-clean lint build publish-pypi publish-npm \
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

## Pre-release Smoke Render
##
## smoke-render walks the full scaffold → install → import path for both
## backends without needing Neo4j, NAMS, or LLM keys. Catches the class of
## breakage the mocked unit suite can't see:
##   - dep-resolution failures (uv sync conflicts)
##   - install-time crashes (e.g. spacy download on NAMS — fixed in 0.11.3)
##   - import-time failures in generated app.main
##   - generated test-scaffold regressions
##
## Run this manually before tagging a release.

SMOKE_RENDER_DIR ?= /tmp/ccg-smoke-render

smoke-render: smoke-render-nams smoke-render-bolt  ## Scaffold + install + import-check both backends

# Placeholder API keys for smoke-render — framework SDKs (PydanticAI, etc.)
# validate keys at module-load time when the Agent is constructed at module
# scope, so we need *something* set to import without a real key.
SMOKE_ENV := ANTHROPIC_API_KEY=sk-smoke-placeholder \
             OPENAI_API_KEY=sk-smoke-placeholder \
             GOOGLE_API_KEY=sk-smoke-placeholder

smoke-render-nams:  ## NAMS-default scaffold: render, install, import-check, run generated tests
	@echo ""
	@echo "===================================================================="
	@echo " smoke-render: NAMS-default scaffold"
	@echo "===================================================================="
	@rm -rf $(SMOKE_RENDER_DIR)/nams
	uv run create-context-graph smoke-nams \
		--domain healthcare --framework strands \
		--nams-api-key sk-smoke-render-fake \
		--output-dir $(SMOKE_RENDER_DIR)/nams
	@echo ""
	@echo "→ make install (NAMS, no spacy download expected)"
	cd $(SMOKE_RENDER_DIR)/nams && $(MAKE) install-backend
	@echo ""
	@echo "→ Import-check generated FastAPI app"
	cd $(SMOKE_RENDER_DIR)/nams/backend && \
		$(SMOKE_ENV) MEMORY_API_KEY=sk-smoke MEMORY_BACKEND=nams \
		uv run python -c "from app.main import app; print(f'NAMS app imported: {app.title}')"
	@echo ""
	@echo "→ Run generated backend test suite"
	cd $(SMOKE_RENDER_DIR)/nams/backend && \
		$(SMOKE_ENV) MEMORY_API_KEY=sk-smoke MEMORY_BACKEND=nams \
		uv run pytest tests/ -v --tb=short
	@echo ""
	@echo "✅ smoke-render-nams passed"

smoke-render-bolt:  ## Self-hosted scaffold: render, install, import-check, run generated tests
	@echo ""
	@echo "===================================================================="
	@echo " smoke-render: self-hosted bolt scaffold"
	@echo "===================================================================="
	@rm -rf $(SMOKE_RENDER_DIR)/bolt
	uv run create-context-graph smoke-bolt \
		--domain healthcare --framework pydanticai \
		--self-hosted --demo-data \
		--output-dir $(SMOKE_RENDER_DIR)/bolt
	@echo ""
	@echo "→ make install (bolt, with spacy import-check guard)"
	cd $(SMOKE_RENDER_DIR)/bolt && $(MAKE) install-backend
	@echo ""
	@echo "→ Import-check generated FastAPI app"
	cd $(SMOKE_RENDER_DIR)/bolt/backend && \
		$(SMOKE_ENV) MEMORY_BACKEND=bolt \
		uv run python -c "from app.main import app; print(f'Bolt app imported: {app.title}')"
	@echo ""
	@echo "→ Run generated backend test suite"
	cd $(SMOKE_RENDER_DIR)/bolt/backend && \
		$(SMOKE_ENV) MEMORY_BACKEND=bolt \
		uv run pytest tests/ -v --tb=short
	@echo ""
	@echo "✅ smoke-render-bolt passed"

smoke-render-clean:  ## Remove smoke-render scratch directories
	rm -rf $(SMOKE_RENDER_DIR)

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
