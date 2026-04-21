from __future__ import annotations

import os


def is_protected(path: str, protected_paths: tuple[str, ...]) -> bool:
    """Check if a path or its parent is in the protected list."""
    try:
        abs_path = os.path.abspath(path)
        for protected in protected_paths:
            abs_protected = os.path.abspath(protected)
            if abs_path == abs_protected:
                return True
            if abs_path.startswith(abs_protected + os.sep):
                return True
    except (ValueError, OSError):
        return True  # Refuse on invalid paths
    return False
