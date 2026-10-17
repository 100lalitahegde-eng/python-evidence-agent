"""Optional local NLI; probabilities describe model output, never factual truth."""
from dataclasses import dataclass
import math
from .corpus import terms
from .domain import Citation, Source

MODEL = 'cross-encoder/nli-deberta-v3-small'
REVISION = 'fa2804872c3b4bd748f38c0185cc85775361e735'
LABELS = {'support', 'contradiction', 'irrelevant', 'uncertain'}


@dataclass(frozen=True)
class Judgment:
    source_id: str
    label: str
    score: float | None
    reason: str
    citation: Citation | None = None

    def validate(self, source):
        if self.source_id != source.id or self.label not in LABELS:
            raise ValueError('invalid judgment')
        if self.score is not None and (type(self.score) not in (int, float) or not math.isfinite(self.score) or not 0 <= self.score <= 1):
            raise ValueError('invalid score')
        if not isinstance(self.reason, str) or not 1 <= len(self.reason) <= 128:
            raise ValueError('invalid reason')
        if self.label != 'uncertain' and self.citation is None:
            raise ValueError('decisive judgment requires an exact citation')
        if self.citation is not None:
            self.citation.validate(source)


@dataclass
class AssessedClaim:
    citations: list[Citation]
    judgments: list[Judgment]
    model: str = MODEL
    revision: str = REVISION


def decide(probabilities, claim, passage, threshold=.9, margin=.2):
    """Neutral is not automatically irrelevant: related neutral text stays uncertain."""
    if set(probabilities) != {'entailment', 'contradiction', 'neutral'}:
        raise ValueError('unknown NLI labels')
    values = list(probabilities.values())
    if any(type(v) not in (float, int) or not math.isfinite(v) or not 0 <= v <= 1 for v in values) or abs(sum(values)-1) > .001:
        raise ValueError('invalid NLI probabilities')
    ordered = sorted(probabilities, key=probabilities.get, reverse=True)
    label, score = ordered[0], probabilities[ordered[0]]
    if score < threshold or score-probabilities[ordered[1]] < margin:
        return 'uncertain', score, 'low_confidence_or_margin'
    if label == 'neutral':
        if not (terms(claim) & terms(passage)):
            return 'irrelevant', score, 'neutral_and_no_content_word_overlap'
        return 'uncertain', score, 'neutral_is_not_proof_of_irrelevance'
    return ('support' if label == 'entailment' else 'contradiction'), score, 'nli_prediction_requires_review'


class SemanticAssessment:
    def __init__(self, threshold=.9, margin=.2, max_tokens=512):
        if (type(threshold) not in (int,float) or not .5 <= threshold <= 1
                or type(margin) not in (int,float) or not 0 <= margin <= 1
                or type(max_tokens) is not int or not 32 <= max_tokens <= 512):
            raise ValueError('invalid semantic policy')
        self.threshold, self.margin, self.max_tokens = threshold, margin, max_tokens
        self._runtime = None

    def __getstate__(self):
        return {'threshold':self.threshold, 'margin':self.margin, 'max_tokens':self.max_tokens, '_runtime':None}

    def _load(self):
        if self._runtime is None:
            import torch
            from transformers import AutoTokenizer, AutoModelForSequenceClassification
            torch.set_num_threads(1)
            tokenizer = AutoTokenizer.from_pretrained(MODEL, revision=REVISION, local_files_only=True, trust_remote_code=False)
            model = AutoModelForSequenceClassification.from_pretrained(
                MODEL, revision=REVISION, local_files_only=True, trust_remote_code=False, use_safetensors=True)
            mapping = {int(k):v.lower() for k,v in model.config.id2label.items()}
            if set(mapping) != {0,1,2} or set(mapping.values()) != {'entailment','contradiction','neutral'}:
                raise ValueError('unexpected model labels')
            self._runtime = torch, tokenizer, model.eval(), mapping
        return self._runtime

    def assess_claim(self, claim: str, sources: tuple[Source, ...]):
        citations, judgments = [], []
        if not sources:
            return AssessedClaim([], [])
        torch, tokenizer, model, mapping = self._load()
        for source in sources:
            # Never silently truncate away a qualifying or contradicting sentence.
            if len(source.text) > 12000:
                judgments.append(Judgment(source.id, 'uncertain', None, 'input_exceeds_model_budget'))
                continue
            encoded = tokenizer(source.text, claim, return_tensors='pt', truncation=False)
            if encoded['input_ids'].shape[1] > self.max_tokens:
                judgments.append(Judgment(source.id, 'uncertain', None, 'input_exceeds_model_budget'))
                continue
            with torch.inference_mode():
                scores = torch.softmax(model(**encoded).logits[0], dim=-1).tolist()
            label, score, reason = decide({mapping[i]:float(v) for i,v in enumerate(scores)}, claim, source.text, self.threshold, self.margin)
            citation = Citation(source.id, source.digest, 0, len(source.text), source.text)
            citations.append(citation)
            judgments.append(Judgment(source.id, label, score, reason, citation))
        return AssessedClaim(citations, judgments)

    def candidates(self, claim, sources):
        return self.assess_claim(claim, sources).citations


def download():
    """Explicit setup only. Inference itself never downloads or sends input text."""
    from huggingface_hub import snapshot_download
    snapshot_download(MODEL, revision=REVISION,
                      allow_patterns=['*.json', 'spm.model', 'model.safetensors'])


if __name__ == '__main__':
    download()
