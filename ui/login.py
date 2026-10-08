from __future__ import annotations

import streamlit as st

from core.auth import AuthManager
from core.manager import BookingManager
from core.models import QueueAError, User
from ui.common import flash, hide_sidebar, show_flash


class LoginScreen:
    def __init__(self, auth: AuthManager, manager: BookingManager):
        self._auth = auth
        self._manager = manager

    @staticmethod
    def start_session(user: User) -> None:
        for key in list(st.session_state.keys()):
            if key != "_flash":
                del st.session_state[key]
        st.session_state["user_id"] = user.id

    def render(self) -> None:
        hide_sidebar()  # no menu before login (also clears the leftover panel after logout)
        _, center, _ = st.columns([1, 1.4, 1])
        with center:
            st.title("Queue&A")
            st.caption("Book and manage consultations with your teachers on one platform.")
            show_flash()
            login_tab, signup_tab = st.tabs(["Log in", "Sign up"])
            with login_tab:
                self._render_login()
            with signup_tab:
                self._render_signup()

    # ------------------------------------------------------------------
    def _render_login(self) -> None:
        with st.form("login_form"):
            email = st.text_input("Email", placeholder="email@mcm.edu.ph")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Log in", type="primary")
        if submitted:
            try:
                user = self._auth.login(email, password)
            except QueueAError as exc:
                st.error(str(exc))
                return
            self.start_session(user)
            flash("You're logged in.")
            st.rerun()

    def _render_signup(self) -> None:
        role_label = st.radio("I am a", ["Student", "Teacher"], horizontal=True, key="signup_role")
        is_teacher = role_label == "Teacher"

        courses = self._manager.list_courses() if is_teacher else []
        course_labels = {c.id: c.label for c in courses}

        with st.form("signup_form"):
            name = st.text_input("Full name", placeholder="e.g. Cesar Leonardo M. Europa")
            email = st.text_input("Email", placeholder="email@mcm.edu.ph", key="signup_email")
            password = st.text_input("Password", type="password", help="At least 8 characters.",
                                     key="signup_password")
            confirm = st.text_input("Confirm password", type="password")

            course_ids: list[str] = []
            new_code = new_title = ""
            if is_teacher:
                st.markdown("**Courses you handle**")
                course_ids = st.multiselect("Select your courses", list(course_labels),
                                            format_func=course_labels.get,
                                            placeholder="Choose one or more courses")
                st.caption("Not in the list? Add it here:")
                col_code, col_title = st.columns([1, 2])
                new_code = col_code.text_input("Course code", placeholder="CS101")
                new_title = col_title.text_input("Course title", placeholder="Introduction to Computer Systems")

            submitted = st.form_submit_button("Create account", type="primary")

        if submitted:
            try:
                user = self._auth.register(
                    name=name, email=email, password=password, confirm_password=confirm,
                    role=role_label.lower(), course_ids=course_ids,
                    new_course_code=new_code, new_course_title=new_title,
                )
            except QueueAError as exc:
                st.error(str(exc))
                return
            self.start_session(user)
            flash(f"Your {user.role} account is ready.")
            st.rerun()
