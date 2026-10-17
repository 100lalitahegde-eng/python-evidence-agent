"""Opt-in live smoke test; exits nonzero if no real source is retrieved."""
import asyncio
import json
from pathlib import Path
from evidence_agent.assessment import LexicalAssessment
from evidence_agent.domain import Policy,Request
from evidence_agent.service import EvidenceService
from evidence_agent.wikipedia import WikipediaRetrieval


async def run():
    service=EvidenceService(WikipediaRetrieval('EvidenceAgent/0.4 (https://github.com/100lalitahegde-eng/python-evidence-agent)'),LexicalAssessment(),
                            Policy(deadline_seconds=45,call_timeout_seconds=10,max_reads=1,max_attempts=2))
    result=await service.run(Request('Earth planet',('Earth is a planet.',)))
    report={'passed':result['status']=='complete' and bool(result['sources']), 'result':result}
    Path('live-retrieval.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
    return report['passed']


if __name__=='__main__':
    raise SystemExit(0 if asyncio.run(run()) else 1)
