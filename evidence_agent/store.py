"""Optional explicit result retention. Local SQLite, no claim of distributed durability."""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3


class RunStore:
    def __init__(self, path: Path, max_runs: int | None = None):
        if max_runs is not None and (type(max_runs) is not int or not 1 <= max_runs <= 1_000_000):
            raise ValueError("max_runs must be 1..1000000 or None")
        self.max_runs = max_runs
        self.path = str(path)
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, result TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=2)
        try:
            conn.execute("PRAGMA synchronous=FULL")
            with conn:
                yield conn
        finally:
            conn.close()

    def save(self, result: dict) -> None:
        if result.get("schema_version") != "1.0" or not isinstance(result.get("run_id"), str):
            raise ValueError("unsupported result envelope")
        payload = json.dumps(result, sort_keys=True, allow_nan=False)
        if len(payload.encode("utf-8")) > 10_000_000:
            raise ValueError("result exceeds retention limit")
        with self._connect() as conn:
            # Never overwrite a previous run, including an accidental duplicate ID.
            conn.execute("INSERT INTO runs(run_id, result) VALUES (?, ?)", (result["run_id"], payload))
            if self.max_runs is not None:
                # Insertion and eviction are one transaction; ties use insertion rowid.
                conn.execute("DELETE FROM runs WHERE rowid NOT IN (SELECT rowid FROM runs ORDER BY rowid DESC LIMIT ?)", (self.max_runs,))

    def get(self, run_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT result FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        return json.loads(row[0]) if row else None

