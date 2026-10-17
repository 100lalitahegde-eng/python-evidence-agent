import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from evidence_agent.store import RunStore


def result(i):
    return {'schema_version':'1.0','run_id':str(i),'payload':'x'*2048}


class RetentionTests(unittest.TestCase):
    def test_bound_reopen_and_failed_insert_atomicity(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'runs.db'
            store = RunStore(path, max_runs=3)
            for i in range(10):
                store.save(result(i))
            with sqlite3.connect(path) as conn:
                self.assertEqual(conn.execute('select count(*) from runs').fetchone()[0], 3)
            self.assertIsNone(store.get('6'))
            self.assertEqual(RunStore(path).get('7'), result(7))
            with self.assertRaises(sqlite3.IntegrityError):
                store.save(result(9))
            self.assertEqual(store.get('7'), result(7))
            store.save(result(10))
            self.assertIsNone(store.get('7'))
            self.assertEqual(store.get('10'), result(10))

    def test_retention_defaults_off_and_invalid_policy(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'runs.db'
            store = RunStore(path)
            for i in range(5):
                store.save(result(i))
            self.assertEqual(store.get('0'), result(0))
            for n in (True,0,-1,1.5,1_000_001):
                with self.assertRaises(ValueError):
                    RunStore(path, n)
