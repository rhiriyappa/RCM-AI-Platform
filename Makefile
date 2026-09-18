.PHONY: up down health test test-p1 test-p2 test-p3 test-p4 lint fmt eval clean

COMPOSE = docker compose
PYTEST  = PYTHONPATH=$(PWD) pytest
COV_SRC = --cov=ingestion --cov=classification --cov=extraction --cov=orchestration --cov=agents --cov=contracts --cov=observability

up:
	$(COMPOSE) up -d
	@sleep 6 && $(MAKE) health

down:
	$(COMPOSE) down -v

health:
	@curl -sf http://localhost:4566/_localstack/health | python3 -m json.tool | grep -E '"s3"|"sqs"' || echo "LocalStack starting..."
	@curl -sf http://localhost:8000/health || echo "Ingestor not ready yet"

test:
	$(PYTEST) tests/ $(COV_SRC) --cov-report=term-missing --cov-fail-under=85

test-p1:
	$(PYTEST) tests/ingestion/ --cov=ingestion --cov=contracts --cov-report=term-missing

test-p2:
	$(PYTEST) tests/classification/ tests/extraction/ --cov=classification --cov=extraction --cov-report=term-missing

test-p3:
	$(PYTEST) tests/orchestration/ --cov=orchestration --cov-report=term-missing

test-p4:
	$(PYTEST) tests/agents/ --cov=agents --cov-report=term-missing

lint:
	ruff check .
	mypy ingestion contracts classification extraction orchestration --ignore-missing-imports

fmt:
	ruff check --fix .
	ruff format .

eval:
	PYTHONPATH=$(PWD) python scripts/run_eval.py --gold-set tests/fixtures/gold_extractions_p2.jsonl

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .coverage htmlcov .mypy_cache .ruff_cache .pytest_cache dist
