# Git Hooks

This repo uses local git hooks configured with:

```bash
git config core.hooksPath scripts/git-hooks
git config commit.template .gitmessage
```

## Hooks

- `pre-commit`: runs the project verification stack through `uv`.
- `commit-msg`: enforces a small Conventional Commit subject format.

The checks are intentionally the same commands documented in `AGENTS.md`:

```bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run ty check
```

