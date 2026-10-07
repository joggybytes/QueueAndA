"""Domain classes for Queue&A.

OOP principles applied here (see the conceptual framework):

* Encapsulation  - passwords, booking status and meeting links are kept in
                   "private" attributes and only change through methods such
                   as ``set_password()``, ``verify_password()``, ``accept()``,
                   ``decline()`` and ``cancel()``.
* Inheritance    - ``Teacher`` and ``Student`` inherit ID, name, email and the
                   login/password behaviour from ``User``.
* Polymorphism   - ``Teacher`` and ``Student`` each override
                   ``view_dashboard()`` and ``view_history()``.
* Abstraction    - ``User`` is an abstract base class; callers work with
                   "a user" without caring which kind it is.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, ClassVar
from urllib.parse import urlparse

from core import timeutil

if TYPE_CHECKING:  # avoid a circular import at runtime
    from core.manager import BookingManager


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class QueueAError(Exception):
    """Base class for errors that are safe to show to the user."""


class ValidationError(QueueAError):
    """Input that breaks a business rule."""


class AuthError(QueueAError):
    """Login or registration failed."""


class PermissionDenied(QueueAError):
    """A user tried to act on something that is not theirs."""


class ConflictError(QueueAError):
    """The data changed underneath us (e.g. slot was just taken)."""


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

class User(ABC):
    """Abstract base class for everyone who can log in to Queue&A."""

    ROLE: ClassVar[str] = ""
    _registry: ClassVar[dict[str, type[User]]] = {}

    _HASH_NAME = "sha256"
    _ITERATIONS = 200_000

    def __init__(self, name: str, email: str, user_id: str | None = None,
                 password_hash: str | None = None, created_at: datetime | None = None):
        name = (name or "").strip()
        email = (email or "").strip().lower()
        if not name:
            raise ValidationError("Name is required.")
        if not email:
            raise ValidationError("Email is required.")
        self._id = user_id
        self._name = name
        self._email = email
        self._password_hash = password_hash  # encapsulated: never exposed
        self._created_at = created_at

    # Subclasses register themselves so records can be turned back into the
    # right class (Teacher or Student) without if/else chains.
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.ROLE:
            User._registry[cls.ROLE] = cls

    # ---- read-only properties ------------------------------------------
    @property
    def id(self) -> str | None:
        return self._id

    @property
    def name(self) -> str:
        return self._name

    @property
    def email(self) -> str:
        return self._email

    @property
    def role(self) -> str:
        return self.ROLE

    @property
    def role_label(self) -> str:
        return self.ROLE.capitalize()

    def __eq__(self, other: object) -> bool:
        return isinstance(other, User) and self._id is not None and self._id == other._id

    def __hash__(self) -> int:
        return hash(self._id)

    # ---- password handling (encapsulation) -----------------------------
    def set_password(self, password: str) -> None:
        if len(password or "") < 8:
            raise ValidationError("Password must be at least 8 characters long.")
        salt = secrets.token_hex(16)
        digest = self._derive(password, salt, self._ITERATIONS)
        self._password_hash = f"pbkdf2_{self._HASH_NAME}${self._ITERATIONS}${salt}${digest}"

    def verify_password(self, password: str) -> bool:
        if not self._password_hash or password is None:
            return False
        try:
            algorithm, iterations, salt, digest = self._password_hash.split("$")
        except ValueError:
            return False
        if algorithm != f"pbkdf2_{self._HASH_NAME}":
            return False
        candidate = self._derive(password, salt, int(iterations))
        return hmac.compare_digest(candidate, digest)

    @classmethod
    def _derive(cls, password: str, salt: str, iterations: int) -> str:
        return hashlib.pbkdf2_hmac(cls._HASH_NAME, password.encode("utf-8"),
                                   bytes.fromhex(salt), iterations).hex()

    # ---- polymorphic behaviour -----------------------------------------
    @abstractmethod
    def view_dashboard(self, manager: BookingManager) -> list[Booking]:
        """Ongoing bookings this user should see on their dashboard."""

    @abstractmethod
    def view_history(self, manager: BookingManager) -> list[Booking]:
        """Past consultations for this user."""

    @abstractmethod
    def owns_booking(self, booking: Booking) -> bool:
        """Whether this user is a party to the booking."""

    @abstractmethod
    def booking_filter(self) -> dict[str, str]:
        """How to find this user's bookings in the data store."""

    # ---- persistence ---------------------------------------------------
    def to_record(self) -> dict:
        record = {
            "name": self._name,
            "email": self._email,
            "role": self.ROLE,
            "password_hash": self._password_hash,
        }
        if self._id:
            record["id"] = self._id
        return record

    @classmethod
    def from_record(cls, record: dict, course_ids: list[str] | None = None) -> User:
        user_cls = User._registry.get(record.get("role", ""))
        if user_cls is None:
            raise ValueError(f"Unknown role: {record.get('role')!r}")
        return user_cls._build(record, course_ids or [])

    @classmethod
    def _build(cls, record: dict, course_ids: list[str]) -> User:
        return cls(name=record["name"], email=record["email"], user_id=record.get("id"),
                   password_hash=record.get("password_hash"),
                   created_at=timeutil.parse(record.get("created_at")))

    def __repr__(self) -> str:
        return f"{type(self).__name__}(id={self._id!r}, email={self._email!r})"


class Teacher(User):
    ROLE = "teacher"

    def __init__(self, name: str, email: str, course_ids: list[str] | None = None, **kwargs):
        super().__init__(name, email, **kwargs)
        self._course_ids = list(dict.fromkeys(course_ids or []))

    @property
    def course_ids(self) -> tuple[str, ...]:
        return tuple(self._course_ids)

    def teaches(self, course_id: str) -> bool:
        return course_id in self._course_ids

    def view_dashboard(self, manager: BookingManager) -> list[Booking]:
        # A teacher's dashboard shows confirmed (upcoming / ongoing) consultations.
        return manager.bookings_for(teacher_id=self.id, statuses=[BookingStatus.CONFIRMED])

    def pending_requests(self, manager: BookingManager) -> list[Booking]:
        return manager.bookings_for(teacher_id=self.id, statuses=[BookingStatus.PENDING])

    def view_history(self, manager: BookingManager) -> list[Booking]:
        return manager.bookings_for(teacher_id=self.id, statuses=BookingStatus.closed(),
                                    newest_first=True)

    def owns_booking(self, booking: Booking) -> bool:
        return booking.teacher_id == self.id

    def booking_filter(self) -> dict[str, str]:
        return {"teacher_id": self.id}

    @classmethod
    def _build(cls, record: dict, course_ids: list[str]) -> Teacher:
        return cls(name=record["name"], email=record["email"], course_ids=course_ids,
                   user_id=record.get("id"), password_hash=record.get("password_hash"),
                   created_at=timeutil.parse(record.get("created_at")))


class Student(User):
    ROLE = "student"

    def view_dashboard(self, manager: BookingManager) -> list[Booking]:
        # A student's dashboard shows requests still waiting and confirmed ones.
        return manager.bookings_for(student_id=self.id, statuses=BookingStatus.active())

    def view_history(self, manager: BookingManager) -> list[Booking]:
        return manager.bookings_for(student_id=self.id, statuses=BookingStatus.closed(),
                                    newest_first=True)

    def owns_booking(self, booking: Booking) -> bool:
        return booking.student_id == self.id

    def booking_filter(self) -> dict[str, str]:
        return {"student_id": self.id}


# ---------------------------------------------------------------------------
# Courses
# ---------------------------------------------------------------------------

class Course:
    def __init__(self, code: str, title: str, course_id: str | None = None):
        code = (code or "").strip().upper()
        title = (title or "").strip()
        if not code or not title:
            raise ValidationError("A course needs both a code and a title.")
        if len(code) > 20:
            raise ValidationError("Course code must be 20 characters or fewer.")
        self._id = course_id
        self._code = code
        self._title = title

    @property
    def id(self) -> str | None:
        return self._id

    @property
    def code(self) -> str:
        return self._code

    @property
    def title(self) -> str:
        return self._title

    @property
    def label(self) -> str:
        return f"{self._code} – {self._title}"

    def to_record(self) -> dict:
        record = {"code": self._code, "title": self._title}
        if self._id:
            record["id"] = self._id
        return record

    @classmethod
    def from_record(cls, record: dict) -> Course:
        return cls(record["code"], record["title"], course_id=record.get("id"))

    def __repr__(self) -> str:
        return f"Course({self._code!r})"


# ---------------------------------------------------------------------------
# Schedule slots
# ---------------------------------------------------------------------------

class SlotStatus(str, Enum):
    OPEN = "open"
    BOOKED = "booked"
    REMOVED = "removed"


class ScheduleSlot:
    """A block of time a teacher has published for consultations."""

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

    # ---- state changes -------------------------------------------------
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

    # ---- persistence ---------------------------------------------------
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


# ---------------------------------------------------------------------------
# Bookings
# ---------------------------------------------------------------------------

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
    """A student's consultation request for one of a teacher's slots."""

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
        self._status = BookingStatus(status)   # private: changed only via methods
        self._meeting_link = meeting_link or None
        self._note = note or None
        self._created_at = created_at

    # ---- read-only properties ------------------------------------------
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

    @property
    def is_active(self) -> bool:
        return self._status in BookingStatus.active()

    # ---- state transitions (encapsulation) -----------------------------
    def _transition(self, allowed_from: list[BookingStatus], to: BookingStatus) -> None:
        if self._status not in allowed_from:
            raise ConflictError(
                f"This booking is already {self._status.value.lower()} and can't be changed to "
                f"{to.value.lower()}."
            )
        self._status = to

    def accept(self, meeting_link: str | None = None) -> None:
        link = self.validate_link(meeting_link)
        self._transition([BookingStatus.PENDING], BookingStatus.CONFIRMED)
        self._meeting_link = link
        self._note = None

    def decline(self, reason: str | None = None) -> None:
        self._transition([BookingStatus.PENDING], BookingStatus.DECLINED)
        self._note = (reason or "").strip() or None

    def cancel(self, reason: str | None = None) -> None:
        self._transition(BookingStatus.active(), BookingStatus.CANCELLED)
        self._note = (reason or "").strip() or None

    def complete(self) -> None:
        self._transition([BookingStatus.CONFIRMED], BookingStatus.COMPLETED)

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

    # ---- persistence ---------------------------------------------------
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
