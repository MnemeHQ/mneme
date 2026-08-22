import sqlite3


class DatabaseClient:
    """Low-level SQLite client. Feature code must not use this class directly."""

    def __init__(self, path):
        self._conn = sqlite3.connect(path)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS members ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL)"
        )
        self._conn.commit()

    def execute(self, sql, params=()):
        cur = self._conn.execute(sql, params)
        self._conn.commit()
        return cur

    def query(self, sql, params=()):
        return self._conn.execute(sql, params).fetchall()

    def close(self):
        self._conn.close()
