SHELL:=/bin/bash
FIX=1
COVERAGE=0
POETRY=poetry
POETRY_RUN=$(POETRY) run
RUFF=$(POETRY_RUN) ruff
LINT_IMPORTS=$(POETRY_RUN) lint-imports
MYPY=$(POETRY_RUN) mypy
PYTEST=$(POETRY_RUN) pytest -W error
PYTHON=$(POETRY_RUN) python
MKDOCS=$(POETRY_RUN) mkdocs
JINJA_TREE=$(POETRY_RUN) jinja-tree

default: help

.PHONY: _check_poetry
_check_poetry: 
	@command -v $(POETRY) >/dev/null 2>&1 || (echo "Poetry is not installed. Please install it from https://python-poetry.org/docs/#installation" && exit 1)

.PHONY: check_poetry
check_poetry: _check_poetry ## Check if poetry is installed and install the app if needed
	@$(POETRY) config virtualenvs.in-project true
	@$(POETRY) env info --path >/dev/null 2>&1 || $(MAKE) install

.PHONY: install
install: _check_poetry ## Install the app
	$(POETRY) config virtualenvs.in-project true
	$(POETRY) install

.PHONY: lint
lint: check_poetry ## Lint the code (FIX=0 to disable autofix)
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
test: check_poetry ## Test the code
ifeq ($(COVERAGE), 0)
	$(PYTEST) tests
else
	$(PYTEST) --no-cov-on-fail --cov=py_agile_ops --cov-report=term --cov-report=html --cov-report=xml tests
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
doc: check_poetry ## Generate the documentation
	$(JINJA_TREE) .
	cp -f README.md docs/index.md
	$(MKDOCS) build --clean --strict 

.PHONY: help
help:
	@# See https://marmelab.com/blog/2016/02/29/auto-documented-makefile.html
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'
