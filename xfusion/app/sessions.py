from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from xfusion.graph.state import AgentGraphState


class SessionManager:
    """Handles saving and loading of agent sessions."""

    def __init__(self, base_dir: Path | None = None):
        if base_dir is None:
            self.base_dir = Path.home() / ".xfusion" / "sessions"
        else:
            self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save_session(self, session_id: str, state: dict[str, Any]) -> None:
        """Save current state to a session file."""
        # Convert state dict to AgentGraphState for validation and serialization
        # (Assuming the dict matches the schema)
        graph_state = AgentGraphState.model_validate(state)

        file_path = self.base_dir / f"{session_id}.json"
        with open(file_path, "w") as f:
            f.write(graph_state.model_dump_json(indent=2))

        # Update session index or metadata if needed
        metadata_path = self.base_dir / "index.json"
        metadata = self._load_metadata()
        metadata[session_id] = {
            "updated_at": datetime.now().isoformat(),
            "last_input": state.get("user_input", "")[:50],
        }
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)

    def load_session(self, session_id: str) -> dict[str, Any]:
        """Load state from a session file."""
        file_path = self.base_dir / f"{session_id}.json"
        if not file_path.exists():
            raise FileNotFoundError(f"Session {session_id} not found.")

        with open(file_path) as f:
            content = f.read()
            return AgentGraphState.model_validate_json(content).model_dump()

    def list_sessions(self) -> list[dict[str, Any]]:
        """List all saved sessions with metadata."""
        metadata = self._load_metadata()
        return [
            {"id": sid, **meta}
            for sid, meta in sorted(
                metadata.items(), key=lambda x: x[1]["updated_at"], reverse=True
            )
        ]

    def _load_metadata(self) -> dict[str, Any]:
        metadata_path = self.base_dir / "index.json"
        if metadata_path.exists():
            with open(metadata_path) as f:
                return json.load(f)
        return {}
