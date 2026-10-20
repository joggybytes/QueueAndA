from __future__ import annotations

from datetime import datetime
from enum import Enum

from models.errors import ConflictError, ValidationError
from utils import timeutil


# schedule slots

class SlotStatus(str, Enum):
    OPEN = "open"
    BOOKED = "booked"
    REMOVED = "removed"


class ScheduleSlot:
    """a time slot a teacher posted"""

    def __init__(self, teacher_id: str, start: datetime, end: datetime,
                 status: SlotStatus | str = SlotStatus.OPEN, slot_id: str | None = None):
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("Slot times must be timezone-aware.")
        if end <= start:
            raise ValidationError("End time must be after the start time.")
        self._id = slot_id
        self._teacher_id = teacher_id
        self._start = start
        self._end = end
        self._status = SlotStatus(status)

    @property
    def id(self) -> str | None:
        return self._id

    @property
    def teacher_id(self) -> str:
        return self._teacher_id

    @property
    def start(self) -> datetime:
        return self._start

    @property
    def end(self) -> datetime:
        return self._end

    @property
    def status(self) -> SlotStatus:
        return self._status

    @property
    def is_open(self) -> bool:
        return self._status == SlotStatus.OPEN

    @property
    def is_booked(self) -> bool:
        return self._status == SlotStatus.BOOKED

    @property
    def is_removed(self) -> bool:
        return self._status == SlotStatus.REMOVED

    @property
    def label(self) -> str:
        return timeutil.fmt_range(self._start, self._end)

    def has_started(self, at: datetime) -> bool:
        return at >= self._start

    def has_ended(self, at: datetime) -> bool:
        return at >= self._end

    def overlaps(self, start: datetime, end: datetime) -> bool:
        return self._start < end and start < self._end

    # status changes
    def lock(self) -> None:
        if not self.is_open:
            raise ConflictError("This schedule is no longer open.")
        self._status = SlotStatus.BOOKED

    def release(self) -> None:
        if self.is_booked:
            self._status = SlotStatus.OPEN

    def remove(self) -> None:
        if self.is_booked:
            raise ValidationError("This schedule has a confirmed booking. Cancel the booking first.")
        self._status = SlotStatus.REMOVED

    # saving
    def to_record(self) -> dict:
        record = {
            "teacher_id": self._teacher_id,
            "start_time": timeutil.to_iso(self._start),
            "end_time": timeutil.to_iso(self._end),
            "status": self._status.value,
        }
        if self._id:
            record["id"] = self._id
        return record

    @classmethod
    def from_record(cls, record: dict) -> ScheduleSlot:
        return cls(record["teacher_id"], timeutil.parse(record["start_time"]),
                   timeutil.parse(record["end_time"]), record.get("status", "open"),
                   slot_id=record.get("id"))

    def __repr__(self) -> str:
        return f"ScheduleSlot({self._id!r}, {self._start:%Y-%m-%d %H:%M}, {self._status.value})"
