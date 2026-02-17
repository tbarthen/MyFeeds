# MyFeeds

Personal RSS reader with regex-based auto-filtering. Killer feature: filtered articles are preserved and grouped by the rule that caught them for false-positive review.

**Stack**: Python 3.11+ / Flask / SQLite / feedparser

## Response Style

Be concise. Answer first, details only if asked.

## Decision Framework

```
Essential for core use case? → Build simply
Simpler way exists? → Use it
Otherwise → Skip it (YAGNI)
```

## Code Principles

- **SRP**: One function = one job
- **DRY**: Extract repeated patterns; use constants for magic numbers/strings
- **No inline comments**: Code should be self-documenting (docstrings OK)
- **Defensive**: Validate inputs, handle None/empty, use type hints

## Commands

```bash
# Dev server
flask run --debug

# Tests (must pass before commit)
pytest

# Single test file
pytest tests/test_filter_engine.py
```

## Critical Constraints

- **SQL injection**: Always use parameterized queries, never f-strings for values
- **Feed fetching**: Handle malformed feeds gracefully (feedparser does most of this)
- **Filter matches**: Store with rule ID in `filter_matches` table — "Filtered" is a virtual view, not a copy
- **Raw content**: Store original article content to allow re-filtering when rules change

## Project Docs

Detailed documentation lives in `docs/`. Reference as needed:
- `docs/architecture.md` — Component relationships
- `docs/data_model.md` — Database schema and relationships
- `docs/filter_engine.md` — Filtering logic and regex handling
- `docs/deployment.md` — GCP deployment instructions