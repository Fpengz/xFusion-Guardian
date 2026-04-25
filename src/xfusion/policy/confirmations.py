from __future__ import annotations


def is_confirmed(user_input: str, expected_phrase: str) -> bool:
    """Check for exact typed confirmation phrase."""
    return user_input.strip() == expected_phrase.strip()
