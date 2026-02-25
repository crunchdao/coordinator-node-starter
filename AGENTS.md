# Coordinator Node — Agent Instructions

## Code Formatting (MANDATORY)

This project uses **Ruff** for formatting and linting all Python code.

**Before every commit, run:**
```bash
make fmt
```

**Rules:**
- Always run `make fmt` after editing Python files — no exceptions.
- Never disable or skip ruff rules without explicit user approval.
- Imports are sorted automatically (isort via ruff).
- Line length is 88 characters (ruff formatter handles wrapping).

**Commands:**
| Command | Purpose |
|---------|---------|
| `make fmt` | Auto-format and auto-fix all Python files |
| `make lint` | Check formatting and linting (no changes) |
| `make check` | Lint + tests |
| `make test` | Runs lint then pytest |

## Testing

```bash
make test
```

Tests live in `tests/`. PYTHONPATH includes `base/challenge` and `base/node`.
