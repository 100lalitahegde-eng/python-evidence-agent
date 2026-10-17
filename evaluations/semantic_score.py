"""Frozen-set semantic scorecard; abstention counts as missed gold classifications."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import platform
import time
from evidence_agent.domain import Source
from evidence_agent.semantic import SemanticAssessment, MODEL, REVISION

LABELS=('support','contradiction','irrelevant','uncertain')


def metrics(records):
    confusion={gold:{pred:0 for pred in LABELS} for gold in LABELS}
    for row in records:
        confusion[row['gold']][row['predicted']]+=1
    per_label={}
    for label in LABELS:
        tp=confusion[label][label]
        predicted=sum(confusion[g][label] for g in LABELS)
        actual=sum(confusion[label].values())
        precision=tp/predicted if predicted else None
        recall=tp/actual if actual else None
        per_label[label]={'precision':precision,'recall':recall,'actual':actual,'predicted':predicted}
    total=len(records)
    return {'confusion':confusion,'per_label':per_label,
            'accuracy':sum(confusion[l][l] for l in LABELS)/total if total else None,
            'abstention_rate':sum(confusion[g]['uncertain'] for g in LABELS)/total if total else None,
            'contradiction_as_support':confusion['contradiction']['support']}


def evaluate(path):
    data=json.loads(path.read_text())
    assessment=SemanticAssessment()
    started=time.monotonic()
    records=[]
    for case in data['cases']:
        source=Source(case['id'],case['domain'],'local://evaluation',case['passage'])
        judgment=assessment.assess_claim(case['claim'],(source,)).judgments[0]
        judgment.validate(source)
        records.append({'id':case['id'],'gold':case['label'],'predicted':judgment.label,'score':judgment.score,'reason':judgment.reason})
    return {'model':MODEL,'revision':REVISION,'threshold':assessment.threshold,'margin':assessment.margin,
            'dataset':path.name,'dataset_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'provenance':data['provenance'],'independent_review':'pending','python':platform.python_version(),
            'duration_seconds':time.monotonic()-started,'metrics':metrics(records),'records':records}


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--dataset',type=Path,default=Path('evaluations/heldout.json'))
    parser.add_argument('--output',type=Path,default=Path('evaluations/semantic-results.json'))
    args=parser.parse_args()
    report=evaluate(args.dataset)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='records'},indent=2))
