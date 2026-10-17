"""Spawned assessment worker; cancellation kills/reaps it before releasing admission.

Assessors must be picklable module-level objects. Isolation is for scheduling, not
for running untrusted Python. Startup and validation count against the deadline.
"""
import asyncio
import multiprocessing as mp
import pickle
import tempfile
import time


def _worker(assessment, claims, sources, path):
    try:
        rows = []
        by_id = {s.id: s for s in sources}
        for claim in claims:
            citations = assessment.candidates(claim, sources)
            if not isinstance(citations, list) or len(citations) > len(sources):
                raise ValueError("invalid assessment output")
            for citation in citations:
                citation.validate(by_id[citation.source_id])
            rows.append(citations)
        payload = (True, rows)
    except Exception:
        payload = (False, None)
    with open(path, "wb") as stream:
        pickle.dump(payload, stream)


async def assess(assessment, claims, sources, deadline):
    if time.monotonic() >= deadline:
        raise TimeoutError
    with tempfile.TemporaryDirectory(prefix="evidence-assessment-") as folder:
        path = folder + "/result"
        process = mp.get_context("spawn").Process(
            target=_worker, args=(assessment, claims, sources, path), daemon=True)
        try:
            try:
                process.start()
            except Exception:
                raise ValueError("assessment must be spawn-compatible") from None
            while process.is_alive():
                if time.monotonic() >= deadline:
                    raise TimeoutError
                await asyncio.sleep(min(.005, max(0, deadline - time.monotonic())))
            if time.monotonic() >= deadline:
                raise TimeoutError
            if process.exitcode != 0:
                raise ValueError("assessment worker failed")
            with open(path, "rb") as stream:
                ok, rows = pickle.load(stream)
            if not ok:
                raise ValueError("invalid assessment output")
            if time.monotonic() >= deadline:
                raise TimeoutError
            return rows
        finally:
            if process.pid is not None:
                if process.is_alive():
                    process.kill()
                process.join()  # Reap before admitting replacement work.
                process.close()
