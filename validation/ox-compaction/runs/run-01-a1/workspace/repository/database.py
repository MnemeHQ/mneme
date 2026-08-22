"""Database opening helpers for the repository layer.

This is the single place where raw database clients are constructed.
Services must go through repositories instead of touching this module
(or ``db.client``) directly.
"""

import os

from db.client import DatabaseClient

DEFAULT_DB_PATH = os.path.join("data", "app.db")


def open_database(path=None):
    """Open the application database at ``path``, creating it if needed.

    Creates parent directories as needed. Defaults to ``data/app.db``
    when no path is given.
    """
    path = resolve_db_path(path)
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    return DatabaseClient(path)


def resolve_db_path(path=None):
    """Return ``path``, or the default application database path."""
    return path if path else DEFAULT_DB_PATH
