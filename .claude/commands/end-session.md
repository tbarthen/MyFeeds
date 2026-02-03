---
description: Validate changes and commit
---

# End Session

Run before committing changes.

## 1. Run Tests

```bash
pytest
```

All tests must pass. If any fail, fix before proceeding.

## 2. Review Changes

Run `git diff` and verify:
- No debugging code left behind (print statements, commented code)
- New code follows CLAUDE.md principles
- No unintended changes to other files

## 3. Update Docs (If Needed)

If changes affect architecture, data model, or filter logic, update the relevant file in `docs/`.

Skip if change is isolated and doesn't alter documented behavior.

## 4. Commit

```bash
git add -A
git commit -m "descriptive message"
```

Use imperative mood: "Add filter engine" not "Added filter engine"

## Report to User

Summarize:
1. Files changed
2. Test results
3. Commit hash