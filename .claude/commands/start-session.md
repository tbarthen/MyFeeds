---
description: Review guidelines and establish session baseline
---

# Start Session

Run at the beginning of each coding session.

## 1. Review CLAUDE.md

Re-read `CLAUDE.md` in the project root. Pay attention to:
- Decision framework (simplicity-first)
- Code principles (SRP, DRY, defensive)
- Critical constraints

## 2. Understand the Task

Before writing code:
- Clarify ambiguous requirements — ask, don't assume
- Identify subjective decisions that need user input
- Flag if task conflicts with CLAUDE.md principles

## 3. Establish Baseline (If Needed)

For changes that could have side effects:
1. Run `pytest` to capture current test state
2. Note which tests pass/fail before starting
3. Identify what existing code the change touches

Skip baseline for isolated new features with no integration points.