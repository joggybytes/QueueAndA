from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable

from core import timeutil
from core.models import (Booking, BookingStatus, ConflictError, Course, QueueAError,
                         ScheduleSlot, SlotStatus, Teacher, User)


class DataStoreError(QueueAError):
    """The database could not complete a request."""


def deleted_user_record(user_id: str) -> dict:
    """Fields written over a deleted account (personal details removed)."""
    return {
        "name": User.DELETED_NAME,
        "email": f"deleted-{user_id}@deleted.invalid",  # frees the real email for reuse
        "password_hash": "!",                          # matches no password
        "deleted_at": timeutil.to_iso(timeutil.now()),
    }


class DataStore(ABC):
    # ---- users ---------------------------------------------------------
    @abstractmethod
    def get_user(self, user_id: str) -> User | None: ...

    @abstractmethod
    def get_user_by_email(self, email: str) -> User | None: ...

    @abstractmethod
    def get_users(self, user_ids: Iterable[str]) -> dict[str, User]: ...

    @abstractmethod
    def add_user(self, user: User, course_ids: list[str] | None = None) -> User: ...

    @abstractmethod
    def list_teachers(self) -> list[Teacher]: ...

    @abstractmethod
    def set_teacher_courses(self, teacher_id: str, course_ids: list[str]) -> None:
        """Replace the list of courses a teacher handles."""

    @abstractmethod
    def update_user(self, user: User) -> User:
        """Save a user's name, email and password hash."""

    @abstractmethod
    def delete_user(self, user: User) -> None:
        """Delete an account: wipe its name, email and password, remove its
        course links, and mark it deleted. Booking records are kept so the
        other person's history stays complete (shown as "Deleted user")."""

    # ---- courses -------------------------------------------------------
    @abstractmethod
    def list_courses(self) -> list[Course]: ...

    @abstractmethod
    def get_course_by_code(self, code: str) -> Course | None: ...

    @abstractmethod
    def add_course(self, course: Course) -> Course: ...

    @abstractmethod
    def update_course(self, course: Course) -> Course: ...

    # ---- schedule slots ------------------------------------------------
    @abstractmethod
    def add_slot(self, slot: ScheduleSlot) -> ScheduleSlot: ...

    @abstractmethod
    def get_slot(self, slot_id: str) -> ScheduleSlot | None: ...

    @abstractmethod
    def get_slots(self, slot_ids: Iterable[str]) -> dict[str, ScheduleSlot]: ...

    @abstractmethod
    def list_slots(self, teacher_id: str,
                   statuses: list[SlotStatus] | None = None) -> list[ScheduleSlot]: ...

    @abstractmethod
    def update_slot_status(self, slot: ScheduleSlot, expected: SlotStatus) -> bool:
        """Save ``slot.status`` only if the stored status is still ``expected``."""

    # ---- bookings ------------------------------------------------------
    @abstractmethod
    def add_booking(self, booking: Booking) -> Booking: ...

    @abstractmethod
    def get_booking(self, booking_id: str) -> Booking | None: ...

    @abstractmethod
    def list_bookings(self, *, student_id: str | None = None, teacher_id: str | None = None,
                      slot_id: str | None = None,
                      statuses: list[BookingStatus] | None = None) -> list[Booking]: ...

    @abstractmethod
    def update_booking(self, booking: Booking, expected: BookingStatus) -> bool:
        """Save the booking only if the stored status is still ``expected``.

        Returns False when someone else changed it first (e.g. the student
        cancelled while the teacher was accepting).
        """


class SupabaseDataStore(DataStore):
    """DataStore backed by a Supabase (PostgreSQL) project."""

    def __init__(self, client):
        self._db = client

    @classmethod
    def connect(cls, url: str, key: str) -> SupabaseDataStore:
        from supabase import create_client
        return cls(create_client(url, key))

    # ---- helpers -------------------------------------------------------
    def _table(self, name: str):
        return self._db.table(name)

    def _run(self, query) -> list[dict]:
        try:
            response = query.execute()
        except Exception as exc:  # postgrest.APIError, httpx errors, ...
            raise self._translate(exc) from exc
        return response.data or []

    @staticmethod
    def _translate(exc: Exception) -> QueueAError:
        code = str(getattr(exc, "code", "") or "")
        message = str(getattr(exc, "message", "") or exc)
        if code == "23505":
            return ConflictError("That was just taken or already exists. Please refresh and try again.")
        if code == "42501" or "row-level security" in message:
            return DataStoreError("Supabase refused access. In .streamlit/secrets.toml, use the "
                                  "secret (service_role) key, not the anon/publishable key.")
        if code in ("42703", "PGRST204") or "deleted_at" in message:
            return DataStoreError("Your Supabase database needs an update for this version of "
                                  "Queue&A. Run supabase/schema.sql again in the SQL Editor.")
        if code in ("42P01", "PGRST205") or "does not exist" in message or "Could not find the table" in message:
            return DataStoreError("The Queue&A tables were not found. Run supabase/schema.sql in "
                                  "the Supabase SQL Editor first.")
        return DataStoreError(f"Database error: {message}")

    def _course_ids_by_teacher(self, teacher_ids: list[str]) -> dict[str, list[str]]:
        if not teacher_ids:
            return {}
        rows = self._run(self._table("teacher_courses").select("teacher_id, course_id")
                         .in_("teacher_id", teacher_ids))
        result: dict[str, list[str]] = {tid: [] for tid in teacher_ids}
        for row in rows:
            result.setdefault(row["teacher_id"], []).append(row["course_id"])
        return result

    def _users_from_rows(self, rows: list[dict]) -> list[User]:
        teacher_ids = [r["id"] for r in rows if r["role"] == Teacher.ROLE]
        courses = self._course_ids_by_teacher(teacher_ids)
        return [User.from_record(r, courses.get(r["id"], [])) for r in rows]

    # ---- users ---------------------------------------------------------
    def get_user(self, user_id: str) -> User | None:
        rows = self._run(self._table("users").select("*").eq("id", user_id).limit(1))
        users = self._users_from_rows(rows)
        return users[0] if users else None

    def get_user_by_email(self, email: str) -> User | None:
        rows = self._run(self._table("users").select("*")
                         .eq("email", email.strip().lower()).limit(1))
        users = self._users_from_rows(rows)
        return users[0] if users else None

    def get_users(self, user_ids: Iterable[str]) -> dict[str, User]:
        ids = sorted(set(user_ids))
        if not ids:
            return {}
        rows = self._run(self._table("users").select("*").in_("id", ids))
        return {u.id: u for u in self._users_from_rows(rows)}

    def add_user(self, user: User, course_ids: list[str] | None = None) -> User:
        rows = self._run(self._table("users").insert(user.to_record()))
        record = rows[0]
        course_ids = list(dict.fromkeys(course_ids or []))
        if course_ids:
            links = [{"teacher_id": record["id"], "course_id": cid} for cid in course_ids]
            try:
                self._run(self._table("teacher_courses").insert(links))
            except QueueAError:
                # Undo the half-created account so the email can be reused.
                self._run(self._table("users").delete().eq("id", record["id"]))
                raise
        return User.from_record(record, course_ids)

    def list_teachers(self) -> list[Teacher]:
        rows = self._run(self._table("users").select("*").eq("role", Teacher.ROLE)
                         .is_("deleted_at", "null").order("name"))
        return [u for u in self._users_from_rows(rows) if isinstance(u, Teacher)]

    def set_teacher_courses(self, teacher_id: str, course_ids: list[str]) -> None:
        wanted = list(dict.fromkeys(course_ids))
        current = set(self._course_ids_by_teacher([teacher_id]).get(teacher_id, []))
        to_add = [cid for cid in wanted if cid not in current]
        to_remove = [cid for cid in current if cid not in set(wanted)]
        if to_add:
            rows = [{"teacher_id": teacher_id, "course_id": cid} for cid in to_add]
            self._run(self._table("teacher_courses")
                      .upsert(rows, on_conflict="teacher_id,course_id", ignore_duplicates=True))
        if to_remove:
            self._run(self._table("teacher_courses").delete()
                      .eq("teacher_id", teacher_id).in_("course_id", to_remove))

    def update_user(self, user: User) -> User:
        record = user.to_record()
        fields = {k: record[k] for k in ("name", "email", "password_hash")}
        rows = self._run(self._table("users").update(fields)
                         .eq("id", user.id).is_("deleted_at", "null"))
        if not rows:
            raise ConflictError("This account no longer exists.")
        return self.get_user(user.id)

    def delete_user(self, user: User) -> None:
        self._run(self._table("teacher_courses").delete().eq("teacher_id", user.id))
        self._run(self._table("users").update(deleted_user_record(user.id)).eq("id", user.id))

    # ---- courses -------------------------------------------------------
    def list_courses(self) -> list[Course]:
        rows = self._run(self._table("courses").select("*").order("code"))
        return [Course.from_record(r) for r in rows]

    def get_course_by_code(self, code: str) -> Course | None:
        rows = self._run(self._table("courses").select("*")
                         .eq("code", code.strip().upper()).limit(1))
        return Course.from_record(rows[0]) if rows else None

    def add_course(self, course: Course) -> Course:
        rows = self._run(self._table("courses").insert(course.to_record()))
        return Course.from_record(rows[0])

    def update_course(self, course: Course) -> Course:
        rows = self._run(self._table("courses")
                         .update({"code": course.code, "title": course.title})
                         .eq("id", course.id))
        if not rows:
            raise ConflictError("That course no longer exists. Refresh and try again.")
        return Course.from_record(rows[0])

    # ---- schedule slots ------------------------------------------------
    def add_slot(self, slot: ScheduleSlot) -> ScheduleSlot:
        rows = self._run(self._table("schedule_slots").insert(slot.to_record()))
        return ScheduleSlot.from_record(rows[0])

    def get_slot(self, slot_id: str) -> ScheduleSlot | None:
        rows = self._run(self._table("schedule_slots").select("*").eq("id", slot_id).limit(1))
        return ScheduleSlot.from_record(rows[0]) if rows else None

    def get_slots(self, slot_ids: Iterable[str]) -> dict[str, ScheduleSlot]:
        ids = sorted(set(slot_ids))
        if not ids:
            return {}
        rows = self._run(self._table("schedule_slots").select("*").in_("id", ids))
        return {r["id"]: ScheduleSlot.from_record(r) for r in rows}

    def list_slots(self, teacher_id: str,
                   statuses: list[SlotStatus] | None = None) -> list[ScheduleSlot]:
        query = self._table("schedule_slots").select("*").eq("teacher_id", teacher_id)
        if statuses:
            query = query.in_("status", [s.value for s in statuses])
        rows = self._run(query.order("start_time"))
        return [ScheduleSlot.from_record(r) for r in rows]

    def update_slot_status(self, slot: ScheduleSlot, expected: SlotStatus) -> bool:
        rows = self._run(self._table("schedule_slots")
                         .update({"status": slot.status.value})
                         .eq("id", slot.id).eq("status", expected.value))
        return bool(rows)

    # ---- bookings ------------------------------------------------------
    def add_booking(self, booking: Booking) -> Booking:
        rows = self._run(self._table("bookings").insert(booking.to_record()))
        return Booking.from_record(rows[0])

    def get_booking(self, booking_id: str) -> Booking | None:
        rows = self._run(self._table("bookings").select("*").eq("id", booking_id).limit(1))
        return Booking.from_record(rows[0]) if rows else None

    def list_bookings(self, *, student_id=None, teacher_id=None, slot_id=None,
                      statuses=None) -> list[Booking]:
        query = self._table("bookings").select("*")
        if student_id:
            query = query.eq("student_id", student_id)
        if teacher_id:
            query = query.eq("teacher_id", teacher_id)
        if slot_id:
            query = query.eq("slot_id", slot_id)
        if statuses:
            query = query.in_("status", [s.value for s in statuses])
        rows = self._run(query.order("created_at"))
        return [Booking.from_record(r) for r in rows]

    def update_booking(self, booking: Booking, expected: BookingStatus) -> bool:
        record = booking.to_record()
        for key in ("id", "student_id", "teacher_id", "slot_id", "course_id", "purpose"):
            record.pop(key, None)
        record["updated_at"] = timeutil.to_iso(timeutil.now())
        rows = self._run(self._table("bookings").update(record)
                         .eq("id", booking.id).eq("status", expected.value))
        return bool(rows)
