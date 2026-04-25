from __future__ import annotations

from pathlib import Path

SECRET_PATH_MARKERS = (
    "/.ssh/id_rsa",
    "/.ssh/id_dsa",
    "/.ssh/id_ecdsa",
    "/.ssh/id_ed25519",
    "/.kube/config",
    "/.aws/credentials",
    "/.config/gcloud/",
    "/.azure/",
    "/secrets/",
    "/secret/",
    "/run/secrets/",
    "/var/run/secrets/",
)

SECRET_FILENAMES = {
    ".env",
    ".env.local",
    ".env.production",
    "credentials",
    "credentials.json",
    "database.yml",
    "database.yaml",
    "db.conf",
    "db.ini",
}


def is_secret_path(path: str) -> bool:
    """Return True for deterministic known-secret path classes."""
    raw = str(path)
    lowered = raw.lower()
    if lowered == "/etc/shadow":
        return True
    if any(marker in lowered for marker in SECRET_PATH_MARKERS):
        return True

    name = Path(raw).name.lower()
    if name in SECRET_FILENAMES:
        return True
    if name.endswith((".pem", ".key", ".p12", ".pfx")):
        return True
    return "credential" in name or "secret" in name
