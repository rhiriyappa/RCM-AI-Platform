# Contributing

## Quick start
```bash
git clone <repo> && cd RCM-AI_Platform
cp .env.example .env
pip install -e ".[dev]"
docker compose up -d
make test
```

## Branching
- `main` — production, requires CI green + peer review
- `develop` — integration branch
- `feature/<phase>/<description>` — feature work

## Commit format
`<type>(<scope>): <summary>`

Types: `feat`, `fix`, `test`, `refactor`, `chore`, `docs`, `ci`

## PR checklist
- [ ] `make lint` clean
- [ ] `make test` passes with ≥85% coverage
- [ ] No secrets or PII in code/fixtures
- [ ] Data contract changes documented
