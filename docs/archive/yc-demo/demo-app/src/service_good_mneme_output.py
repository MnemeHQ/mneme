"""AI-generated change WITH Mneme context.

This follows ADR-001 by using the approved cache abstraction.
"""

from src.cache import get_cached_value, set_cached_value


def get_user_profile(user_id: str) -> dict:
    cache_key = f"user:{user_id}"
    cached = get_cached_value(cache_key)
    if cached:
        return cached

    profile = {"user_id": user_id, "name": "Demo User"}
    return set_cached_value(cache_key, profile)
