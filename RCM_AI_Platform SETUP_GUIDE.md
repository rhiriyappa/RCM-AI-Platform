# RCM AI Platform — Local Setup Guide

**Tested on:** macOS 14+, Ubuntu 22.04/24.04, WSL2 (Windows 11)  
**Python required:** 3.11 or 3.12  
**Tests:** 161 passing, 91% coverage

---

## Prerequisites

Before starting, verify you have these tools installed:

```bash
python3 --version       # must be 3.11 or 3.12
docker --version        # must be 20.10+
docker compose version  # must be 2.x (not v1)
git --version
```

If anything is missing:
- **Python 3.11/3.12:** https://www.python.org/downloads/ or `brew install python@3.12`
- **Docker Desktop:** https://www.docker.com/products/docker-desktop/
- **Git:** https://git-scm.com/downloads

---

## Step 1 — Get the code (clone from GitHub)

```bash
git clone git@github.com:rhiriyappa/RCM-AI-Platform.git
cd RCM-AI-Platform
```

---

## Step 2 — Create a Python virtual environment

**Always use a virtual environment.** Do not install into your system Python.

```bash
# Create the venv (from inside the project directory)
python3 -m venv .venv

# Activate it
# macOS / Linux / WSL:
source .venv/bin/activate

# Windows PowerShell:
.venv\Scripts\Activate.ps1

# Windows CMD:
.venv\Scripts\activate.bat
```

Your prompt should now show `(.venv)` at the start. If it doesn't, the activation didn't work — do not proceed until it does.

---

## Step 3 — Install Python dependencies

```bash
# Install the project and all dev dependencies in one command
pip install -e ".[dev]"
```

This installs:
- `pydantic`, `boto3`, `fastapi`, `scikit-learn`, `numpy`, `structlog`, `tenacity`
- `pytest`, `pytest-cov`, `pytest-mock`, `moto` (AWS mocking), `ruff`, `mypy`

Expected output ends with something like:
```
Successfully installed RCM-AI-Platform-1.0.0 ...
```

**If you see an error here**, see the Troubleshooting section at the bottom.

---

## Step 4 — Copy environment config

```bash
cp .env.example .env
```

The `.env` file has everything pre-configured for local development with LocalStack. You only need to edit it if you want to connect to real AWS or add LLM API keys.

---

## Step 5 — Run the unit tests (no Docker needed)

The full test suite runs entirely offline. No AWS, no Docker, no API keys required.

```bash
pytest tests/ -v
```

Expected output:
```
============================= test session starts ==============================
...
161 passed in 4.6s
```

### Run with coverage report

```bash
pytest tests/ \
  --cov=ingestion --cov=classification --cov=extraction \
  --cov=orchestration --cov=agents --cov=contracts --cov=observability \
  --cov-report=term-missing \
  --cov-fail-under=85
```

Expected: **161 passed, 91% coverage**.

### Run tests for a specific phase

```bash
pytest tests/ingestion/        -v   # Phase 1 — ingestion
pytest tests/classification/   -v   # Phase 2 — classifier
pytest tests/extraction/       -v   # Phase 2 — extraction
pytest tests/orchestration/    -v   # Phase 3 — orchestration
pytest tests/agents/           -v   # Phase 4 — agents
```

---

## Step 6 — Start the full local stack (Docker required)

This spins up LocalStack (AWS mock), Postgres with pgvector, and Redis.

```bash
# Start all services
docker compose up -d

# Watch startup logs (Ctrl+C to stop watching, services keep running)
docker compose logs -f

# Check everything is healthy (wait ~15 seconds after starting)
docker compose ps
```

All services should show `healthy` or `running`. If LocalStack takes more than 60 seconds, see Troubleshooting.

### Initialize AWS resources

```bash
# Create the S3 bucket and SQS queues in LocalStack
bash infra/localstack/init.sh
```

Expected output:
```
>> Creating S3 bucket: onecall-raw-docs
>> Creating FIFO queues
>> Creating standard queues
>> LocalStack resources ready
```

### Start the ingestor API

```bash
# In a new terminal (or run in background with &)
uvicorn ingestion.api:app --reload --port 8000
```

Check it's up:
```bash
curl http://localhost:8000/health
# {"status":"ok","service":"ingestor","version":"1.0.0"}
```

---

## Step 7 — Test the ingestor API manually

### Send a FHIR bundle

```bash
curl -X POST http://localhost:8000/ingest/fhir \
  -H "Content-Type: application/json" \
  -d '{
    "resourceType": "Bundle",
    "entry": [
      {"resource": {
        "resourceType": "Patient",
        "name": [{"family": "Smith", "given": ["Jane"]}],
        "birthDate": "1978-04-12",
        "identifier": [{"value": "MRN-00042"}]
      }},
      {"resource": {
        "resourceType": "Coverage",
        "payor": [{"identifier": {"value": "BCBS-TX"}}]
      }},
      {"resource": {
        "resourceType": "Claim",
        "diagnosis": [{"diagnosisCodeableConcept": {"coding": [{"code": "M54.5"}]}}],
        "item": [{"productOrService": {"coding": [{"code": "99213"}]}}]
      }}
    ]
  }'
```

Expected response:
```json
{"document_id": "...", "status": "queued"}
```

### Send an EDI 837 claim

```bash
curl -X POST http://localhost:8000/ingest/edi837 \
  -H "Content-Type: application/x12" \
  --data-binary "ISA*00*~
NM1*QC*1*DOE*JOHN****MI*MBR-001~
HI*ABK:M54.5~
SV1*HC:99213*185.00~"
```

---

## Step 8 — Stop the local stack

```bash
docker compose down        # stop but keep data
docker compose down -v     # stop and wipe volumes (clean reset)
```

---

## Quick reference

| Task | Command |
|---|---|
| Activate venv | `source .venv/bin/activate` |
| Run all tests | `pytest tests/ -v` |
| Run with coverage | `pytest tests/ --cov=ingestion --cov=classification ... --cov-fail-under=85` |
| Phase 1 tests only | `pytest tests/ingestion/ -v` |
| Phase 2 tests only | `pytest tests/classification/ tests/extraction/ -v` |
| Start Docker stack | `docker compose up -d` |
| Stop Docker stack | `docker compose down` |
| Start ingestor API | `uvicorn ingestion.api:app --reload` |
| Check API health | `curl http://localhost:8000/health` |
| Lint | `ruff check .` |
| Type check | `mypy ingestion contracts classification extraction orchestration` |
| Run eval harness | `python scripts/run_eval.py --gold-set tests/fixtures/gold_extractions_p2.jsonl` |

---

## Troubleshooting

### ❌ `ModuleNotFoundError: No module named 'contracts'`

The project root is not on Python's path.

**Fix:** Make sure you installed with `pip install -e .` (editable install). Verify:
```bash
pip show RCM-AI-Platform
```
If it's not installed, re-run:
```bash
pip install -e ".[dev]"
```

If tests still fail, run pytest with explicit path:
```bash
PYTHONPATH=$(pwd) pytest tests/ -v
```

---

### ❌ `pip install -e ".[dev]"` fails with metadata/hatchling error

This happens when an old version of hatchling or setuptools is installed.

**Fix:**
```bash
pip install --upgrade pip setuptools wheel
pip install -e ".[dev]"
```

---

### ❌ `externally-managed-environment` error on pip install

Your system Python is managed by your OS and blocks pip.

**Fix:** Make sure you activated the virtual environment first:
```bash
source .venv/bin/activate   # must show (.venv) in prompt
pip install -e ".[dev]"     # now inside venv — works
```

---

### ❌ `LogisticRegression.__init__() got an unexpected keyword argument 'multi_class'`

Your scikit-learn is 1.5+. This argument was removed.

**Fix:** The project's `classification/embeddings.py` does not use `multi_class`. If you see this error, you have a stale `.pyc` file. Fix:
```bash
find . -name "*.pyc" -delete
find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
pytest tests/ -v
```

---

### ❌ Docker Compose: `Cannot connect to the Docker daemon`

Docker Desktop isn't running.

**Fix:** Open Docker Desktop and wait for it to start (the whale icon in the menu bar stops animating). Then retry.

---

### ❌ LocalStack health check failing / services not healthy

LocalStack takes 20–60 seconds on first start.

**Fix:** Wait and retry:
```bash
# Wait 30 seconds, then check
sleep 30
docker compose ps

# If still unhealthy, check LocalStack logs
docker compose logs localstack | tail -30
```

If LocalStack crashes with `Killed`, your Docker Desktop doesn't have enough memory. Go to Docker Desktop → Settings → Resources → increase Memory to at least 4GB.

---

### ❌ `Port 4566 already in use`

Something else is using LocalStack's port.

**Fix:**
```bash
# Find what's using it
lsof -i :4566

# Kill it (replace PID with the actual number)
kill -9 <PID>

# Or change the port in docker-compose.yml:
# ports: ["4567:4566"]
# and update .env: AWS_ENDPOINT_URL=http://localhost:4567
```

---

### ❌ `Port 8000 already in use` (ingestor)

**Fix:** Use a different port:
```bash
uvicorn ingestion.api:app --reload --port 8001
```

---

### ❌ Tests slow or hanging on `test_embeddings.py`

The embedding classifier trains on startup. On slow machines this can take a few seconds.

**Fix:** This is expected. The `scope="module"` fixture trains once per test session. It takes 1–3 seconds and only runs once.

---

### ❌ `pytest: command not found` after activating venv

The venv wasn't created with the project installed.

**Fix:**
```bash
# Confirm venv is active (should show path inside .venv)
which python3

# Reinstall
pip install -e ".[dev]"
which pytest   # should now resolve
```

---

### ❌ Coverage below 85% / `FAIL Required test coverage ... not reached`

Run the coverage command with all source modules listed:

```bash
pytest tests/ \
  --cov=ingestion \
  --cov=classification \
  --cov=extraction \
  --cov=orchestration \
  --cov=agents \
  --cov=contracts \
  --cov=observability \
  --cov-fail-under=85
```

If a module is missing from `--cov=`, that module's uncovered lines won't be counted — giving a false low reading.

---

## Adding LLM API keys (optional — for Phase 3+)

The unit tests all use mock LLM calls and work without any API keys. If you want to run the extraction engine against a real model, add your key to `.env`:

```bash
# Edit .env
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
```

Then in code, inject a real call function:

```python
import anthropic

client = anthropic.Anthropic()

def call_llm(system: str, user: str) -> str:
    msg = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return msg.content[0].text

# Inject into ExtractionEngine
from extraction.engine import ExtractionEngine
from extraction.enrichment import ExtractionEnricher, MockNPILookup, CodeValidator

engine = ExtractionEngine(
    call_llm=call_llm,
    enricher=ExtractionEnricher(MockNPILookup(), CodeValidator()),
)
```

---

## Verified environment

These are the exact versions tested and confirmed working:

| Package | Version |
|---|---|
| Python | 3.11, 3.12 |
| pydantic | 2.6+ |
| scikit-learn | 1.4+ (1.5, 1.8 confirmed) |
| boto3 | 1.34+ |
| numpy | 1.26+ |
| pytest | 8.1+ |
| moto | 5.0+ |
| fastapi | 0.110+ |
