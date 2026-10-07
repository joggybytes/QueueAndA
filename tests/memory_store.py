"""In-memory DataStore used by the tests (same interface as SupabaseDataStore)."""

from __future__ import annotations

import copy
import uuid
from typing import Iterable

from core import timeutil
from core.datastore import DataStore
from core.models import (Booking, BookingStatus, ConflictError, Course, ScheduleSlot,
                         SlotStatus, Teacher, User)


class InMemoryDataStore(DataStore):
    def __init__(self):
        self.users: dict[str, dict] = {}
        self.teacher_courses: dict[str, list[str]] = {}
        self.courses: dict[str, dict] = {}
        self.slots: dict[str, dict] = {}
        self.bookings: dict[str, dict] = {}

    @staticmethod
    def _new_id() -> str:
        return str(uuid.uuid4())

    def _user(self, rec: dict) -> User:
        return User.from_record(copy.deepcopy(rec), list(self.teacher_courses.get(rec["id"], [])))

    # ---- users ---------------------------------------------------------
    def get_user(self, user_id):
        rec = self.users.get(user_id)
        return self._user(rec) if rec else None

    def get_user_by_email(self, email):
        email = email.strip().lower()
        for rec in self.users.values():
            if rec["email"] == email:
                return self._user(rec)
        return None

    def get_users(self, user_ids: Iterable[str]):
        return {uid: self._user(self.users[uid]) for uid in set(user_ids) if uid in self.users}

    def add_user(self, user, course_ids=None):
        if self.get_user_by_email(user.email):
            raise ConflictError("duplicate email")
        rec = user.to_record()
        rec["id"] = self._new_id()
        rec["created_at"] = timeutil.to_iso(timeutil.now())
        self.users[rec["id"]] = rec
        self.teacher_courses[rec["id"]] = list(dict.fromkeys(course_ids or []))
        return self._user(rec)

    def list_teachers(self):
        teachers = [self._user(r) for r in self.users.values() if r["role"] == Teacher.ROLE]
        return sorted(teachers, key=lambda t: t.name)

    # ---- courses -------------------------------------------------------
    def list_courses(self):
        return sorted((Course.from_record(r) for r in self.courses.values()), key=lambda c: c.code)

    def get_course_by_code(self, code):
        code = code.strip().upper()
        for rec in self.courses.values():
            if rec["code"] == code:
                return Course.from_record(rec)
        return None

    def add_course(self, course):
        if self.get_course_by_code(course.code):
            raise ConflictError("duplicate course")
        rec = course.to_record()
        rec["id"] = self._new_id()
        self.courses[rec["id"]] = rec
        return Course.from_record(rec)

    # ---- slots ---------------------------------------------------------
    def add_slot(self, slot):
        rec = slot.to_record()
        rec["id"] = self._new_id()
        self.slots[rec["id"]] = rec
        return ScheduleSlot.from_record(rec)

    def get_slot(self, slot_id):
        rec = self.slots.get(slot_id)
        return ScheduleSlot.from_record(rec) if rec else None

    def get_slots(self, slot_ids):
        return {sid: ScheduleSlot.from_record(self.slots[sid]) for sid in set(slot_ids)
                if sid in self.slots}

    def list_slots(self, teacher_id, statuses=None):
        wanted = {s.value for s in statuses} if statuses else None
        rows = [r for r in self.slots.values() if r["teacher_id"] == teacher_id
                and (wanted is None or r["status"] in wanted)]
        slots = [ScheduleSlot.from_record(r) for r in rows]
        return sorted(slots, key=lambda s: s.start)

    def update_slot_status(self, slot, expected):
        rec = self.slots.get(slot.id)
        if rec is None or rec["status"] != expected.value:
            return False
        rec["status"] = slot.status.value
        return True

    # ---- bookings ------------------------------------------------------
    def add_booking(self, booking):
        rec = booking.to_record()
        if rec["status"] == "Confirmed" and any(
                b["slot_id"] == rec["slot_id"] and b["status"] == "Confirmed"
                for b in self.bookings.values()):
            raise ConflictError("slot already confirmed")
        rec["id"] = self._new_id()
        rec["created_at"] = timeutil.to_iso(timeutil.now())
        self._seq = getattr(self, "_seq", 0) + 1
        rec["_seq"] = self._seq
        self.bookings[rec["id"]] = rec
        return Booking.from_record(rec)

    def get_booking(self, booking_id):
        rec = self.bookings.get(booking_id)
        return Booking.from_record(rec) if rec else None

    def list_bookings(self, *, student_id=None, teacher_id=None, slot_id=None, statuses=None):
        wanted = {s.value for s in statuses} if statuses else None
        rows = [r for r in self.bookings.values()
                if (student_id is None or r["student_id"] == student_id)
                and (teacher_id is None or r["teacher_id"] == teacher_id)
                and (slot_id is None or r["slot_id"] == slot_id)
                and (wanted is None or r["status"] in wanted)]
        rows.sort(key=lambda r: r["_seq"])
        return [Booking.from_record(r) for r in rows]

    def update_booking(self, booking, expected: BookingStatus):
        rec = self.bookings.get(booking.id)
        if rec is None or rec["status"] != expected.value:
            return False
        new = booking.to_record()
        if new["status"] == "Confirmed" and any(
                b["slot_id"] == rec["slot_id"] and b["status"] == "Confirmed" and b["id"] != rec["id"]
                for b in self.bookings.values()):
            raise ConflictError("slot already confirmed")
        rec.update(status=new["status"], meeting_link=new["meeting_link"], note=new["note"])
        return True
