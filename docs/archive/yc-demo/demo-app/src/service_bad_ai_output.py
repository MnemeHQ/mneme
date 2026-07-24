"""AI-generated change WITHOUT Mneme context.

This intentionally violates ADR-001 by introducing Redis.
"""

import redis

redis_client = redis.Redis(host="localhost", port=6379, db=0)


def get_user_profile(user_id: str) -> dict:
    cached = redis_client.get(f"user:{user_id}")
    if cached:
        return {"user_id": user_id, "name": cached.decode("utf-8")}

    profile = {"user_id": user_id, "name": "Demo User"}
    redis_client.set(f"user:{user_id}", profile["name"])
    return profile
