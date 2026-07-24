"""Demo service before AI changes."""


def get_user_profile(user_id: str) -> dict:
    # Imagine this calls the database.
    return {"user_id": user_id, "name": "Demo User"}
