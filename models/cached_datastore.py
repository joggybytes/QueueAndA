from __future__ import annotations

import copy
import threading
import time
from typing import Any, Callable, Iterable

from models.booking import Booking, BookingStatus
from models.course import Course
from models.datastore import DataStore
from models.schedule_slot import ScheduleSlot, SlotStatus
from models.user import Teacher, User

# slots that arent removed
_LIVE = (SlotStatus.OPEN, SlotStatus.BOOKED)


class SharedCache:
    """small cache shared by everyone"""

    def __init__(self, ttl: float = 30.0, clock: Callable[[], float] = time.monotonic):
        self._ttl = ttl
        self._clock = clock
        self._lock = threading.Lock()
        self._items: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        with self._lock:
            item = self._items.get(key)
            if item is None or item[0] < self._clock():
                self._items.pop(key, None)
                return None
            return item[1]

    def put(self, key: str, value: Any) -> None:
        if self._ttl <= 0:          # sharing off
            return
        with self._lock:
            self._items[key] = (self._clock() + self._ttl, value)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


class CachingDataStore(DataStore):
    """remembers reads during one page load so we dont ask twice"""

    def __init__(self, inner: DataStore, shared: SharedCache | None = None):
        self._inner = inner
        self._shared = shared or SharedCache(ttl=0)
        self._reset()

    # cache
    def _reset(self) -> None:
        self._users: dict[str, User | None] = {}
        self._slots: dict[str, ScheduleSlot | None] = {}
        self._live_slots: dict[str, list[ScheduleSlot]] = {}       # open and booked slots per teacher
        self._bookings_of: dict[tuple[str, str], list[Booking]] = {}  # bookings per person
        self._memo: dict[tuple, Any] = {}

    def _changed(self, shared_too: bool = False) -> None:
        self._reset()
        if shared_too:
            self._shared.clear()

    @staticmethod
    def _copy(value):
        return copy.deepcopy(value)

    def _remember(self, key: tuple, load: Callable[[], Any]):
        if key not in self._memo:
            self._memo[key] = load()
        return self._copy(self._memo[key])

    def _shared_read(self, key: str, load: Callable[[], Any]):
        value = self._shared.get(key)
        if value is None:
            value = load()
            self._shared.put(key, value)
        return self._copy(value)

    # users
    def get_user(self, user_id: str) -> User | None:
        if user_id not in self._users:
            self._users[user_id] = self._inner.get_user(user_id)
        return self._copy(self._users[user_id])

    def get_user_by_email(self, email: str) -> User | None:
        return self._remember(("user_by_email", email.strip().lower()),
                              lambda: self._inner.get_user_by_email(email))

    def get_users(self, user_ids: Iterable[str]) -> dict[str, User]:
        ids = set(user_ids)
        missing = [uid for uid in ids if uid not in self._users]
        if missing:
            found = self._inner.get_users(missing)
            for uid in missing:
                self._users[uid] = found.get(uid)
        return {uid: self._copy(self._users[uid]) for uid in ids if self._users.get(uid) is not None}

    def add_user(self, user: User, course_ids: list[str] | None = None) -> User:
        try:
            return self._inner.add_user(user, course_ids)
        finally:
            self._changed(shared_too=True)

    def list_teachers(self) -> list[Teacher]:
        return self._shared_read("teachers", self._inner.list_teachers)

    def set_teacher_courses(self, teacher_id: str, course_ids: list[str]) -> None:
        try:
            self._inner.set_teacher_courses(teacher_id, course_ids)
        finally:
            self._changed(shared_too=True)

    def update_user(self, user: User) -> User:
        try:
            return self._inner.update_user(user)
        finally:
            self._changed(shared_too=True)

    def delete_user(self, user: User) -> None:
        try:
            self._inner.delete_user(user)
        finally:
            self._changed(shared_too=True)

    # courses
    def list_courses(self) -> list[Course]:
        return self._shared_read("courses", self._inner.list_courses)

    def get_course_by_code(self, code: str) -> Course | None:
        return self._remember(("course_by_code", code.strip().upper()),
                              lambda: self._inner.get_course_by_code(code))

    def add_course(self, course: Course) -> Course:
        try:
            return self._inner.add_course(course)
        finally:
            self._changed(shared_too=True)

    def update_course(self, course: Course) -> Course:
        try:
            return self._inner.update_course(course)
        finally:
            self._changed(shared_too=True)

    # slots
    def _note_slots(self, slots: list[ScheduleSlot]) -> None:
        for slot in slots:
            self._slots[slot.id] = slot

    def add_slot(self, slot: ScheduleSlot) -> ScheduleSlot:
        try:
            return self._inner.add_slot(slot)
        finally:
            self._changed()

    def get_slot(self, slot_id: str) -> ScheduleSlot | None:
        if slot_id not in self._slots:
            self._slots[slot_id] = self._inner.get_slot(slot_id)
        return self._copy(self._slots[slot_id])

    def get_slots(self, slot_ids: Iterable[str]) -> dict[str, ScheduleSlot]:
        ids = set(slot_ids)
        missing = [sid for sid in ids if sid not in self._slots]
        if missing:
            found = self._inner.get_slots(missing)
            for sid in missing:
                self._slots[sid] = found.get(sid)
        return {sid: self._copy(self._slots[sid]) for sid in ids if self._slots.get(sid) is not None}

    @staticmethod
    def _wants_live_only(statuses: list[SlotStatus] | None) -> bool:
        return bool(statuses) and all(s in _LIVE for s in statuses)

    def list_slots(self, teacher_id: str,
                   statuses: list[SlotStatus] | None = None) -> list[ScheduleSlot]:
        if not self._wants_live_only(statuses):
            key = ("slots", teacher_id, tuple(s.value for s in statuses or ()))
            return self._remember(key, lambda: self._inner.list_slots(teacher_id, statuses))
        if teacher_id not in self._live_slots:
            live = self._inner.list_slots(teacher_id, list(_LIVE))
            self._live_slots[teacher_id] = live
            self._note_slots(live)
        wanted = set(statuses)
        return [self._copy(s) for s in self._live_slots[teacher_id] if s.status in wanted]

    def list_slots_for_teachers(self, teacher_ids: Iterable[str],
                                statuses: list[SlotStatus] | None = None) -> list[ScheduleSlot]:
        ids = list(dict.fromkeys(teacher_ids))
        if not self._wants_live_only(statuses):
            key = ("slots_for", tuple(sorted(ids)), tuple(s.value for s in statuses or ()))
            return self._remember(key, lambda: self._inner.list_slots_for_teachers(ids, statuses))
        missing = [tid for tid in ids if tid not in self._live_slots]
        if missing:
            live = self._inner.list_slots_for_teachers(missing, list(_LIVE))
            for tid in missing:
                self._live_slots[tid] = [s for s in live if s.teacher_id == tid]
            self._note_slots(live)
        wanted = set(statuses)
        merged = [s for tid in ids for s in self._live_slots[tid] if s.status in wanted]
        return [self._copy(s) for s in sorted(merged, key=lambda s: s.start)]

    def update_slot_status(self, slot: ScheduleSlot, expected: SlotStatus) -> bool:
        try:
            return self._inner.update_slot_status(slot, expected)
        finally:
            self._changed()

    # bookings
    def add_booking(self, booking: Booking) -> Booking:
        try:
            return self._inner.add_booking(booking)
        finally:
            self._changed()

    def get_booking(self, booking_id: str) -> Booking | None:
        return self._remember(("booking", booking_id), lambda: self._inner.get_booking(booking_id))

    def list_bookings(self, *, student_id: str | None = None, teacher_id: str | None = None,
                      slot_id: str | None = None,
                      statuses: list[BookingStatus] | None = None) -> list[Booking]:
        owner = [(f, v) for f, v in (("student_id", student_id), ("teacher_id", teacher_id)) if v]
        if len(owner) == 1 and slot_id is None:
            # get all bookings once then filter
            key = owner[0]
            if key not in self._bookings_of:
                self._bookings_of[key] = self._inner.list_bookings(**{key[0]: key[1]})
            wanted = set(statuses) if statuses else None
            return [self._copy(b) for b in self._bookings_of[key]
                    if wanted is None or b.status in wanted]
        key = ("bookings", student_id, teacher_id, slot_id,
               tuple(s.value for s in statuses) if statuses else None)
        return self._remember(key, lambda: self._inner.list_bookings(
            student_id=student_id, teacher_id=teacher_id, slot_id=slot_id, statuses=statuses))

    def update_booking(self, booking: Booking, expected: BookingStatus) -> bool:
        try:
            return self._inner.update_booking(booking, expected)
        finally:
            self._changed()
