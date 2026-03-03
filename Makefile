PYTHON := python3

.PHONY: lint-check lint-fix typecheck test review full unit integration validation ux fixtures

lint-check:
	$(PYTHON) -m ruff check src tests

lint-fix:
	$(PYTHON) -m ruff check src tests --fix

typecheck:
	$(PYTHON) -m mypy src --ignore-missing-imports

test: lint-check typecheck
	$(PYTHON) test_runner.py

unit:
	$(PYTHON) test_runner.py unit

integration:
	$(PYTHON) test_runner.py integration

validation:
	$(PYTHON) test_runner.py validation

ux:
	$(PYTHON) test_runner.py ux

fixtures:
	$(PYTHON) scripts/generate_fixtures.py

review:
	$(PYTHON) review_pass.py

full: test review

