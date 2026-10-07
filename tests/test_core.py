"""Tests for Queue&A's business rules. Run with:  python -m unittest discover tests"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from core import timeutil
from core.auth import AuthManager
from core.manager import BookingManager
from core.models import (AuthError, Booking, BookingStatus, ConflictError, Course,
                         PermissionDenied, ScheduleSlot, Student, Teacher, User,
                         ValidationError)
from tests.memory_store import InMemoryDataStore


class Clock:
    def __init__(self, start: datetime):
        self.value = start

    def __call__(self) -> datetime:
        return self.value


class QueueATestCase(unittest.TestCase):
    def setUp(self):
        timeutil.configure("Asia/Manila")
        self.store = InMemoryDataStore()
        self.cs = self.store.add_course(Course("CS202", "Object-Oriented Programming"))
        self.math = self.store.add_course(Course("MATH101", "Calculus 1"))
        self.auth = AuthManager(self.store)
        self.clock = Clock(datetime(2026, 10, 8, 8, 0, tzinfo=timeutil.tz()))
        self.mgr = BookingManager(self.store, clock=self.clock)

        self.teacher = self.auth.register(name="Prof. Santos", email="Santos@School.edu",
                                          password="teacherpass", confirm_password="teacherpass",
                                          role="teacher", course_ids=[self.cs.id])
        self.alice = self.auth.register(name="Alice", email="alice@school.edu",
                                        password="alicepass1", confirm_password="alicepass1",
                                        role="student")
        self.bob = self.auth.register(name="Bob", email="bob@school.edu",
                                      password="bobpass12", confirm_password="bobpass12",
                                      role="student")

    def at(self, day: int, hour: int, minute: int = 0) -> datetime:
        return datetime(2026, 10, day, hour, minute, tzinfo=timeutil.tz())

    def publish(self, day=9, hour=10, minutes=30) -> ScheduleSlot:
        start = self.at(day, hour)
        return self.mgr.publish_slot(self.teacher, start, start + timedelta(minutes=minutes))

    def book(self, student, slot, purpose="Help with inheritance"):
        return self.mgr.request_booking(student, slot.id, self.cs.id, purpose)


class TestAuth(QueueATestCase):
    def test_register_returns_right_subclass(self):
        self.assertIsInstance(self.teacher, Teacher)
        self.assertIsInstance(self.alice, Student)
        self.assertEqual(self.teacher.email, "santos@school.edu")
        self.assertEqual(self.teacher.course_ids, (self.cs.id,))

    def test_login_success_and_case_insensitive_email(self):
        user = self.auth.login("ALICE@school.edu ", "alicepass1")
        self.assertEqual(user.id, self.alice.id)
        self.assertIsInstance(user, Student)

    def test_login_wrong_password_and_unknown_email_same_message(self):
        with self.assertRaises(AuthError) as wrong:
            self.auth.login("alice@school.edu", "nope-nope")
        with self.assertRaises(AuthError) as unknown:
            self.auth.login("ghost@school.edu", "whatever1")
        self.assertEqual(str(wrong.exception), str(unknown.exception))

    def test_password_is_hashed_not_stored(self):
        rec = self.store.users[self.alice.id]
        self.assertNotIn("alicepass1", rec["password_hash"])
        self.assertTrue(rec["password_hash"].startswith("pbkdf2_sha256$"))

    def test_registration_rules(self):
        base = dict(name="X", email="x@school.edu", password="password1",
                    confirm_password="password1", role="student")
        with self.assertRaises(AuthError):
            self.auth.register(**{**base, "email": "alice@school.edu"})
        with self.assertRaises(ValidationError):
            self.auth.register(**{**base, "confirm_password": "different1"})
        with self.assertRaises(ValidationError):
            self.auth.register(**{**base, "password": "short", "confirm_password": "short"})
        with self.assertRaises(ValidationError):
            self.auth.register(**{**base, "email": "not-an-email"})
        with self.assertRaises(ValidationError):
            self.auth.register(**{**base, "role": "teacher"})  # teacher without courses
        with self.assertRaises(ValidationError):
            self.auth.register(**{**base, "role": "admin"})

    def test_teacher_can_add_new_course_at_signup(self):
        t = self.auth.register(name="Prof. Cruz", email="cruz@school.edu", password="password1",
                               confirm_password="password1", role="teacher",
                               new_course_code="it305", new_course_title="Web Development")
        course = self.store.get_course_by_code("IT305")
        self.assertIsNotNone(course)
        self.assertTrue(t.teaches(course.id))
        # Reusing an existing code links to the existing course instead of duplicating it.
        t2 = self.auth.register(name="Prof. Lim", email="lim@school.edu", password="password1",
                                confirm_password="password1", role="teacher",
                                new_course_code="IT305", new_course_title="Anything")
        self.assertTrue(t2.teaches(course.id))
        self.assertEqual(len([c for c in self.store.list_courses() if c.code == "IT305"]), 1)

    def test_from_record_dispatches_by_role(self):
        user = User.from_record({"id": "1", "name": "N", "email": "n@x.io", "role": "teacher"}, ["c"])
        self.assertIsInstance(user, Teacher)
        with self.assertRaises(TypeError):
            User("N", "n@x.io")  # abstract class cannot be instantiated


class TestSlots(QueueATestCase):
    def test_publish_and_list(self):
        slot = self.publish()
        self.assertTrue(slot.is_open)
        self.assertEqual([s.id for s in self.mgr.open_slots(self.teacher.id)], [slot.id])

    def test_publish_rules(self):
        with self.assertRaises(ValidationError):  # past
            self.mgr.publish_slot(self.teacher, self.at(7, 10), self.at(7, 11))
        with self.assertRaises(ValidationError):  # end before start
            self.mgr.publish_slot(self.teacher, self.at(9, 11), self.at(9, 10))
        with self.assertRaises(ValidationError):  # too short
            self.mgr.publish_slot(self.teacher, self.at(9, 11), self.at(9, 11, 5))
        with self.assertRaises(ValidationError):  # too long
            self.mgr.publish_slot(self.teacher, self.at(9, 8), self.at(9, 13))
        with self.assertRaises(PermissionDenied):  # students can't publish
            self.mgr.publish_slot(self.alice, self.at(9, 10), self.at(9, 11))

    def test_overlap_rejected_but_adjacent_allowed(self):
        self.publish(hour=10, minutes=60)
        with self.assertRaises(ValidationError):
            self.mgr.publish_slot(self.teacher, self.at(9, 10, 30), self.at(9, 11, 30))
        self.mgr.publish_slot(self.teacher, self.at(9, 11), self.at(9, 11, 30))  # touches, OK

    def test_remove_slot_declines_pending(self):
        slot = self.publish()
        b = self.book(self.alice, slot)
        self.mgr.remove_slot(self.teacher, slot.id)
        self.assertEqual(self.store.get_booking(b.id).status, BookingStatus.DECLINED)
        self.assertEqual(self.mgr.open_slots(self.teacher.id), [])
        self.assertEqual(self.mgr.teacher_slots(self.teacher), [])

    def test_cannot_remove_booked_slot_or_someone_elses(self):
        slot = self.publish()
        b = self.book(self.alice, slot)
        self.mgr.accept_booking(self.teacher, b.id, "meet.google.com/abc-defg-hij")
        with self.assertRaises(ValidationError):
            self.mgr.remove_slot(self.teacher, slot.id)
        other = self.auth.register(name="Other", email="o@school.edu", password="password1",
                                   confirm_password="password1", role="teacher",
                                   course_ids=[self.math.id])
        with self.assertRaises(PermissionDenied):
            self.mgr.remove_slot(other, slot.id)


class TestBookingFlow(QueueATestCase):
    def test_full_happy_path(self):
        slot = self.publish()
        booking = self.book(self.alice, slot)
        self.assertEqual(booking.status, BookingStatus.PENDING)

        # Student dashboard shows it; teacher sees it as a pending request.
        self.assertEqual([b.id for b in self.alice.view_dashboard(self.mgr)], [booking.id])
        self.assertEqual([b.id for b in self.teacher.pending_requests(self.mgr)], [booking.id])
        self.assertEqual(self.teacher.view_dashboard(self.mgr), [])

        accepted = self.mgr.accept_booking(self.teacher, booking.id, "zoom.us/j/123456")
        self.assertEqual(accepted.status, BookingStatus.CONFIRMED)
        self.assertEqual(accepted.meeting_link, "https://zoom.us/j/123456")
        self.assertTrue(self.store.get_slot(slot.id).is_booked)
        self.assertEqual([b.id for b in self.teacher.view_dashboard(self.mgr)], [booking.id])

        # After the slot ends, refresh moves it to history as Completed.
        self.clock.value = self.at(9, 10, 31)
        self.mgr.refresh_statuses(self.alice)
        self.assertEqual(self.alice.view_dashboard(self.mgr), [])
        history = self.alice.view_history(self.mgr)
        self.assertEqual(history[0].status, BookingStatus.COMPLETED)
        self.assertEqual(self.teacher.view_history(self.mgr)[0].id, booking.id)

    def test_accept_declines_competing_requests(self):
        slot = self.publish()
        a = self.book(self.alice, slot)
        b = self.book(self.bob, slot)
        self.mgr.accept_booking(self.teacher, a.id)
        self.assertEqual(self.store.get_booking(b.id).status, BookingStatus.DECLINED)
        self.assertEqual(self.store.get_booking(b.id).note, BookingManager.TAKEN_NOTE)
        with self.assertRaises(ConflictError):  # slot is locked now
            self.book(self.bob, slot)

    def test_decline_keeps_slot_open(self):
        slot = self.publish()
        b = self.book(self.alice, slot)
        self.mgr.decline_booking(self.teacher, b.id, "Please ask during class.")
        stored = self.store.get_booking(b.id)
        self.assertEqual(stored.status, BookingStatus.DECLINED)
        self.assertEqual(stored.note, "Please ask during class.")
        self.assertTrue(self.store.get_slot(slot.id).is_open)
        self.book(self.bob, slot)  # someone else can still book it

    def test_student_cancel_confirmed_releases_slot(self):
        slot = self.publish()
        b = self.book(self.alice, slot)
        self.mgr.accept_booking(self.teacher, b.id)
        self.mgr.cancel_booking(self.alice, b.id, "Schedule conflict")
        stored = self.store.get_booking(b.id)
        self.assertEqual(stored.status, BookingStatus.CANCELLED)
        self.assertEqual(stored.note, "Cancelled by student: Schedule conflict")
        self.assertTrue(self.store.get_slot(slot.id).is_open)

    def test_teacher_can_cancel_confirmed(self):
        slot = self.publish()
        b = self.book(self.alice, slot)
        self.mgr.accept_booking(self.teacher, b.id)
        self.mgr.cancel_booking(self.teacher, b.id)
        self.assertEqual(self.store.get_booking(b.id).note, "Cancelled by teacher.")

    def test_booking_validation(self):
        slot = self.publish()
        with self.assertRaises(ValidationError):  # course not handled by teacher
            self.mgr.request_booking(self.alice, slot.id, self.math.id, "Help")
        with self.assertRaises(ValidationError):  # empty purpose
            self.mgr.request_booking(self.alice, slot.id, self.cs.id, "   ")
        with self.assertRaises(ValidationError):  # too long purpose
            self.mgr.request_booking(self.alice, slot.id, self.cs.id, "x" * 201)
        self.mgr.request_booking(self.alice, slot.id, self.cs.id, "x" * 200)
        with self.assertRaises(ConflictError):  # same slot twice
            self.book(self.alice, slot)
        with self.assertRaises(PermissionDenied):  # teachers can't book
            self.mgr.request_booking(self.teacher, slot.id, self.cs.id, "Help")

    def test_student_cannot_double_book_overlapping_times(self):
        slot = self.publish(hour=10, minutes=60)
        other = self.auth.register(name="Prof. Reyes", email="reyes@school.edu",
                                   password="password1", confirm_password="password1",
                                   role="teacher", course_ids=[self.cs.id])
        other_slot = self.mgr.publish_slot(other, self.at(9, 10, 30), self.at(9, 11))
        self.book(self.alice, slot)
        with self.assertRaises(ValidationError):
            self.book(self.alice, other_slot)

    def test_cannot_book_started_slot_and_pending_expires(self):
        slot = self.publish()
        b = self.book(self.alice, slot)
        self.clock.value = self.at(9, 10, 5)
        with self.assertRaises(ValidationError):
            self.book(self.bob, slot)
        with self.assertRaises(ValidationError):
            self.mgr.accept_booking(self.teacher, b.id)
        self.mgr.refresh_statuses(self.teacher)
        stored = self.store.get_booking(b.id)
        self.assertEqual(stored.status, BookingStatus.CANCELLED)
        self.assertEqual(stored.note, BookingManager.EXPIRED_NOTE)
        self.assertEqual(self.mgr.open_slots(self.teacher.id), [])

    def test_only_owner_can_act(self):
        slot = self.publish()
        b = self.book(self.alice, slot)
        with self.assertRaises(PermissionDenied):
            self.mgr.cancel_booking(self.bob, b.id)
        with self.assertRaises(PermissionDenied):
            self.mgr.accept_booking(self.alice, b.id)
        other = self.auth.register(name="Other", email="o2@school.edu", password="password1",
                                   confirm_password="password1", role="teacher",
                                   course_ids=[self.cs.id])
        with self.assertRaises(PermissionDenied):
            self.mgr.accept_booking(other, b.id)

    def test_stale_accept_after_student_cancel(self):
        slot = self.publish()
        b = self.book(self.alice, slot)
        self.mgr.cancel_booking(self.alice, b.id)
        with self.assertRaises(ConflictError):
            self.mgr.accept_booking(self.teacher, b.id)
        self.assertTrue(self.store.get_slot(slot.id).is_open)

    def test_meeting_link_validation_and_update(self):
        slot = self.publish()
        b = self.book(self.alice, slot)
        with self.assertRaises(ValidationError):
            self.mgr.accept_booking(self.teacher, b.id, "not a link")
        # Failed validation must not have changed anything.
        self.assertEqual(self.store.get_booking(b.id).status, BookingStatus.PENDING)
        self.assertTrue(self.store.get_slot(slot.id).is_open)
        self.mgr.accept_booking(self.teacher, b.id, "")
        self.assertIsNone(self.store.get_booking(b.id).meeting_link)
        self.mgr.update_meeting_link(self.teacher, b.id, "https://teams.microsoft.com/l/x")
        self.assertEqual(self.store.get_booking(b.id).meeting_link, "https://teams.microsoft.com/l/x")

    def test_details_and_search(self):
        slot = self.publish()
        self.book(self.alice, slot)
        rows = self.mgr.details(self.alice.view_dashboard(self.mgr))
        self.assertEqual(rows[0].teacher_name, "Prof. Santos")
        self.assertEqual(rows[0].course_label, "CS202 – Object-Oriented Programming")
        self.assertEqual(len(self.mgr.search_teachers("santos")), 1)
        self.assertEqual(len(self.mgr.search_teachers("object-oriented")), 1)
        self.assertEqual(len(self.mgr.search_teachers(course_id=self.math.id)), 0)
        self.assertEqual(len(self.mgr.search_teachers("nobody")), 0)


class TestModels(unittest.TestCase):
    def test_booking_transitions_are_guarded(self):
        b = Booking("s", "t", "slot", "c", "Purpose")
        b.decline()
        with self.assertRaises(ConflictError):
            b.accept()
        with self.assertRaises(ConflictError):
            b.cancel()

    def test_status_cannot_be_assigned_directly(self):
        b = Booking("s", "t", "slot", "c", "Purpose")
        with self.assertRaises(AttributeError):
            b.status = BookingStatus.CONFIRMED  # read-only property

    def test_parse_handles_supabase_formats(self):
        timeutil.configure("Asia/Manila")
        dt = timeutil.parse("2026-10-09T02:00:00.12345+00:00")
        self.assertEqual((dt.hour, dt.tzinfo.key), (10, "Asia/Manila"))
        self.assertEqual(timeutil.parse("2026-10-09T02:00:00Z").hour, 10)
        self.assertEqual(timeutil.fmt_time(dt), "10:00 AM")


if __name__ == "__main__":
    unittest.main()
