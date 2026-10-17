"""30-minute qualification with bounded harness memory and process-tree RSS (Linux)."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import platform
import sqlite3
import tempfile
import time
from evidence_agent.assessment import LexicalAssessment
from evidence_agent.domain import Policy, Request, Source
from evidence_agent.service import EvidenceService
from evidence_agent.store import RunStore


class Workload:
    async def search(self, question, limit):
        return [question]
    async def read(self, source_id):
        size = int(source_id)
        sentence = 'Active holds consume available capacity. '
        return Source(source_id, 'Synthetic capacity note', 'local://capacity', (sentence*(size//len(sentence)+1))[:size])


def tree_rss(pid):
    """Sum RSS across descendants; shared pages may be counted more than once."""
    pending, seen, total = [pid], set(), 0
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        try:
            total += int(Path(f'/proc/{current}/statm').read_text().split()[1])*os.sysconf('SC_PAGE_SIZE')
            pending.extend(int(x) for x in Path(f'/proc/{current}/task/{current}/children').read_text().split())
        except (FileNotFoundError, ProcessLookupError):
            pass
    return total


class Histogram:
    def __init__(self):
        self.bins = [0]*30001
        self.count = 0
        self.maximum = 0
    def add(self, milliseconds):
        self.bins[min(30000,int(milliseconds))] += 1
        self.count += 1
        self.maximum = max(self.maximum,milliseconds)
    def percentile(self, q):
        if not self.count:
            return None
        n = max(1, int(self.count*q+.99999))
        for index,count in enumerate(self.bins):
            n -= count
            if n <= 0:
                return index+1 if index < 30000 else None
    def report(self):
        return {'count':self.count,'p50_upper_ms':self.percentile(.5),'p95_upper_ms':self.percentile(.95),'p99_upper_ms':self.percentile(.99),'max_ms':self.maximum}


async def stage(seconds, concurrency, path, progress):
    service = EvidenceService(Workload(),LexicalAssessment(),Policy(max_concurrent=concurrency))
    store = RunStore(path,max_runs=1000)
    normal,cancel = Histogram(),Histogram()
    completed, failures = 0, 0
    samples=[]
    started=time.monotonic()
    stop=started+seconds
    async def client(index):
        nonlocal completed, failures
        iteration=index
        while time.monotonic()<stop:
            size=(400,4000,40000)[iteration%3]
            claims=(1,5,20)[(iteration//3)%3]
            request=Request(str(size),('Active holds consume available capacity.',)*claims)
            began=time.monotonic()
            task=asyncio.create_task(service.run(request))
            if iteration%25==24:
                await asyncio.sleep(.01)
                if not task.done():
                    began=time.monotonic()
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        cancel.add((time.monotonic()-began)*1000)
                    iteration+=1
                    continue
            result=await task
            store.save(result)
            normal.add((time.monotonic()-began)*1000)
            completed+=1
            failures+=int(result['status']!='complete')
            iteration+=1
    async def sample():
        while time.monotonic()<stop:
            with sqlite3.connect(path) as db:
                count=db.execute('select count(*) from runs').fetchone()[0]
            sample={'elapsed_s':round(time.monotonic()-started,3),'completed':completed,
                    'tree_rss_bytes':tree_rss(os.getpid()),'database_bytes':path.stat().st_size,'retained_rows':count}
            samples.append(sample)
            progress.write_text(json.dumps({'stage_concurrency':concurrency,**sample}))
            await asyncio.sleep(min(5,max(0,stop-time.monotonic())))
    await asyncio.gather(*(client(i) for i in range(concurrency)),sample())
    with sqlite3.connect(path) as db:
        count=db.execute('select count(*) from runs').fetchone()[0]
        integrity=db.execute('pragma integrity_check').fetchone()[0]
    import multiprocessing
    return {'seconds':time.monotonic()-started,'concurrency':concurrency,'completed':completed,'failed_results':failures,
            'latency':normal.report(),'cancellation':cancel.report(),'retained_rows':count,'integrity':integrity,
            'active_workers_after':len(multiprocessing.active_children()),'admission_after':service._active,
            'max_sampled_tree_rss_bytes':max(s['tree_rss_bytes'] for s in samples),
            'database_bytes':path.stat().st_size,'samples':samples}


async def run(seconds, output):
    result={'python':platform.python_version(),'platform':platform.platform(),
            'workload':{'source_chars':[400,4000,40000],'claim_counts':[1,5,20],'retention_limit':1000,
                        'cancellation':'every 25th request, after 10ms if still pending',
                        'latency':'includes SQLite FULL-sync save; 1ms histogram upper bounds',
                        'memory':'sampled every 5s, sum of parent and descendants RSS, includes shared-page double counting'},'stages':[]}
    with tempfile.TemporaryDirectory() as folder:
        path=Path(folder)/'soak.db'
        for concurrency in (1,4,8):
            result['stages'].append(await stage(seconds,concurrency,path,output.with_suffix('.progress.json')))
            output.write_text(json.dumps(result,indent=2))
    result['complete']=True
    output.write_text(json.dumps(result,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--stage-seconds',type=int,default=600)
    parser.add_argument('--output',type=Path,default=Path('benchmarks/soak-results.json'))
    args=parser.parse_args()
    if not 1 <= args.stage_seconds <= 1200:
        parser.error('stage-seconds must be 1..1200')
    asyncio.run(run(args.stage_seconds,args.output))
