from __future__ import annotations

import hashlib
import hmac
import secrets
from abc import ABC, abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING, ClassVar

from models.booking import Booking, BookingStatus
from models.errors import ValidationError
from utils import timeutil

if TYPE_CHECKING:  # avoids circular import
    from controllers.booking_controller import BookingManager


# users

class User(ABC):
    """base class for teachers and students"""

    ROLE: ClassVar[str] = ""
    _registry: ClassVar[dict[str, type[User]]] = {}

    _HASH_NAME = "sha256"
    _ITERATIONS = 200_000

    DELETED_NAME = "Deleted user"

    def __init__(self, name: str, email: str, user_id: str | None = None,
                 password_hash: str | None = None, created_at: datetime | None = None,
                 deleted_at: datetime | None = None):
        self._id = user_id
        self._name = self._clean_name(name)
        self._email = self._clean_email(email)
        self._password_hash = password_hash  # private
        self._created_at = created_at
        self._deleted_at = deleted_at

    NAME_MAX = 100

    @classmethod
    def _clean_name(cls, name: str) -> str:
        name = " ".join((name or "").split())
        if not name:
            raise ValidationError("Name is required.")
        if len(name) > cls.NAME_MAX:
            raise ValidationError(f"Name must be {cls.NAME_MAX} characters or fewer.")
        return name

    @staticmethod
    def _clean_email(email: str) -> str:
        email = (email or "").strip().lower()
        if not email:
            raise ValidationError("Email is required.")
        return email

    def update_details(self, name: str, email: str) -> None:
        """change name or email"""
        new_name, new_email = self._clean_name(name), self._clean_email(email)
        self._name, self._email = new_name, new_email

    # subclasses get saved here so we know wich class to make
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.ROLE:
            User._registry[cls.ROLE] = cls

    # properties
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
    def created_at(self) -> datetime | None:
        return self._created_at

    @property
    def is_deleted(self) -> bool:
        return self._deleted_at is not None

    @property
    def role_label(self) -> str:
        return self.ROLE.capitalize()

    def __eq__(self, other: object) -> bool:
        return isinstance(other, User) and self._id is not None and self._id == other._id

    def __hash__(self) -> int:
        return hash(self._id)

    # password
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

    # each role does these differently
    @abstractmethod
    def view_dashboard(self, manager: BookingManager) -> list[Booking]:
        """bookings on the dashboard"""

    @abstractmethod
    def view_history(self, manager: BookingManager) -> list[Booking]:
        """past consultations"""

    @abstractmethod
    def owns_booking(self, booking: Booking) -> bool:
        """is this thier booking"""

    @abstractmethod
    def booking_filter(self) -> dict[str, str]:
        """how to find thier bookings"""

    # saving
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
                   created_at=timeutil.parse(record.get("created_at")),
                   deleted_at=timeutil.parse(record.get("deleted_at")))

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
        # teacher dashboard shows confirmed ones
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
                   created_at=timeutil.parse(record.get("created_at")),
                   deleted_at=timeutil.parse(record.get("deleted_at")))


class Student(User):
    ROLE = "student"

    def view_dashboard(self, manager: BookingManager) -> list[Booking]:
        # student dashboard shows pending and confirmed
        return manager.bookings_for(student_id=self.id, statuses=BookingStatus.active())

    def view_history(self, manager: BookingManager) -> list[Booking]:
        return manager.bookings_for(student_id=self.id, statuses=BookingStatus.closed(),
                                    newest_first=True)

    def owns_booking(self, booking: Booking) -> bool:
        return booking.student_id == self.id

    def booking_filter(self) -> dict[str, str]:
        return {"student_id": self.id}
