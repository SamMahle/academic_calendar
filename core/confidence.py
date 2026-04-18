"""
Confidence scoring for extracted events.

Scoring rubric (total max 1.0):
  +0.4  event-type keyword matched (WPR, TEE, Writ, etc.)
  +0.3  lesson number or explicit date extracted cleanly
  +0.2  course code found in the same context window
  +0.1  no conflict with other extracted events
"""

from dataclasses import dataclass
from typing import Optional

THRESHOLD_AUTO_ACCEPT = 0.7
THRESHOLD_COPILOT_HANDOFF = 0.4


@dataclass
class ConfidenceFactors:
    has_event_keyword: bool = False
    has_date_or_lesson: bool = False
    has_course_code: bool = False
    no_conflict: bool = True

    def score(self) -> float:
        s = 0.0
        if self.has_event_keyword:
            s += 0.4
        if self.has_date_or_lesson:
            s += 0.3
        if self.has_course_code:
            s += 0.2
        if self.no_conflict:
            s += 0.1
        return round(s, 2)


def needs_review(score: float) -> bool:
    return score < THRESHOLD_AUTO_ACCEPT


def needs_copilot(score: float) -> bool:
    return score < THRESHOLD_COPILOT_HANDOFF
