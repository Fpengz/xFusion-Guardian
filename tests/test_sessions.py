from __future__ import annotations

import json

from xfusion.app.sessions import SessionManager


def _base_state() -> dict[str, object]:
    return {
        "user_input": "find markdown files",
        "language": "en",
        "environment": {
            "distro_family": "darwin",
            "distro_version": "26.3",
            "current_user": "tester",
            "sudo_available": False,
            "systemd_available": False,
            "package_manager": "brew",
            "disk_pressure": "unknown",
            "session_locality": "local",
            "protected_paths": ["/", "/etc", "/boot", "/usr", "/var/lib"],
            "active_facts": {},
        },
    }


def test_save_session_ignores_transient_ui_fields(tmp_path):
    manager = SessionManager(base_dir=tmp_path)
    state = _base_state()
    state["debug_logs"] = ["[DEBUG] transient"]
    state["ui_only_field"] = {"selected_tab": "audit"}

    manager.save_session("abc12345", state)
    restored = manager.load_session("abc12345")

    assert "debug_logs" not in restored
    assert "ui_only_field" not in restored

    saved_payload = json.loads((tmp_path / "abc12345.json").read_text())
    assert "debug_logs" not in saved_payload
    assert "ui_only_field" not in saved_payload


def test_load_session_ignores_unknown_fields_from_disk(tmp_path):
    manager = SessionManager(base_dir=tmp_path)
    payload = _base_state()
    payload["unknown_saved_field"] = {"legacy": True}
    (tmp_path / "legacy123.json").write_text(json.dumps(payload))

    restored = manager.load_session("legacy123")

    assert restored["user_input"] == "find markdown files"
    assert "unknown_saved_field" not in restored
