from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable

from models.booking import Booking, BookingStatus
from models.course import Course
from models.errors import ConflictError
from models.schedule_slot import ScheduleSlot, SlotStatus
from models.user import Teacher, User
from utils import timeutil


def deleted_user_record(user_id: str) -> dict:
    """what a deleted account gets replaced with"""
    return {
        "name": User.DELETED_NAME,
        "email": f"deleted-{user_id}@deleted.invalid",  # so the email can be used again
        "password_hash": "!",                          # no password
        "deleted_at": timeutil.to_iso(timeutil.now()),
    }


class DataStore(ABC):
    # users
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
        """sets a teachers courses"""

    @abstractmethod
    def update_user(self, user: User) -> User:
        """saves name, email and password"""

    @abstractmethod
    def delete_user(self, user: User) -> None:
        """deletes an account but keeps the bookings"""

    # courses
    @abstractmethod
    def list_courses(self) -> list[Course]: ...

    @abstractmethod
    def get_course_by_code(self, code: str) -> Course | None: ...

    @abstractmethod
    def add_course(self, course: Course) -> Course: ...

    @abstractmethod
    def update_course(self, course: Course) -> Course: ...

    # slots
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
    def list_slots_for_teachers(self, teacher_ids: Iterable[str],
                                statuses: list[SlotStatus] | None = None) -> list[ScheduleSlot]:
        """slots for many teachers"""

    @abstractmethod
    def update_slot_status(self, slot: ScheduleSlot, expected: SlotStatus) -> bool:
        """saves only if the status didnt change"""

    # bookings
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
        """saves only if nobody changed it first"""


class SupabaseDataStore(DataStore):
    """saves to supabase"""

    def __init__(self, client):
        self._db = client

    @classmethod
    def connect(cls, url: str, key: str) -> SupabaseDataStore:
        from supabase import create_client
        return cls(create_client(url, key))

    # helpers
    def _table(self, name: str):
        return self._db.table(name)

    def _run(self, query) -> list[dict]:
        return query.execute().data or []

    # users and courses in one request, falls back to two if it dosent work
    _USER_COLUMNS = "*, teacher_courses(course_id)"
    _embed_courses = True

    def _fetch_users(self, add_filters) -> list[User]:
        """gets users"""
        if SupabaseDataStore._embed_courses:
            try:
                response = add_filters(self._table("users").select(self._USER_COLUMNS)).execute()
            except Exception as exc:
                if str(getattr(exc, "code", "") or "") != "PGRST200":  # pgrst200 = cant join the tables
                    raise
                SupabaseDataStore._embed_courses = False
            else:
                return [User.from_record(r, [link["course_id"] for link in (r.get("teacher_courses") or [])])
                        for r in (response.data or [])]
        return self._users_from_rows(self._run(add_filters(self._table("users").select("*"))))

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

    # users
    def get_user(self, user_id: str) -> User | None:
        users = self._fetch_users(lambda q: q.eq("id", user_id).limit(1))
        return users[0] if users else None

    def get_user_by_email(self, email: str) -> User | None:
        users = self._fetch_users(lambda q: q.eq("email", email.strip().lower()).limit(1))
        return users[0] if users else None

    def get_users(self, user_ids: Iterable[str]) -> dict[str, User]:
        ids = sorted(set(user_ids))
        if not ids:
            return {}
        return {u.id: u for u in self._fetch_users(lambda q: q.in_("id", ids))}

    def add_user(self, user: User, course_ids: list[str] | None = None) -> User:
        rows = self._run(self._table("users").insert(user.to_record()))
        record = rows[0]
        course_ids = list(dict.fromkeys(course_ids or []))
        if course_ids:
            links = [{"teacher_id": record["id"], "course_id": cid} for cid in course_ids]
            try:
                self._run(self._table("teacher_courses").insert(links))
            except Exception:
                # undo it so the email can be used again
                self._run(self._table("users").delete().eq("id", record["id"]))
                raise
        return User.from_record(record, course_ids)

    def list_teachers(self) -> list[Teacher]:
        users = self._fetch_users(lambda q: q.eq("role", Teacher.ROLE)
                                  .is_("deleted_at", "null").order("name"))
        return [u for u in users if isinstance(u, Teacher)]

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

    # courses
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

    # slots
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

    def list_slots_for_teachers(self, teacher_ids: Iterable[str],
                                statuses: list[SlotStatus] | None = None) -> list[ScheduleSlot]:
        ids = sorted(set(teacher_ids))
        if not ids:
            return []
        query = self._table("schedule_slots").select("*").in_("teacher_id", ids)
        if statuses:
            query = query.in_("status", [s.value for s in statuses])
        rows = self._run(query.order("start_time"))
        return [ScheduleSlot.from_record(r) for r in rows]

    def update_slot_status(self, slot: ScheduleSlot, expected: SlotStatus) -> bool:
        rows = self._run(self._table("schedule_slots")
                         .update({"status": slot.status.value})
                         .eq("id", slot.id).eq("status", expected.value))
        return bool(rows)

    # bookings
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
