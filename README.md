# XFusion

XFusion is a v0.1 safety-aware Linux administration agent for the AI Hackathon 2026 preliminary problem.

The frozen v0.1 spec is in [docs/specs/xfusion-v0.1.md](docs/specs/xfusion-v0.1.md).

The standardized verification suite is documented in
[docs/verification-suite.md](docs/verification-suite.md), with YAML scenarios under
[verification/scenarios](verification/scenarios).

The post-v0.1 target architecture is documented in
[docs/architecture/pydantic-langgraph-blueprint.md](docs/architecture/pydantic-langgraph-blueprint.md).

## Development

Use `uv` for environment and command management:

```bash
uv sync --dev
uv run pytest
uv run ruff check .
uv run ruff format .
uv run ty check
```

The implementation targets Python 3.11+ and a Lima Ubuntu 24.04 VM for the official demo sandbox.
