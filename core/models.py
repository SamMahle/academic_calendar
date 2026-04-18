from datetime import date
from typing import Literal, Optional
from pydantic import BaseModel, field_validator


DayType = Literal["1", "2", "R", "holiday", "tee", "grad", "weekend", "break"]
EventType = Literal["WPR", "TEE", "Writ", "PS", "HW", "Quiz", "Lab", "Project", "Other"]
EventSource = Literal["parsed", "copilot", "manual"]
CourseTrack = Literal[1, 2]


class DayMeta(BaseModel):
    day_type: DayType
    notes: list[str] = []

    @property
    def is_academic(self) -> bool:
        return self.day_type in ("1", "2")

    @property
    def track(self) -> Optional[int]:
        if self.day_type in ("1", "2"):
            return int(self.day_type)
        return None


class Event(BaseModel):
    course_code: str
    event_type: EventType
    title: str
    date: date
    lesson_ref: Optional[str] = None
    weight_pct: Optional[float] = None
    confidence: float
    source: EventSource
    notes: Optional[str] = None

    @field_validator("confidence")
    @classmethod
    def clamp_confidence(cls, v: float) -> float:
        return max(0.0, min(1.0, v))

    @field_validator("weight_pct")
    @classmethod
    def validate_weight(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and not (0.0 <= v <= 100.0):
            raise ValueError("weight_pct must be between 0 and 100")
        return v


class Course(BaseModel):
    code: str
    short_name: str
    track: CourseTrack
    color: str  # hex without leading #, e.g. "FF6B6B"
    events: list[Event] = []

    @field_validator("color")
    @classmethod
    def validate_hex_color(cls, v: str) -> str:
        v = v.lstrip("#")
        if len(v) != 6:
            raise ValueError("color must be a 6-character hex string")
        int(v, 16)  # raises ValueError if not valid hex
        return v.upper()
