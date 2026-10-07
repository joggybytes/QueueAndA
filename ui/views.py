"""Teacher end and Student end.

``BaseView`` holds what both ends share (sidebar, navigation, history page).
``TeacherView`` and ``StudentView`` override ``pages()`` and the dashboard
(inheritance + polymorphism), so ``app.py`` can just call ``view.render()``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import time, timedelta
from typing import Callable, ClassVar

import streamlit as st

from core import timeutil
from core.manager import BookingDetails, BookingManager
from core.models import BookingStatus, SlotStatus, Student, Teacher, User
from ui.common import form_key, md, run_action, show_flash, status_badge


class BaseView(ABC):
    NAV_KEY: ClassVar[str] = "nav"
    _views: ClassVar[dict[type[User], type[BaseView]]] = {}

    USER_CLASS: ClassVar[type[User] | None] = None

    def __init__(self, user: User, manager: BookingManager):
        self.user = user
        self.manager = manager

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.USER_CLASS is not None:
            BaseView._views[cls.USER_CLASS] = cls

    @classmethod
    def for_user(cls, user: User, manager: BookingManager) -> BaseView:
        """Pick the right end of the app for whoever logged in."""
        return cls._views[type(user)](user, manager)

    # ---- to be provided by each end ------------------------------------
    @abstractmethod
    def pages(self) -> dict[str, Callable[[], None]]:
        """Page title -> render function, in sidebar order."""

    @abstractmethod
    def counterpart_label(self) -> str:
        """'Student' for teachers, 'Teacher' for students."""

    @abstractmethod
    def counterpart(self, d: BookingDetails) -> str: ...

    # ---- shared layout -------------------------------------------------
    def render(self) -> None:
        self.manager.refresh_statuses(self.user)
        pages = self.pages()
        with st.sidebar:
            st.title("Queue&A")
            st.markdown(f"**{md(self.user.name)}**  \n{self.user.role_label} · {md(self.user.email)}")
            st.divider()
            choice = st.radio("Menu", list(pages), key=self.NAV_KEY, label_visibility="collapsed")
            st.divider()
            if st.button("Log out"):
                st.session_state.clear()
                st.rerun()
        st.header(choice)
        show_flash()
        pages[choice]()

    def go_to(self, page: str) -> None:
        """Button callback that switches the sidebar page."""
        st.session_state[self.NAV_KEY] = page

    def render_history(self) -> None:
        history = self.manager.details(self.user.view_history(self.manager), newest_first=True)
        if not history:
            st.info("No past consultations yet. Completed, declined and cancelled bookings will appear here.")
            return
        statuses = [s.value for s in BookingStatus.closed()]
        chosen = st.multiselect("Show", statuses, default=statuses)
        rows = [
            {
                "Date": timeutil.fmt_date(d.start) if d.start else "",
                "Time": (f"{timeutil.fmt_time(d.slot.start)} – {timeutil.fmt_time(d.slot.end)}"
                         if d.slot else ""),
                self.counterpart_label(): self.counterpart(d),
                "Course": d.course_label,
                "Purpose": d.booking.purpose,
                "Status": d.booking.status.value,
                "Notes": d.booking.note or "",
            }
            for d in history if d.booking.status.value in chosen
        ]
        st.caption(f"{len(rows)} consultation(s)")
        if rows:
            st.dataframe(rows, hide_index=True)

    def render_booking_header(self, d: BookingDetails, column) -> None:
        column.markdown(f"**{md(self.counterpart(d))}** · {md(d.course_label)}")
        column.caption(d.when)
        column.markdown(f"**Purpose:** {md(d.booking.purpose)}")


# =========================================================================
# Teacher end
# =========================================================================

class TeacherView(BaseView):
    USER_CLASS = Teacher
    NAV_KEY = "nav_teacher"
    user: Teacher

    def pages(self):
        return {
            "Dashboard": self.render_dashboard,
            "Publish Availability": self.render_publish,
            "Booking Requests": self.render_requests,
            "Consultation History": self.render_history,
        }

    def counterpart_label(self) -> str:
        return "Student"

    def counterpart(self, d: BookingDetails) -> str:
        return d.student_name

    # ---- Dashboard -----------------------------------------------------
    def render_dashboard(self) -> None:
        ongoing = self.manager.details(self.user.view_dashboard(self.manager))
        pending = self.user.pending_requests(self.manager)
        open_slots = [s for s in self.manager.teacher_slots(self.user) if s.is_open]

        c1, c2, c3 = st.columns(3)
        c1.metric("Upcoming consultations", len(ongoing))
        c2.metric("Pending requests", len(pending))
        c3.metric("Open schedules", len(open_slots))

        if pending:
            st.info(f"You have {len(pending)} booking request(s) waiting for your response.")
            st.button("Review booking requests", on_click=self.go_to, args=("Booking Requests",))

        st.subheader("Ongoing bookings")
        if not ongoing:
            st.caption("No confirmed consultations right now. Accepted requests will show up here.")
            if not open_slots:
                st.button("Publish your availability", on_click=self.go_to,
                          args=("Publish Availability",))
        for d in ongoing:
            self._render_confirmed_card(d)

    def _render_confirmed_card(self, d: BookingDetails) -> None:
        booking = d.booking
        with st.container(border=True):
            left, right = st.columns([3, 1])
            self.render_booking_header(d, left)
            if d.student:
                left.caption(f"Student email: {d.student.email}")
            right.markdown(status_badge(booking.status))
            if booking.meeting_link:
                right.link_button("Open meeting link", booking.meeting_link)
            else:
                right.caption("No meeting link yet")

            with st.expander("Manage booking"):
                with st.form(form_key(f"link_{booking.id}")):
                    link = st.text_input("Meeting link", value=booking.meeting_link or "",
                                         placeholder="https://meet.google.com/...")
                    if st.form_submit_button("Save meeting link"):
                        run_action(lambda: self.manager.update_meeting_link(self.user, booking.id, link),
                                   "Meeting link updated.")
                with st.form(form_key(f"cancel_{booking.id}")):
                    reason = st.text_input("Reason for cancelling (optional)")
                    if st.form_submit_button("Cancel this consultation"):
                        run_action(lambda: self.manager.cancel_booking(self.user, booking.id, reason),
                                   "Consultation cancelled. The schedule is open again.")

    # ---- Publish Availability -----------------------------------------
    def render_publish(self) -> None:
        st.caption("Publish the times when students can book a consultation with you.")
        today = timeutil.now().date()
        with st.form(form_key("publish")):
            c1, c2, c3 = st.columns(3)
            day = c1.date_input("Date", value=today, min_value=today)
            start = c2.time_input("Start time", value=time(9, 0), step=timedelta(minutes=15))
            end = c3.time_input("End time", value=time(9, 30), step=timedelta(minutes=15))
            submitted = st.form_submit_button("Publish schedule", type="primary")
        if submitted:
            run_action(lambda: self.manager.publish_slot(self.user, timeutil.combine(day, start),
                                                         timeutil.combine(day, end)),
                       f"Schedule published for {timeutil.fmt_date(timeutil.combine(day, start))}.")

        st.subheader("Your upcoming schedules")
        slots = self.manager.teacher_slots(self.user)
        if not slots:
            st.caption("You haven't published any upcoming schedules yet.")
            return
        pending_by_slot: dict[str, int] = {}
        for b in self.user.pending_requests(self.manager):
            pending_by_slot[b.slot_id] = pending_by_slot.get(b.slot_id, 0) + 1

        for slot in slots:
            with st.container(border=True):
                c1, c2, c3 = st.columns([3, 2, 1])
                c1.markdown(f"**{slot.label}**")
                if slot.status == SlotStatus.BOOKED:
                    c2.markdown("🟢 Booked")
                else:
                    count = pending_by_slot.get(slot.id, 0)
                    c2.markdown("⚪ Open" + (f" · {count} request(s)" if count else ""))
                    if c3.button("Remove", key=f"remove_{slot.id}"):
                        run_action(lambda s=slot: self.manager.remove_slot(self.user, s.id),
                                   "Schedule removed.")

    # ---- Booking Requests ---------------------------------------------
    def render_requests(self) -> None:
        requests = self.manager.details(self.user.pending_requests(self.manager))
        if not requests:
            st.info("No pending requests. New booking requests from students will appear here.")
            return
        per_slot: dict[str, int] = {}
        for d in requests:
            per_slot[d.booking.slot_id] = per_slot.get(d.booking.slot_id, 0) + 1

        st.caption("Accepting a request confirms it and locks the schedule. Other requests for "
                   "the same schedule are declined automatically.")
        for d in requests:
            booking = d.booking
            with st.container(border=True):
                left, right = st.columns([3, 1])
                self.render_booking_header(d, left)
                if d.student:
                    left.caption(f"Student email: {d.student.email}")
                right.markdown(status_badge(booking.status))
                others = per_slot.get(booking.slot_id, 1) - 1
                if others:
                    right.caption(f"{others} other request(s) for this schedule")

                with st.form(form_key(f"respond_{booking.id}")):
                    link = st.text_input("Meeting link (for Accept)",
                                         placeholder="https://zoom.us/j/... or https://meet.google.com/...")
                    reason = st.text_input("Reason (optional, for Decline)")
                    a, b, _ = st.columns([1, 1, 3])
                    accept = a.form_submit_button("Accept", type="primary")
                    decline = b.form_submit_button("Decline")
                if accept:
                    run_action(lambda: self.manager.accept_booking(self.user, booking.id, link),
                               f"Booking with {d.student_name} confirmed.")
                elif decline:
                    run_action(lambda: self.manager.decline_booking(self.user, booking.id, reason),
                               f"Request from {d.student_name} declined.")


# =========================================================================
# Student end
# =========================================================================

class StudentView(BaseView):
    USER_CLASS = Student
    NAV_KEY = "nav_student"
    user: Student

    def pages(self):
        return {
            "Dashboard": self.render_dashboard,
            "Book a Consultation": self.render_search,
            "Consultation History": self.render_history,
        }

    def counterpart_label(self) -> str:
        return "Teacher"

    def counterpart(self, d: BookingDetails) -> str:
        return d.teacher_name

    # ---- Dashboard -----------------------------------------------------
    def render_dashboard(self) -> None:
        ongoing = self.manager.details(self.user.view_dashboard(self.manager))
        pending = [d for d in ongoing if d.booking.status == BookingStatus.PENDING]
        confirmed = [d for d in ongoing if d.booking.status == BookingStatus.CONFIRMED]
        completed = [b for b in self.user.view_history(self.manager)
                     if b.status == BookingStatus.COMPLETED]

        c1, c2, c3 = st.columns(3)
        c1.metric("Confirmed", len(confirmed))
        c2.metric("Waiting for response", len(pending))
        c3.metric("Completed", len(completed))

        st.subheader("Ongoing bookings")
        if not ongoing:
            st.caption("You have no ongoing bookings.")
            st.button("Find a teacher", on_click=self.go_to, args=("Book a Consultation",),
                      type="primary")
            return
        for d in ongoing:
            self._render_booking_card(d)

    def _render_booking_card(self, d: BookingDetails) -> None:
        booking = d.booking
        with st.container(border=True):
            left, right = st.columns([3, 1])
            self.render_booking_header(d, left)
            right.markdown(status_badge(booking.status))
            if booking.status == BookingStatus.CONFIRMED:
                if booking.meeting_link:
                    right.link_button("Join meeting", booking.meeting_link, type="primary")
                else:
                    right.caption("Your teacher hasn't added a meeting link yet.")
            else:
                right.caption("Waiting for the teacher to respond.")

            with st.expander("Cancel this booking"):
                with st.form(form_key(f"cancel_{booking.id}")):
                    reason = st.text_input("Reason (optional)")
                    if st.form_submit_button("Cancel booking"):
                        run_action(lambda: self.manager.cancel_booking(self.user, booking.id, reason),
                                   "Booking cancelled.")

    # ---- Search & book -------------------------------------------------
    def render_search(self) -> None:
        courses = self.manager.courses_by_id()
        course_ids = sorted(courses, key=lambda cid: courses[cid].code)

        c1, c2 = st.columns([2, 1])
        query = c1.text_input("Search teachers", placeholder="Name, email, or course")
        course_filter = c2.selectbox(
            "Course", [None] + course_ids,
            format_func=lambda cid: "All courses" if cid is None else courses[cid].label,
        )

        teachers = self.manager.search_teachers(query, course_filter)
        if not teachers:
            st.info("No teachers match your search.")
            return

        already_requested = {b.slot_id for b in self.user.view_dashboard(self.manager)}
        for teacher in teachers:
            self._render_teacher(teacher, courses, course_filter, already_requested)

    def _render_teacher(self, teacher: Teacher, courses, course_filter, already_requested) -> None:
        teacher_courses = sorted((courses[c] for c in teacher.course_ids if c in courses),
                                 key=lambda c: c.code)
        slots = [s for s in self.manager.open_slots(teacher.id) if s.id not in already_requested]

        with st.container(border=True):
            st.markdown(f"#### {md(teacher.name)}")
            st.caption(teacher.email)
            st.markdown(" · ".join(md(c.label) for c in teacher_courses) or "_No courses listed_")
            if not slots:
                st.caption("No open schedules right now. Check back later.")
                return
            if not teacher_courses:
                st.caption("This teacher hasn't listed any courses yet.")
                return

            with st.expander(f"Book a consultation · {len(slots)} open schedule(s)"):
                slot_labels = {s.id: s.label for s in slots}
                course_labels = {c.id: c.label for c in teacher_courses}
                course_options = list(course_labels)
                default_course = (course_options.index(course_filter)
                                  if course_filter in course_options else 0)
                with st.form(form_key(f"book_{teacher.id}")):
                    slot_id = st.selectbox("Schedule", list(slot_labels), format_func=slot_labels.get)
                    course_id = st.selectbox("Course", course_options, index=default_course,
                                             format_func=course_labels.get)
                    purpose = st.text_area("Purpose of the meeting", max_chars=200,
                                           placeholder="e.g. I'd like help understanding "
                                                       "inheritance for our project.")
                    submitted = st.form_submit_button("Request consultation", type="primary")
                if submitted:
                    run_action(lambda: self.manager.request_booking(self.user, slot_id, course_id, purpose),
                               f"Request sent to {teacher.name}. You'll see it on your dashboard "
                               f"as Pending until they respond.")
