SHELL:=/bin/bash
FIX=1
COVERAGE=0
UV=uv
UV_PYTHON?=3.9
LIMITED_SUPPORT=0
ifeq ($(UV_PYTHON), 3.7)
	LIMITED_SUPPORT=1
endif
ifeq ($(UV_PYTHON), 3.8)
	LIMITED_SUPPORT=1
endif
UV_PYTHON_OPTS=--python=$(UV_PYTHON) --python-preference=only-managed
UV_OPTS=$(UV_PYTHON_OPTS)
ifeq ($(LIMITED_SUPPORT), 1)
	UV_OPTS+=--no-group=dev --no-group=doc --no-group=lint
endif
UV_RUN=$(UV) run $(UV_OPTS)
RUFF=$(UV_RUN) ruff
LINT_IMPORTS=$(UV_RUN) lint-imports
MYPY=$(UV_RUN) mypy
PYTEST=$(UV_RUN) pytest -W error
PYTHON=$(UV_RUN) python
MKDOCS=$(UV_RUN) mkdocs
JINJA_TREE=$(UV_RUN) jinja-tree

default: help

.PHONY: _check_uv
_check_uv: 
	@command -v $(UV) >/dev/null 2>&1 || (echo "uv is not installed. Please install it from https://docs.astral.sh/uv/" && exit 1)

.PHONY: install
install: _check_uv .venv/installed ## Install the app

.venv/installed: uv.lock
	$(MAKE) --silent --no-print-directory _check_uv
	$(UV) --version
	$(UV) sync $(UV_OPTS)
	touch $@
	$(UV_RUN) python --version

uv.lock: pyproject.toml
	$(MAKE) --silent --no-print-directory _check_uv
	$(UV) lock $(UV_PYTHON_OPTS)
	touch $@

.PHONY: lint
lint: .venv/installed ## Lint the code (FIX=0 to disable autofix)
ifeq ($(FIX), 0)
	$(RUFF) format --config ./ruff.toml --check .
	$(RUFF) check --config ./ruff.toml .
else
	$(RUFF) format --config ./ruff.toml .
	$(RUFF) check --config ./ruff.toml --fix .
endif
	$(MYPY) --check-untyped-defs .
	$(LINT_IMPORTS)

.PHONY: no-dirty
no-dirty: ## Test if there are some dirty files
	@DIFF=`git status --short`; if test "$${DIFF}" != ""; then echo "ERROR: There are dirty files"; echo; git status; git diff; exit 1; fi

.PHONY: test
test: .venv/installed ## Test the code
ifeq ($(COVERAGE), 0)
	$(PYTEST) tests
else
	$(PYTEST) --no-cov-on-fail --cov=rtc --cov-report=term --cov-report=html --cov-report=xml tests
endif

.PHONY: clean
clean: ## Clean generated files
	rm -Rf .*_cache build
	find . -type d -name __pycache__ -exec rm -Rf {} \; 2>/dev/null || true
	rm -Rf .venv
	rm -Rf html
	rm -Rf site
	rm -f docs/index.md

.PHONY: doc
doc: .venv/installed ## Generate the documentation
	$(JINJA_TREE) .
	cp -f README.md docs/index.md
	$(MKDOCS) build --clean --strict 

.PHONY: help
help:
	@# See https://marmelab.com/blog/2016/02/29/auto-documented-makefile.html
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'
