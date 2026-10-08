from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import time, timedelta
from typing import Callable, ClassVar

import streamlit as st

from core import timeutil
from core.auth import AuthManager
from core.manager import BookingDetails, BookingManager
from core.models import BookingStatus, QueueAError, SlotStatus, Student, Teacher, User
from ui.common import (bump_forms, end_aligned, flash, form_key, md, red_button_area,
                       run_action, show_flash, status_badge)


@dataclass(frozen=True)
class PageSpec:
    """One entry in the sidebar menu."""

    key: str                      # URL path, e.g. "requests"
    title: str
    icon: str                     # Material icon, e.g. ":material/inbox:"
    render: Callable[[], None]
    badge: int = 0                # number shown next to the title (0 = none)
    heading: str | None = None    # page heading, if different from the menu title


class BaseView(ABC):
    _views: ClassVar[dict[type[User], type[BaseView]]] = {}

    USER_CLASS: ClassVar[type[User] | None] = None

    def __init__(self, user: User, manager: BookingManager, auth: AuthManager):
        self.user = user
        self.manager = manager
        self.auth = auth
        self._nav_pages: dict[str, object] = {}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.USER_CLASS is not None:
            BaseView._views[cls.USER_CLASS] = cls

    @classmethod
    def for_user(cls, user: User, manager: BookingManager, auth: AuthManager) -> BaseView:
        """Pick the right end of the app for whoever logged in."""
        return cls._views[type(user)](user, manager, auth)

    # ---- to be provided by each end ------------------------------------
    @abstractmethod
    def pages(self) -> list[PageSpec]:
        """Sidebar menu entries, in order. The first one is the home page."""

    @abstractmethod
    def counterpart_label(self) -> str:
        """'Student' for teachers, 'Teacher' for students."""

    @abstractmethod
    def counterpart(self, d: BookingDetails) -> str: ...

    @abstractmethod
    def deletion_summary(self) -> str:
        """What happens to this kind of user's data when they delete their account."""

    # ---- shared layout -------------------------------------------------
    def render(self) -> None:
        self.manager.refresh_statuses(self.user)

        specs = self.pages() + [
            PageSpec("account", "Account", ":material/manage_accounts:", self.render_account),
        ]
        self._nav_pages = {
            spec.key: st.Page(self._page_runner(spec),
                              title=spec.title + (f" ({spec.badge})" if spec.badge else ""),
                              icon=spec.icon, url_path=spec.key, default=(i == 0))
            for i, spec in enumerate(specs)
        }
        current = st.navigation({f"{self.user.role_label} menu": list(self._nav_pages.values())})

        # st.navigation already draws one line under the menu, so no extra divider here.
        with st.sidebar:
            st.markdown(f"**{md(self.user.name)}**  \n{self.user.role_label} · {md(self.user.email)}")
            if st.button("Log out", icon=":material/logout:"):
                self.end_session()

        current.run()

    @staticmethod
    def _page_runner(spec: PageSpec) -> Callable[[], None]:
        def run() -> None:
            st.header(spec.heading or spec.title)
            show_flash()
            spec.render()
        return run

    def end_session(self, message: str | None = None) -> None:
        """Log out and go back to "/" so the login screen opens cleanly."""
        home = next(iter(self._nav_pages.values()))
        st.session_state.clear()
        if message:
            flash(message)
        st.switch_page(home)

    # ---- Account (shared by both ends) ---------------------------------
    def render_account(self) -> None:
        with st.container(border=True):
            st.markdown(f"**Name:** {md(self.user.name)}  \n"
                        f"**Email:** {md(self.user.email)}  \n"
                        f"**Role:** {self.user.role_label}")
            if self.user.created_at:
                st.caption(f"Member since {timeutil.fmt_date(self.user.created_at)}")

        st.subheader("Edit profile")
        with st.form(form_key("edit_profile")):
            name = st.text_input("Full name", value=self.user.name)
            email = st.text_input("Email", value=self.user.email)
            current = st.text_input("Current password (only needed to change your email)",
                                    type="password")
            save_profile = st.form_submit_button("Save changes", type="primary")
        if save_profile:
            run_action(lambda: self.auth.update_profile(self.user, name=name, email=email,
                                                        current_password=current),
                       "Your profile has been updated.")

        st.subheader("Change password")
        with st.form(form_key("change_password")):
            old_pw = st.text_input("Current password", type="password")
            new_pw = st.text_input("New password", type="password", help="At least 8 characters.")
            confirm_pw = st.text_input("Confirm new password", type="password")
            save_password = st.form_submit_button("Update password", type="primary")
        if save_password:
            run_action(lambda: self.auth.change_password(self.user, current_password=old_pw,
                                                         new_password=new_pw,
                                                         confirm_password=confirm_pw),
                       "Your password has been changed.")

        st.subheader("Delete account")
        st.warning(self.deletion_summary() + " **This can't be undone.**", icon="⚠️")
        with st.form(form_key("delete_account")):
            password = st.text_input("Enter your password to confirm", type="password")
            confirmed = st.checkbox("I understand that my account will be permanently deleted.")
            with red_button_area("deleteaccount", "me"):
                delete = st.form_submit_button("Delete my account", icon=":material/delete_forever:")
        if delete:
            try:
                self.auth.delete_account(self.user, password, confirmed, self.manager)
            except QueueAError as exc:
                st.error(str(exc))
                return
            self.end_session("Your account has been deleted.")

    def welcome_heading(self) -> str:
        return f"Welcome, {self.user.name}!"

    def go_to(self, key: str) -> None:
        """Jump to another page of the sidebar menu."""
        st.switch_page(self._nav_pages[key])

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
    user: Teacher

    def pages(self) -> list[PageSpec]:
        pending = len(self.user.pending_requests(self.manager))
        return [
            PageSpec("dashboard", "Dashboard", ":material/dashboard:", self.render_dashboard,
                     heading=self.welcome_heading()),
            PageSpec("availability", "Publish Availability", ":material/event_available:",
                     self.render_publish),
            PageSpec("requests", "Booking Requests", ":material/inbox:", self.render_requests,
                     badge=pending),
            PageSpec("courses", "My Courses", ":material/menu_book:", self.render_courses),
            PageSpec("history", "Consultation History", ":material/history:", self.render_history),
        ]

    def counterpart_label(self) -> str:
        return "Student"

    def deletion_summary(self) -> str:
        return ("Deleting your account cancels your pending and confirmed consultations and "
                "removes your published schedules. Your name and email are erased. Students keep "
                "their past consultation records, shown with \"Deleted user\" as the teacher.")

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
            if st.button("Review booking requests", type="primary"):
                self.go_to("requests")

        st.subheader("Ongoing bookings")
        if not ongoing:
            st.caption("No confirmed consultations right now. Accepted requests will show up here.")
            if not open_slots:
                if st.button("Publish your availability", type="primary"):
                    self.go_to("availability")
        for d in ongoing:
            self._render_confirmed_card(d)

    def _render_confirmed_card(self, d: BookingDetails) -> None:
        booking = d.booking
        with st.container(border=True):
            left, right = st.columns([3, 1])
            right = end_aligned(right, f"confirmed_{booking.id}")
            self.render_booking_header(d, left)
            if d.student:
                left.caption(f"Student email: {d.student.email}")
            now = self.manager.now()
            started = d.slot is None or d.slot.has_started(now)
            badge = status_badge(booking.status)
            if d.slot and started and not d.slot.has_ended(now):
                badge += " · in progress"
            right.markdown(badge)
            if booking.meeting_link:
                right.link_button("Open meeting link", booking.meeting_link,
                                  icon=":material/videocam:")
            else:
                right.caption("No meeting link yet")
            self._render_complete_controls(d, right, early=not started)

            with st.expander("Manage booking"):
                with st.form(form_key(f"manage_{booking.id}"), border=False):
                    link = st.text_input("Meeting link (for Save)", value=booking.meeting_link or "",
                                         placeholder="https://meet.google.com/...")
                    reason = st.text_input("Reason (optional, for Cancel)")
                    with st.container(horizontal=True, gap="small"):  # buttons side by side
                        save = st.form_submit_button("Save meeting link", type="primary")
                        with red_button_area("cancel", booking.id):
                            cancel = st.form_submit_button("Cancel this consultation")
                if save:
                    run_action(lambda: self.manager.update_meeting_link(self.user, booking.id, link),
                               "Meeting link updated.")
                elif cancel:
                    run_action(lambda: self.manager.cancel_booking(self.user, booking.id, reason),
                               "Consultation cancelled. The schedule is open again.")

    def _render_complete_controls(self, d: BookingDetails, column, early: bool) -> None:
        """'Mark as completed' button. Before the scheduled start it asks for
        confirmation with a warning instead of completing straight away."""
        booking = d.booking
        confirm_key = f"confirm_complete_{booking.id}"
        done_message = f"Consultation with {d.student_name} marked as completed."

        clicked = column.button(
            "Mark as completed", key=f"complete_{booking.id}", type="primary",
            icon=":material/task_alt:",
            help=("This meeting hasn't started yet. You'll be asked to confirm." if early else None),
        )
        if clicked:
            if early:
                st.session_state[confirm_key] = True
            else:
                run_action(lambda: self.manager.mark_completed(self.user, booking.id), done_message)

        if early and st.session_state.get(confirm_key):
            st.warning(f"This meeting is scheduled for **{d.when}** and hasn't started yet. "
                       "Are you sure you want to mark it as completed?", icon="⚠️")
            with st.container(horizontal=True, gap="small"):  # buttons side by side
                yes = st.button("Yes, mark as completed", key=f"complete_yes_{booking.id}",
                                type="primary")
                no = st.button("Not yet", key=f"complete_no_{booking.id}")
            if yes:
                st.session_state.pop(confirm_key, None)
                run_action(lambda: self.manager.mark_completed(self.user, booking.id,
                                                               confirm_early=True),
                           done_message)
            if no:
                st.session_state.pop(confirm_key, None)
                st.rerun()

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
                    with end_aligned(c3, f"slot_{slot.id}"), red_button_area("remove", slot.id):
                        remove = st.button("Remove", key=f"remove_{slot.id}")
                    if remove:
                        run_action(lambda s=slot: self.manager.remove_slot(self.user, s.id),
                                   "Schedule removed.")

    # ---- My Courses ---------------------------------------------------
    def render_courses(self) -> None:
        st.caption("Students can only book you for the courses listed here.")
        courses = self.manager.courses_by_id()
        mine = sorted((courses[c] for c in self.user.course_ids if c in courses),
                      key=lambda c: c.code)

        st.subheader(f"Courses you handle ({len(mine)})")
        if not mine:
            st.info("You don't have any courses yet. Add at least one below so students can book you.")
        only_one = len(mine) == 1
        for course in mine:
            with st.container(border=True):
                left, right = st.columns([4, 1])
                right = end_aligned(right, f"course_{course.id}")
                left.markdown(f"**{md(course.code)}** – {md(course.title)}")
                with right, red_button_area("removecourse", course.id):
                    remove = st.button(
                        "Remove", key=f"remove_course_{course.id}", disabled=only_one,
                        help="You need at least one course." if only_one else None,
                    )
                if remove:
                    run_action(lambda c=course: self.manager.remove_course(self.user, c.id),
                               f"{course.code} removed from your courses.")
                self._render_edit_course(course)
        if mine:
            st.caption("Removing a course doesn't cancel bookings already made for it. "
                       "Students just can't choose it for new bookings.")

        st.subheader("Add courses")
        available = sorted((c for c in courses.values() if not self.user.teaches(c.id)),
                           key=lambda c: c.code)
        if available:
            labels = {c.id: c.label for c in available}
            with st.form(form_key("add_courses")):
                chosen = st.multiselect("Choose one or more courses", list(labels),
                                        format_func=labels.get,
                                        placeholder="Select courses to add")
                add = st.form_submit_button("Add selected courses", type="primary")
            if add:
                run_action(lambda: self.manager.add_courses(self.user, chosen),
                           f"Added {len(chosen)} course(s).")
        else:
            st.caption("You already handle every course in the list.")

        st.markdown("**Course not in the list?**")
        with st.form(form_key("create_course")):
            c1, c2 = st.columns([1, 2])
            code = c1.text_input("Course code", placeholder=CS101")
            title = c2.text_input("Course title", placeholder="Introduction to Computer Systems")
            create = st.form_submit_button("Create and add course", type="primary")
        if create:
            try:
                course, existed = self.manager.create_course_for(self.user, code, title)
            except QueueAError as exc:
                st.error(str(exc))
            else:
                note = (f"{course.code} already existed as \"{course.title}\", so it was added to "
                        "your courses." if existed else f"{course.label} created and added to your courses.")
                bump_forms()
                flash(note)
                st.rerun()

    def _render_edit_course(self, course) -> None:
        with st.expander("Edit course", icon=":material/edit:"):
            others = self.manager.other_teachers_handling(self.user, course.id)
            if others:
                st.info(f"{others} other teacher(s) also handle this course. "
                        "Your changes will show for them too.")
            with st.form(form_key(f"edit_course_{course.id}"), border=False):
                c1, c2 = st.columns([1, 2])
                code = c1.text_input("Course code", value=course.code)
                title = c2.text_input("Course title", value=course.title)
                save = st.form_submit_button("Save changes", type="primary")
            if save:
                run_action(lambda: self.manager.update_course(self.user, course.id, code, title),
                           f"Course updated to {code.strip().upper()} – {title.strip()}.")

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
                right = end_aligned(right, f"request_{booking.id}")
                self.render_booking_header(d, left)
                if d.student:
                    left.caption(f"Student email: {d.student.email}")
                right.markdown(status_badge(booking.status))
                others = per_slot.get(booking.slot_id, 1) - 1
                if others:
                    right.caption(f"{others} other request(s) for this schedule")

                with st.form(form_key(f"respond_{booking.id}"), border=False):
                    link = st.text_input("Meeting link (for Accept)",
                                         placeholder="eg. https://meet.google.com/...")
                    reason = st.text_input("Reason (optional, for Decline)")
                    with st.container(horizontal=True, gap="small"):  # buttons side by side
                        accept = st.form_submit_button("Accept", type="primary")
                        with red_button_area("decline", booking.id):
                            decline = st.form_submit_button("Decline")
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
    user: Student

    def pages(self) -> list[PageSpec]:
        return [
            PageSpec("dashboard", "Dashboard", ":material/dashboard:", self.render_dashboard,
                     heading=self.welcome_heading()),
            PageSpec("book", "Book a Consultation", ":material/person_search:", self.render_search),
            PageSpec("history", "Consultation History", ":material/history:", self.render_history),
        ]

    def counterpart_label(self) -> str:
        return "Teacher"

    def deletion_summary(self) -> str:
        return ("Deleting your account cancels your pending and confirmed bookings. Your name and "
                "email are erased. Teachers keep their past consultation records, shown with "
                "\"Deleted user\" as the student.")

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
            if st.button("Find a teacher", type="primary"):
                self.go_to("book")
            return
        for d in ongoing:
            self._render_booking_card(d)

    def _render_booking_card(self, d: BookingDetails) -> None:
        booking = d.booking
        with st.container(border=True):
            left, right = st.columns([3, 1])
            right = end_aligned(right, f"student_booking_{booking.id}")
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
                with st.form(form_key(f"cancel_{booking.id}"), border=False):
                    reason = st.text_input("Reason (optional)")
                    with red_button_area("cancel", booking.id):
                        cancel = st.form_submit_button("Cancel booking")
                    if cancel:
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
                with st.form(form_key(f"book_{teacher.id}"), border=False):
                    slot_id = st.selectbox("Schedule", list(slot_labels), format_func=slot_labels.get)
                    course_id = st.selectbox("Course", course_options, index=default_course,
                                             format_func=course_labels.get)
                    purpose = st.text_area("Purpose of the meeting", max_chars=200,
                                           placeholder="e.g I have a question about an assignment.")
                    submitted = st.form_submit_button("Request consultation", type="primary")
                if submitted:
                    run_action(lambda: self.manager.request_booking(self.user, slot_id, course_id, purpose),
                               f"Request sent to {teacher.name}. You'll see it on your dashboard "
                               f"as Pending until they respond.")
