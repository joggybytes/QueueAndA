from __future__ import annotations

import streamlit as st  # pyright: ignore[reportMissingImports]

from controllers.booking_controller import BookingDetails
from models.booking import BookingStatus
from models.user import Student, Teacher
from views.base_view import BaseView, PageSpec
from views.common import card, end_aligned, form_key, md, red_button_area, run_action, status_badge


# student side

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

    # dashboard
    def render_dashboard(self) -> None:
        ongoing = self.manager.details(self.user.view_dashboard(self.manager))
        pending = [d for d in ongoing if d.booking.status == BookingStatus.PENDING]
        confirmed = [d for d in ongoing if d.booking.status == BookingStatus.CONFIRMED]
        completed = [b for b in self.user.view_history(self.manager)
                     if b.status == BookingStatus.COMPLETED]
        self.page_header()

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
        with card(f"booking_{booking.id}"):
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

    # search and book
    def render_search(self) -> None:
        courses = self.manager.courses_by_id()
        course_options = [None] + sorted(courses, key=lambda cid: courses[cid].code)

        # search runs before drawing the boxes
        if st.session_state.get("book_course") not in course_options:  # course got removed
            st.session_state.pop("book_course", None)
        query = st.session_state.get("book_search", "")
        course_filter = st.session_state.get("book_course")
        teachers = self.manager.search_teachers(query, course_filter)
        already_requested = {b.slot_id for b in self.user.view_dashboard(self.manager)}
        open_by_teacher = (self.manager.open_slots_by_teacher([t.id for t in teachers])  # one request
                           if teachers else {})
        self.page_header()

        c1, c2 = st.columns([2, 1])
        c1.text_input("Search teachers", placeholder="Name, email, or course", key="book_search")
        c2.selectbox(
            "Course", course_options, key="book_course",
            format_func=lambda cid: "All courses" if cid is None else courses[cid].label,
        )

        if not teachers:
            st.info("No teachers match your search.")
            return

        for teacher in teachers:
            self._render_teacher(teacher, courses, course_filter, already_requested,
                                 open_by_teacher.get(teacher.id, []))

    def _render_teacher(self, teacher: Teacher, courses, course_filter, already_requested,
                        open_slots) -> None:
        teacher_courses = sorted((courses[c] for c in teacher.course_ids if c in courses),
                                 key=lambda c: c.code)
        slots = [s for s in open_slots if s.id not in already_requested]

        with card(f"teacher_{teacher.id}"):
            st.markdown(f"#### {md(teacher.name)}")
            st.caption(teacher.email)
            st.markdown(" · ".join(md(c.label) for c in teacher_courses) or "_No courses listed_")
            if not slots:
                st.caption("No open schedules right now. Check back later.")
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
