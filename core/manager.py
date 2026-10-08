from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from core import timeutil
from core.datastore import DataStore
from core.models import (Booking, BookingStatus, ConflictError, Course, PermissionDenied,
                         ScheduleSlot, SlotStatus, Student, Teacher, User, ValidationError)


class EarlyCompletionWarning(ValidationError):
    """Raised when a meeting is marked completed before its start time without
    the teacher confirming it."""


@dataclass(frozen=True)
class BookingDetails:
    """A booking together with everything the screens need to display it."""

    booking: Booking
    slot: ScheduleSlot | None
    course: Course | None
    student: User | None
    teacher: User | None

    @property
    def start(self) -> datetime | None:
        return self.slot.start if self.slot else None

    @property
    def when(self) -> str:
        return self.slot.label if self.slot else "Schedule unavailable"

    @property
    def course_label(self) -> str:
        return self.course.label if self.course else "Unknown course"

    @property
    def student_name(self) -> str:
        return self.student.name if self.student else "Unknown student"

    @property
    def teacher_name(self) -> str:
        return self.teacher.name if self.teacher else "Unknown teacher"


class BookingManager:
    MIN_DURATION = timedelta(minutes=10)
    MAX_DURATION = timedelta(hours=4)

    EXPIRED_NOTE = "Expired: the teacher did not respond before the schedule started."
    TAKEN_NOTE = "Another student was booked for this schedule."
    REMOVED_NOTE = "The teacher removed this schedule."
    EARLY_NOTE = "Marked as completed before the scheduled time."

    def __init__(self, store: DataStore, clock: Callable[[], datetime] = timeutil.now):
        self._store = store
        self._clock = clock

    def now(self) -> datetime:
        return self._clock()

    # =================================================================
    # Courses and teachers
    # =================================================================
    def list_courses(self) -> list[Course]:
        return self._store.list_courses()

    def courses_by_id(self) -> dict[str, Course]:
        return {c.id: c for c in self._store.list_courses()}

    def courses_for(self, teacher: Teacher) -> list[Course]:
        courses = self.courses_by_id()
        found = [courses[cid] for cid in teacher.course_ids if cid in courses]
        return sorted(found, key=lambda c: c.code)

    def search_teachers(self, query: str = "", course_id: str | None = None) -> list[Teacher]:
        courses = self.courses_by_id()
        needle = (query or "").strip().lower()
        results = []
        for teacher in self._store.list_teachers():
            if course_id and not teacher.teaches(course_id):
                continue
            if needle:
                haystack = " ".join(
                    [teacher.name, teacher.email]
                    + [courses[c].label for c in teacher.course_ids if c in courses]
                ).lower()
                if needle not in haystack:
                    continue
            results.append(teacher)
        return results

    # =================================================================
    # Teacher's courses (Teacher end -> My Courses)
    # =================================================================
    def add_courses(self, teacher: User, course_ids: list[str]) -> Teacher:
        """Add one or more existing courses to the courses a teacher handles."""
        teacher = self._require_teacher(teacher)
        if not course_ids:
            raise ValidationError("Choose at least one course to add.")
        known = self.courses_by_id()
        unknown = [cid for cid in course_ids if cid not in known]
        if unknown:
            raise ValidationError("One of the selected courses no longer exists. Refresh and try again.")
        return self._save_courses(teacher, list(teacher.course_ids) + list(course_ids))

    def remove_course(self, teacher: User, course_id: str) -> Teacher:
        """Stop handling a course. Bookings already made for it are not affected."""
        teacher = self._require_teacher(teacher)
        if not teacher.teaches(course_id):
            return teacher
        remaining = [cid for cid in teacher.course_ids if cid != course_id]
        if not remaining:
            raise ValidationError("You need at least one course so students can book with you.")
        return self._save_courses(teacher, remaining)

    def create_course_for(self, teacher: User, code: str, title: str) -> tuple[Course, bool]:
        """Add a course that isn't in the list yet and attach it to the teacher.

        If a course with the same code already exists, that course is used
        instead of creating a duplicate. Returns ``(course, already_existed)``.
        """
        teacher = self._require_teacher(teacher)
        course = Course(code, title)  # validates code and title
        existing = self._store.get_course_by_code(course.code)
        course = existing or self._store.add_course(course)
        self._save_courses(teacher, list(teacher.course_ids) + [course.id])
        return course, existing is not None

    def update_course(self, teacher: User, course_id: str, code: str, title: str) -> Course:
        """Rename a course (code and/or title). Only a teacher who handles it may do this."""
        teacher = self._require_teacher(teacher)
        if not teacher.teaches(course_id):
            raise PermissionDenied("You can only edit courses you handle.")
        course = Course(code, title, course_id=course_id)  # validates both fields
        clash = self._store.get_course_by_code(course.code)
        if clash is not None and clash.id != course_id:
            raise ValidationError(f"Another course already uses the code {course.code}.")
        return self._store.update_course(course)

    def other_teachers_handling(self, teacher: User, course_id: str) -> int:
        """How many other teachers would also see a change to this course."""
        return sum(1 for t in self._store.list_teachers()
                   if t.id != teacher.id and t.teaches(course_id))

    def _require_teacher(self, user: User) -> Teacher:
        if not isinstance(user, Teacher):
            raise PermissionDenied("Only teachers can manage courses.")
        fresh = self._store.get_user(user.id)  # use the latest saved course list
        if not isinstance(fresh, Teacher):
            raise PermissionDenied("Only teachers can manage courses.")
        return fresh

    def _save_courses(self, teacher: Teacher, course_ids: list[str]) -> Teacher:
        self._store.set_teacher_courses(teacher.id, list(dict.fromkeys(course_ids)))
        return self._store.get_user(teacher.id)

    # =================================================================
    # Schedule slots (Teacher end -> Publish Availability)
    # =================================================================
    def publish_slot(self, teacher: User, start: datetime, end: datetime) -> ScheduleSlot:
        if not isinstance(teacher, Teacher):
            raise PermissionDenied("Only teachers can publish consultation schedules.")
        if end <= start:
            raise ValidationError("End time must be after the start time.")
        if start <= self.now():
            raise ValidationError("Choose a start time in the future.")
        duration = end - start
        if duration < self.MIN_DURATION:
            raise ValidationError("A consultation slot must be at least 10 minutes long.")
        if duration > self.MAX_DURATION:
            raise ValidationError("A consultation slot can be at most 4 hours long.")
        for existing in self._store.list_slots(teacher.id, [SlotStatus.OPEN, SlotStatus.BOOKED]):
            if existing.overlaps(start, end):
                raise ValidationError(f"This overlaps with your schedule on {existing.label}.")
        return self._store.add_slot(ScheduleSlot(teacher.id, start, end))

    def teacher_slots(self, teacher: Teacher, upcoming_only: bool = True) -> list[ScheduleSlot]:
        slots = self._store.list_slots(teacher.id, [SlotStatus.OPEN, SlotStatus.BOOKED])
        if upcoming_only:
            now = self.now()
            slots = [s for s in slots if not s.has_ended(now)]
        return slots

    def open_slots(self, teacher_id: str) -> list[ScheduleSlot]:
        """Slots a student can still request."""
        now = self.now()
        return [s for s in self._store.list_slots(teacher_id, [SlotStatus.OPEN])
                if not s.has_started(now)]

    def remove_slot(self, teacher: User, slot_id: str) -> None:
        slot = self._store.get_slot(slot_id)
        if slot is None or slot.teacher_id != teacher.id:
            raise PermissionDenied("That schedule doesn't belong to you.")
        if slot.is_removed:
            return
        previous = slot.status
        slot.remove()  # refuses if a booking is confirmed
        if not self._store.update_slot_status(slot, expected=previous):
            raise ConflictError("This schedule just changed. Refresh and try again.")
        for pending in self._store.list_bookings(slot_id=slot.id, statuses=[BookingStatus.PENDING]):
            pending.decline(self.REMOVED_NOTE)
            self._store.update_booking(pending, expected=BookingStatus.PENDING)

    # =================================================================
    # Bookings
    # =================================================================
    def bookings_for(self, *, student_id: str | None = None, teacher_id: str | None = None,
                     statuses: list[BookingStatus] | None = None,
                     newest_first: bool = False) -> list[Booking]:
        bookings = self._store.list_bookings(student_id=student_id, teacher_id=teacher_id,
                                             statuses=statuses)
        return list(reversed(bookings)) if newest_first else bookings

    def request_booking(self, student: User, slot_id: str, course_id: str,
                        purpose: str) -> Booking:
        """Student end: request a consultation. The booking starts as Pending."""
        if not isinstance(student, Student):
            raise PermissionDenied("Only students can book consultations.")
        if not slot_id:
            raise ValidationError("Choose a schedule.")
        if not course_id:
            raise ValidationError("Choose a course.")

        slot = self._store.get_slot(slot_id)
        if slot is None or slot.is_removed:
            raise ValidationError("This schedule is no longer available.")
        if not slot.is_open:
            raise ConflictError("This schedule has already been booked. Please choose another time.")
        if slot.has_started(self.now()):
            raise ValidationError("This schedule has already started. Please choose a later time.")

        teacher = self._store.get_user(slot.teacher_id)
        if not isinstance(teacher, Teacher):
            raise ValidationError("This teacher is no longer available.")
        if not teacher.teaches(course_id):
            raise ValidationError("Please choose a course handled by this teacher.")

        booking = Booking(student.id, teacher.id, slot.id, course_id, purpose)  # validates purpose

        mine = self._store.list_bookings(student_id=student.id, statuses=BookingStatus.active())
        if any(b.slot_id == slot.id for b in mine):
            raise ConflictError("You already have a request for this schedule.")
        my_slots = self._store.get_slots(b.slot_id for b in mine)
        for other in mine:
            other_slot = my_slots.get(other.slot_id)
            if other_slot and other_slot.overlaps(slot.start, slot.end):
                raise ValidationError(
                    f"You already have a {other.status.value.lower()} booking at that time "
                    f"({other_slot.label})."
                )
        return self._store.add_booking(booking)

    def accept_booking(self, teacher: User, booking_id: str,
                       meeting_link: str | None = None) -> Booking:
        """Teacher end: accept a request, lock the slot, and add a meeting link."""
        booking = self._owned_booking(teacher, booking_id, Teacher)
        if booking.status != BookingStatus.PENDING:
            raise ConflictError(f"This request is already {booking.status.value.lower()}.")
        slot = self._store.get_slot(booking.slot_id)
        if slot is None or not slot.is_open:
            raise ConflictError("This schedule is no longer open.")
        if slot.has_started(self.now()):
            raise ValidationError("This schedule has already started, so it can't be accepted.")

        booking.accept(meeting_link)  # validates the link before anything is saved
        slot.lock()
        if not self._store.update_slot_status(slot, expected=SlotStatus.OPEN):
            raise ConflictError("This schedule was just booked. Refresh and try again.")
        if not self._store.update_booking(booking, expected=BookingStatus.PENDING):
            slot.release()
            self._store.update_slot_status(slot, expected=SlotStatus.BOOKED)
            raise ConflictError("The student cancelled this request a moment ago.")

        # One confirmed booking per slot: decline everyone else who asked for it.
        for other in self._store.list_bookings(slot_id=slot.id, statuses=[BookingStatus.PENDING]):
            other.decline(self.TAKEN_NOTE)
            self._store.update_booking(other, expected=BookingStatus.PENDING)
        return booking

    def decline_booking(self, teacher: User, booking_id: str, reason: str | None = None) -> Booking:
        booking = self._owned_booking(teacher, booking_id, Teacher)
        booking.decline(reason)
        if not self._store.update_booking(booking, expected=BookingStatus.PENDING):
            raise ConflictError("This request just changed. Refresh and try again.")
        return booking

    def cancel_booking(self, user: User, booking_id: str, reason: str | None = None) -> Booking:
        """Either party can cancel a pending or confirmed booking."""
        booking = self._owned_booking(user, booking_id)
        previous = booking.status
        reason = (reason or "").strip()
        booking.cancel(f"Cancelled by {user.role}" + (f": {reason}" if reason else "."))
        if not self._store.update_booking(booking, expected=previous):
            raise ConflictError("This booking just changed. Refresh and try again.")
        if previous == BookingStatus.CONFIRMED:
            slot = self._store.get_slot(booking.slot_id)
            if slot is not None and slot.is_booked:
                slot.release()
                self._store.update_slot_status(slot, expected=SlotStatus.BOOKED)
        return booking

    def is_early(self, slot: ScheduleSlot | None) -> bool:
        """True when a meeting's scheduled start time hasn't arrived yet."""
        return slot is not None and not slot.has_started(self.now())

    def mark_completed(self, teacher: User, booking_id: str, confirm_early: bool = False) -> Booking:
        """Teacher end: mark a confirmed consultation as done.

        Completing a meeting before its scheduled start is allowed, but only
        when the teacher has confirmed it (``confirm_early=True``) after
        seeing a warning. The booking's note records that it ended early.
        """
        booking = self._owned_booking(teacher, booking_id, Teacher)
        if booking.status != BookingStatus.CONFIRMED:
            raise ConflictError("Only confirmed consultations can be marked as completed.")
        slot = self._store.get_slot(booking.slot_id)
        early = self.is_early(slot)
        if early and not confirm_early:
            raise EarlyCompletionWarning(
                f"This meeting is scheduled for {slot.label} and hasn't started yet. "
                "Confirm that you want to mark it as completed anyway."
            )
        booking.complete(self.EARLY_NOTE if early else None)
        if not self._store.update_booking(booking, expected=BookingStatus.CONFIRMED):
            raise ConflictError("This booking just changed. Refresh and try again.")
        return booking

    def update_meeting_link(self, teacher: User, booking_id: str, meeting_link: str | None) -> Booking:
        booking = self._owned_booking(teacher, booking_id, Teacher)
        booking.update_meeting_link(meeting_link)
        if not self._store.update_booking(booking, expected=BookingStatus.CONFIRMED):
            raise ConflictError("This booking just changed. Refresh and try again.")
        return booking

    def close_account(self, user: User) -> None:
        """Clean up before an account is deleted: cancel the user's pending and
        confirmed bookings, and take down a teacher's remaining schedules."""
        note = f"Cancelled: the {user.role} deleted their account."
        for booking in self._store.list_bookings(statuses=BookingStatus.active(),
                                                 **user.booking_filter()):
            previous = booking.status
            booking.cancel(note)
            saved = self._store.update_booking(booking, expected=previous)
            if saved and previous == BookingStatus.CONFIRMED:
                slot = self._store.get_slot(booking.slot_id)
                if slot is not None and slot.is_booked:
                    slot.release()
                    self._store.update_slot_status(slot, expected=SlotStatus.BOOKED)
        if isinstance(user, Teacher):
            for slot in self._store.list_slots(user.id, [SlotStatus.OPEN, SlotStatus.BOOKED]):
                previous = slot.status
                slot.release()
                slot.remove()
                self._store.update_slot_status(slot, expected=previous)

    def refresh_statuses(self, user: User) -> None:
        """Move finished consultations to history and expire unanswered requests."""
        now = self.now()
        active = self._store.list_bookings(statuses=BookingStatus.active(), **user.booking_filter())
        slots = self._store.get_slots(b.slot_id for b in active)
        for booking in active:
            slot = slots.get(booking.slot_id)
            if slot is None:
                continue
            if booking.status == BookingStatus.CONFIRMED and slot.has_ended(now):
                booking.complete()
                self._store.update_booking(booking, expected=BookingStatus.CONFIRMED)
            elif booking.status == BookingStatus.PENDING and slot.has_started(now):
                booking.cancel(self.EXPIRED_NOTE)
                self._store.update_booking(booking, expected=BookingStatus.PENDING)

    # =================================================================
    # Display helpers
    # =================================================================
    def details(self, bookings: list[Booking], newest_first: bool = False) -> list[BookingDetails]:
        if not bookings:
            return []
        slots = self._store.get_slots(b.slot_id for b in bookings)
        courses = self.courses_by_id()
        people = self._store.get_users([b.student_id for b in bookings]
                                       + [b.teacher_id for b in bookings])
        rows = [BookingDetails(b, slots.get(b.slot_id), courses.get(b.course_id),
                               people.get(b.student_id), people.get(b.teacher_id))
                for b in bookings]
        far_past = datetime.min.replace(tzinfo=timeutil.tz())
        rows.sort(key=lambda d: d.start or far_past, reverse=newest_first)
        return rows

    # =================================================================
    # Internal
    # =================================================================
    def _owned_booking(self, user: User, booking_id: str,
                       required_role: type[User] | None = None) -> Booking:
        if required_role is not None and not isinstance(user, required_role):
            raise PermissionDenied(f"Only a {required_role.ROLE} can do that.")
        booking = self._store.get_booking(booking_id)
        if booking is None or not user.owns_booking(booking):
            raise PermissionDenied("That booking doesn't belong to you.")
        return booking
