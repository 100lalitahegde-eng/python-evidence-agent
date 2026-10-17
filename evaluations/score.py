"""Report candidate recall and false support risk; does not invent stance labels."""
import json
from pathlib import Path
from evidence_agent.assessment import LexicalAssessment
from evidence_agent.domain import Source


def evaluate():
    data = json.loads(Path(__file__).with_name('labeled.json').read_text())
    totals = {label: {'total': 0, 'selected': 0} for label in ('support', 'contradiction', 'irrelevant')}
    details = []
    for case in data['cases']:
        source = Source(case['id'], case['domain'], 'local://evaluation', case['passage'])
        selected = bool(LexicalAssessment().candidates(case['claim'], (source,)))
        totals[case['label']]['total'] += 1
        totals[case['label']]['selected'] += int(selected)
        details.append({'id': case['id'], 'label': case['label'], 'candidate_selected': selected})
    return {'dataset_version': data['version'], 'provenance': data['provenance'], 'by_label': totals,
            'stance_accuracy': None, 'reason': 'LexicalAssessment does not predict stance. Selection must never be interpreted as support.', 'cases': details}


if __name__ == '__main__':
    print(json.dumps(evaluate(), indent=2))
