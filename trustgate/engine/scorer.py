from __future__ import annotations

from typing import Iterable, Sequence

from trustgate.engine.policy import band_for
from trustgate.models import ActionRequest, TrustAssessment
from trustgate.signals.base import Signal


class TrustScorer:
    """Runs every signal and combines them into a single 0..100 trust score.

    The score is a weighted blend of per-signal risk. It stays explainable:
    the assessment carries each signal's risk, weight, and reason so you can
    always answer "why 28?" instead of waving at a black box.
    """

    def __init__(self, signals: Iterable[Signal]):
        self.signals = list(signals)

    def assess(
        self, request: ActionRequest, history: Sequence[ActionRequest] = ()
    ) -> TrustAssessment:
        results = [s.evaluate(request, history) for s in self.signals]
        total_weight = sum(r.weight for r in results) or 1.0
        weighted_risk = sum(r.risk * r.weight for r in results) / total_weight
        score = round(100 * (1 - weighted_risk))
        return TrustAssessment(score=score, band=band_for(score), signals=results)
