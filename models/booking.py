from __future__ import annotations

from datetime import datetime
from enum import Enum
from urllib.parse import urlparse

from models.errors import ConflictError, ValidationError
from utils import timeutil


# bookings

class BookingStatus(str, Enum):
    PENDING = "Pending"
    CONFIRMED = "Confirmed"
    DECLINED = "Declined"
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"

    @classmethod
    def active(cls) -> list[BookingStatus]:
        return [cls.PENDING, cls.CONFIRMED]

    @classmethod
    def closed(cls) -> list[BookingStatus]:
        return [cls.COMPLETED, cls.DECLINED, cls.CANCELLED]


class Booking:
    """a consultation request"""

    PURPOSE_MAX = 200

    def __init__(self, student_id: str, teacher_id: str, slot_id: str, course_id: str,
                 purpose: str, status: BookingStatus | str = BookingStatus.PENDING,
                 meeting_link: str | None = None, note: str | None = None,
                 booking_id: str | None = None, created_at: datetime | None = None):
        purpose = (purpose or "").strip()
        if not purpose:
            raise ValidationError("Please describe the purpose of the meeting.")
        if len(purpose) > self.PURPOSE_MAX:
            raise ValidationError(f"The purpose must be {self.PURPOSE_MAX} characters or fewer.")
        self._id = booking_id
        self._student_id = student_id
        self._teacher_id = teacher_id
        self._slot_id = slot_id
        self._course_id = course_id
        self._purpose = purpose
        self._status = BookingStatus(status)   # private
        self._meeting_link = meeting_link or None
        self._note = note or None
        self._created_at = created_at

    # properties
    @property
    def id(self) -> str | None:
        return self._id

    @property
    def student_id(self) -> str:
        return self._student_id

    @property
    def teacher_id(self) -> str:
        return self._teacher_id

    @property
    def slot_id(self) -> str:
        return self._slot_id

    @property
    def course_id(self) -> str:
        return self._course_id

    @property
    def purpose(self) -> str:
        return self._purpose

    @property
    def status(self) -> BookingStatus:
        return self._status

    @property
    def meeting_link(self) -> str | None:
        return self._meeting_link

    @property
    def note(self) -> str | None:
        return self._note

    @property
    def created_at(self) -> datetime | None:
        return self._created_at

    # status changes
    def _transition(self, allowed_from: list[BookingStatus], to: BookingStatus) -> None:
        if self._status not in allowed_from:
            raise ConflictError(
                f"This booking is already {self._status.value.lower()} and can't be changed to "
                f"{to.value.lower()}."
            )
        self._status = to

    def accept(self, meeting_link: str | None = None) -> None:
        """accept, needs a meeting link"""
        link = self.validate_link(meeting_link)
        if link is None and self._status == BookingStatus.PENDING:
            # not pending gets the other error
            raise ValidationError("Add a meeting link before accepting this request.")
        self._transition([BookingStatus.PENDING], BookingStatus.CONFIRMED)
        self._meeting_link = link
        self._note = None

    def decline(self, reason: str | None = None) -> None:
        self._transition([BookingStatus.PENDING], BookingStatus.DECLINED)
        self._note = (reason or "").strip() or None

    def cancel(self, reason: str | None = None) -> None:
        self._transition(BookingStatus.active(), BookingStatus.CANCELLED)
        self._note = (reason or "").strip() or None

    def complete(self, note: str | None = None) -> None:
        self._transition([BookingStatus.CONFIRMED], BookingStatus.COMPLETED)
        if note:
            self._note = note

    def update_meeting_link(self, meeting_link: str | None) -> None:
        if self._status != BookingStatus.CONFIRMED:
            raise ConflictError("A meeting link can only be changed on a confirmed booking.")
        self._meeting_link = self.validate_link(meeting_link)

    @staticmethod
    def validate_link(link: str | None) -> str | None:
        link = (link or "").strip()
        if not link:
            return None
        if "://" not in link:
            link = "https://" + link
        parsed = urlparse(link)
        if parsed.scheme not in ("http", "https") or "." not in parsed.netloc:
            raise ValidationError("The meeting link doesn't look like a valid web address.")
        return link

    # saving
    def to_record(self) -> dict:
        record = {
            "student_id": self._student_id,
            "teacher_id": self._teacher_id,
            "slot_id": self._slot_id,
            "course_id": self._course_id,
            "purpose": self._purpose,
            "status": self._status.value,
            "meeting_link": self._meeting_link,
            "note": self._note,
        }
        if self._id:
            record["id"] = self._id
        return record

    @classmethod
    def from_record(cls, record: dict) -> Booking:
        return cls(record["student_id"], record["teacher_id"], record["slot_id"],
                   record["course_id"], record["purpose"], record.get("status", "Pending"),
                   meeting_link=record.get("meeting_link"), note=record.get("note"),
                   booking_id=record.get("id"),
                   created_at=timeutil.parse(record.get("created_at")))

    def __repr__(self) -> str:
        return f"Booking({self._id!r}, {self._status.value})"
