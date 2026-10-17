"""Closed-loop sustained runs, explicit storage growth and cancellation probe."""
import argparse
import asyncio
import json
import multiprocessing
import os
from pathlib import Path
import platform
import resource
import sqlite3
import tempfile
import time
from evidence_agent.assessment import LexicalAssessment
from evidence_agent.corpus import Corpus, LocalRetrieval
from evidence_agent.domain import Policy, Request
from evidence_agent.service import EvidenceService
from evidence_agent.store import RunStore


class SlowAssessment:
    def candidates(self, claim, sources):
        time.sleep(30)
        return []


def pct(values, fraction):
    return sorted(values)[min(len(values)-1, int((len(values)-1)*fraction))]


def rss():
    return int(Path('/proc/self/statm').read_text().split()[1]) * os.sysconf('SC_PAGE_SIZE')


async def measure(seconds, concurrency):
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder)/'runs.db'
        store = RunStore(path)
        service = EvidenceService(LocalRetrieval(Corpus(Path('corpus.json'))), LexicalAssessment(), Policy(max_concurrent=concurrency))
        request = Request('reservation capacity', ('Active holds consume capacity.',))
        latencies, samples, statuses = [], [], {}
        started = time.monotonic()
        stop = started + seconds
        initial = path.stat().st_size
        initial_rss = rss()
        async def worker():
            while time.monotonic() < stop:
                begin = time.monotonic()
                result = await service.run(request)
                # Measures real serial SQLite FULL-sync retention in the hosting loop.
                store.save(result)
                latencies.append((time.monotonic()-begin)*1000)
                statuses[result['status']] = statuses.get(result['status'], 0)+1
        async def sampler():
            while time.monotonic() < stop:
                samples.append({'seconds':round(time.monotonic()-started,2), 'completed':len(latencies), 'rss_bytes':rss(), 'db_bytes':path.stat().st_size,
                                'wal_bytes':Path(str(path)+'-wal').stat().st_size if Path(str(path)+'-wal').exists() else 0})
                await asyncio.sleep(1)
        await asyncio.gather(*(worker() for _ in range(concurrency)), sampler())
        elapsed = time.monotonic()-started
        with sqlite3.connect(path) as db:
            count = db.execute('select count(*) from runs').fetchone()[0]
            integrity = db.execute('pragma integrity_check').fetchone()[0]
        cancel_ms=[]
        service.assessment=SlowAssessment()
        for _ in range(20):
            task=asyncio.create_task(service.run(request))
            await asyncio.sleep(.075)
            begin=time.monotonic()
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            cancel_ms.append((time.monotonic()-begin)*1000)
        return {'python':platform.python_version(),'platform':platform.platform(),'duration_seconds':elapsed,'requested_seconds':seconds,'concurrency':concurrency,
                'workload':'closed-loop local synthetic corpus; process-isolated lexical assessment; SQLite FULL synchronous retention; no external network',
                'completed':len(latencies),'statuses':statuses,'runs_per_second':len(latencies)/elapsed,
                'latency_ms':{'p50':pct(latencies,.5),'p95':pct(latencies,.95),'p99':pct(latencies,.99),'max':max(latencies)},
                'retention':{'rows':count,'integrity':integrity,'initial_bytes':initial,'final_bytes':path.stat().st_size,'bytes_per_run':(path.stat().st_size-initial)/count},
                'rss':{'initial_bytes':initial_rss,'final_bytes':rss(),'parent_peak_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'largest_child_peak_kib':resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss},
                'cancellation':{'trials':len(cancel_ms),'p95_ms':pct(cancel_ms,.95),'max_ms':max(cancel_ms),'children_remaining':len(multiprocessing.active_children()),'admission_remaining':service._active},'samples':samples}


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--seconds',type=float,default=60)
    parser.add_argument('--concurrency',type=int,default=4)
    args=parser.parse_args()
    if not 1 <= args.seconds <= 3600 or not 1 <= args.concurrency <= 100:
        parser.error('seconds must be 1..3600 and concurrency 1..100')
    print(json.dumps(asyncio.run(measure(args.seconds,args.concurrency)),indent=2))
