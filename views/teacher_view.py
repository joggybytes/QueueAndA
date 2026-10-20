from __future__ import annotations

from datetime import time, timedelta

import streamlit as st  # pyright: ignore[reportMissingImports]

from controllers.booking_controller import BookingDetails
from models.errors import QueueAError
from models.schedule_slot import SlotStatus
from models.user import Teacher
from utils import timeutil
from views.base_view import BaseView, PageSpec
from views.common import (bump_forms, card, end_aligned, flash, form_key, md, red_button_area,
                          run_action, status_badge)


# teacher side

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

    # dashboard
    def render_dashboard(self) -> None:
        ongoing = self.manager.details(self.user.view_dashboard(self.manager))
        pending = self.user.pending_requests(self.manager)
        open_slots = [s for s in self.manager.teacher_slots(self.user) if s.is_open]
        self.page_header()

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
        with card(f"confirmed_{booking.id}"):
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
                    link = st.text_input("Meeting link", value=booking.meeting_link or "",
                                         placeholder="https://meet.google.com/...")
                    reason = st.text_input("Reason (optional, for Cancel)")
                    with st.container(horizontal=True, gap="small"):  # side by side
                        save = st.form_submit_button("Save meeting link", type="primary")
                        with red_button_area("cancel", str(booking.id)):
                            cancel = st.form_submit_button("Cancel this consultation")
                if save and booking.id is not None:
                    run_action(lambda: self.manager.update_meeting_link(self.user, str(booking.id), link),
                               "Meeting link updated.")
                elif cancel and booking.id is not None:
                    run_action(lambda: self.manager.cancel_booking(self.user, str(booking.id), reason),
                               "Consultation cancelled. The schedule is open again.")

    def _render_complete_controls(self, d: BookingDetails, column, early: bool) -> None:
        """mark as completed, warns if its too early"""
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
            elif booking.id is not None:
                run_action(lambda: self.manager.mark_completed(self.user, str(booking.id)), done_message)

        if early and st.session_state.get(confirm_key):
            st.warning(f"This meeting is scheduled for **{d.when}** and hasn't started yet. "
                       "Are you sure you want to mark it as completed?", icon="⚠️")
            with st.container(horizontal=True, gap="small"):  # side by side
                yes = st.button("Yes, mark as completed", key=f"complete_yes_{booking.id}",
                                type="primary")
                no = st.button("Not yet", key=f"complete_no_{booking.id}")
            if yes:
                st.session_state.pop(confirm_key, None)
                if booking.id is not None:
                    run_action(lambda: self.manager.mark_completed(self.user, str(booking.id),
                                                                   confirm_early=True),
                               done_message)
            if no:
                st.session_state.pop(confirm_key, None)
                st.rerun()

    # publish availability
    def render_publish(self) -> None:
        slots = self.manager.teacher_slots(self.user)
        pending_by_slot: dict[str, int] = {}
        for b in self.user.pending_requests(self.manager):
            pending_by_slot[b.slot_id] = pending_by_slot.get(b.slot_id, 0) + 1
        self.page_header()

        st.caption("Publish the times when students can book a consultation with you.")
        today = timeutil.now().date()
        # old date cant be in the past
        if st.session_state.get("publish_date") is not None and st.session_state["publish_date"] < today:
            del st.session_state["publish_date"]
        # fixed keys so the date and time stay after publishing
        with st.form("publish"):
            c1, c2, c3 = st.columns(3)
            day = c1.date_input("Date", value=today, min_value=today, key="publish_date")
            start = c2.time_input("Start time", value=time(9, 0), step=timedelta(minutes=15),
                                  format="12h", key="publish_start")
            end = c3.time_input("End time", value=time(9, 30), step=timedelta(minutes=15),
                                format="12h", key="publish_end")
            submitted = st.form_submit_button("Publish schedule", type="primary")
        if submitted:
            run_action(lambda: self.manager.publish_slot(self.user, timeutil.combine(day, start),
                                                         timeutil.combine(day, end)),
                       f"Schedule published for {timeutil.fmt_date(timeutil.combine(day, start))}.")

        st.subheader("Your upcoming schedules")
        if not slots:
            st.caption("You haven't published any upcoming schedules yet.")
            return

        for slot in slots:
            with card(f"slot_{slot.id if slot.id is not None else slot.label}"):
                c1, c2, c3 = st.columns([3, 2, 1])
                c1.markdown(f"**{slot.label}**")
                if slot.status == SlotStatus.BOOKED:
                    c2.markdown("🟢 Booked")
                else:
                    count = pending_by_slot.get(slot.id, 0)
                    c2.markdown("⚪ Open" + (f" · {count} request(s)" if count else ""))
                    slot_key = str(slot.id) if slot.id is not None else f"slot_{slot.label}"
                    with end_aligned(c3, f"slot_{slot_key}"), red_button_area("remove", slot_key):
                        remove = st.button("Remove", key=f"remove_{slot_key}")
                    if remove and slot.id is not None:
                        run_action(lambda slot_id=slot.id: self.manager.remove_slot(self.user, slot_id),
                                   "Schedule removed.")

    # my courses
    def render_courses(self) -> None:
        courses = self.manager.courses_by_id()
        mine = sorted((courses[c] for c in self.user.course_ids if c in courses),
                      key=lambda c: c.code)
        shared_with = {c.id: self.manager.other_teachers_handling(self.user, c.id) for c in mine}
        self.page_header()

        st.caption("Students can only book you for the courses listed here.")

        st.subheader(f"Courses you handle ({len(mine)})")
        if not mine:
            st.info("You don't have any courses yet. Add at least one below so students can book you.")
        only_one = len(mine) == 1
        for course in mine:
            with card(f"course_{course.id if course.id is not None else course.code}"):
                left, right = st.columns([4, 1])
                course_key = str(course.id) if course.id is not None else f"course_{course.code}"
                right = end_aligned(right, f"course_{course_key}")
                left.markdown(f"**{md(course.code)}** – {md(course.title)}")
                with right, red_button_area("removecourse", course_key):
                    remove = st.button(
                        "Remove", key=f"remove_course_{course_key}", disabled=only_one,
                        help="You need at least one course." if only_one else None,
                    )
                if remove:
                    run_action(lambda c=course: self.manager.remove_course(self.user, c.id),
                               f"{course.code} removed from your courses.")
                self._render_edit_course(course, shared_with.get(course.id, 0))
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
            code = c1.text_input("Course code", placeholder="CS101")
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

    def _render_edit_course(self, course, others: int) -> None:
        with st.expander("Edit course", icon=":material/edit:"):
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

    # booking requests
    def render_requests(self) -> None:
        requests = self.manager.details(self.user.pending_requests(self.manager))
        self.page_header()
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
            with card(f"request_{booking.id}"):
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
                    link = st.text_input("Meeting link (Required)",
                                         placeholder="eg. https://meet.google.com/...")
                    reason = st.text_input("Reason (optional, for Decline)")
                    with st.container(horizontal=True, gap="small"):  # side by side
                        accept = st.form_submit_button("Accept", type="primary")
                        with red_button_area("decline", booking.id):
                            decline = st.form_submit_button("Decline")
                if accept:
                    run_action(lambda: self.manager.accept_booking(self.user, booking.id, link),
                               f"Booking with {d.student_name} confirmed.")
                elif decline:
                    run_action(lambda: self.manager.decline_booking(self.user, booking.id, reason),
                               f"Request from {d.student_name} declined.")
