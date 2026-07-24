"""Approved cache abstraction for the demo app.

All cache access must go through this module.
In the real product, this would be backed by Postgres.
"""

_store = {}


def get_cached_value(key: str):
    return _store.get(key)


def set_cached_value(key: str, value):
    _store[key] = value
    return value
