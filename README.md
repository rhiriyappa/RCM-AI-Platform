# RCM AI Platform

Production grade AI platform for Revenue Cycle Management — real time ingestion, classification, LLM extraction, agentic workflows, and observability.

[![CI](https://github.com/rhiriyappa/RCM-AI-Platform/actions/workflows/ci.yml/badge.svg)](https://github.com/rhiriyappa/RCM-AI-Platform/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/badge/coverage-85%25-brightgreen)](https://github.com/rhiriyappa/RCM-AI-Platform)
[![Python](https://img.shields.io/badge/python-3.11+-blue)](https://python.org)

## Architecture

```
Unstructured inputs (fax · HL7 · FHIR · EDI 837 · webhooks)
        │
┌───────▼──────────────────────────────────────────────┐
│  Phase 1 · Ingestion & normalization                 │
│  Textract OCR · format parsers · RawDocument schema  │
└───────┬──────────────────────────────────────────────┘
        │
┌───────▼──────────────────────────────────────────────┐
│  Phase 2 · Classification & extraction               │
│  3-tier ensemble · LLM extraction · NPI/code enrich  │
└───────┬──────────────────────────────────────────────┘
        │
┌───────▼──────────────────────────────────────────────┐
│  Phase 3 · LLM orchestration                         │
│  Prompt registry · model router · guardrails          │
└───────┬──────────────────────────────────────────────┘
        │
┌───────▼──────────────────────────────────────────────┐
│  Phase 4 · Agentic workflows (LangGraph)             │
│  Prior auth · denial appeal · referral triage        │
└───────┬──────────────────────────────────────────────┘
        │
┌───────▼──────────────────────────────────────────────┐
│  Phase 5 · Observability                             │
│  LangSmith · CloudWatch · RAGAS evals · feedback     │
└──────────────────────────────────────────────────────┘
```

## Quick start

```bash
git clone https://github.com/rhiriyappa/RCM-AI-Platform.git
cd ai-platform
cp .env.example .env
docker compose up -d
make health
make test
```

## Project structure

```
RCM-AI-Platform/
├── ingestion/          # Phase 1: adapters, OCR, parsers, normalizer, validator, fan-out
├── classification/     # Phase 2: rules, embedding classifier, LLM fallback, ensemble
├── extraction/         # Phase 2: LLM extraction engine, parser, enrichment, confidence
├── orchestration/      # Phase 3: prompt registry, model router, guardrails, fallback
├── agents/             # Phase 4: LangGraph graphs (prior_auth, denial, triage)
├── contracts/          # Cross-cutting: Pydantic schemas, Avro contracts, FHIR profiles
├── observability/      # Phase 5: metrics, eval pipelines, feedback loops
├── tests/              # Unit + integration + eval tests per layer
├── infra/              # LocalStack init, DB migrations, Terraform modules
├── scripts/            # Developer utilities, eval harness runner
└── .github/            # CI/CD workflows, issue templates, PR template
```

## Make targets

| Command | Description |
|---|---|
| `make up` | Start full local stack (LocalStack + Postgres + Redis) |
| `make down` | Stop all services |
| `make test` | Full test suite with coverage gate (≥85%) |
| `make test-p1` | Phase 1 ingestion tests |
| `make test-p2` | Phase 2 classification + extraction tests |
| `make test-p3` | Phase 3 orchestration tests |
| `make test-p4` | Phase 4 agent tests |
| `make lint` | ruff + mypy |
| `make fmt` | Auto-format |
| `make eval` | Run extraction eval harness against gold set |
| `make health` | Check service health endpoints |

## Phase status

| Phase | Scope | Status |
|---|---|---|
| Phase 1 | Ingestion & normalization | ✅ Complete |
| Phase 2 | Classification & extraction | ✅ Complete |
| Phase 3 | LLM orchestration layer | ✅ Complete |
| Phase 4 | Agentic workflow engine | ✅ Complete |
| Phase 5 | Observability & eval | ✅ Complete |

## Tech stack

| Concern | Technology |
|---|---|
| OCR | AWS Textract (async) |
| LLM inference | Claude Sonnet · GPT-4o · vLLM |
| Structured outputs | Instructor + Pydantic v2 |
| Orchestration | LangGraph + LangChain |
| Vector store | pgvector (HNSW) |
| Message bus | SQS FIFO · Kinesis |
| Observability | LangSmith · CloudWatch · Grafana |
| Eval | RAGAS · pytest · gold extraction sets |
| Local dev | LocalStack · Docker Compose |
