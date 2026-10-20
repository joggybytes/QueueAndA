from __future__ import annotations

import streamlit as st  # type: ignore[reportMissingImports]

from controllers.auth_controller import AuthManager
from controllers.booking_controller import BookingManager
from models.errors import QueueAError
from models.user import User
from views.common import LOGO_FULL, flash, hide_sidebar, md, show_flash


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
        # load courses first if teacher is picked
        self._signup_courses = (self._manager.list_courses()
                                if st.session_state.get("signup_role") == "Teacher" else [])
        hide_sidebar()  # no sidebar on login
        _, center, _ = st.columns([1, 1.4, 1])
        with center:
            st.image(str(LOGO_FULL), width=220)
            st.caption("Book and manage consultations with your teachers on one platform.")
            show_flash()
            login_tab, signup_tab = st.tabs(["Log in", "Sign up"])
            with login_tab:
                self._render_login()
            with signup_tab:
                self._render_signup()

    # login and sign up
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

        courses = self._signup_courses if is_teacher else []
        course_labels = {c.id: c.label for c in courses}

        with st.form("signup_form"):
            name = st.text_input("Full name", placeholder="e.g. Cesar Leonardo M. Europa")
            email = st.text_input("Email", placeholder="email@mcm.edu.ph", key="signup_email")
            password = st.text_input("Password", type="password", help="At least 8 characters.",
                                     key="signup_password")
            confirm = st.text_input("Confirm password", type="password")

            course_ids: list[str] = []
            new_code = new_title = ""
            add_clicked = False
            removed: int | None = None
            pending: list[tuple[str, str]] = st.session_state.setdefault(_PENDING, [])
            if is_teacher:
                st.markdown("**Courses you handle**")
                course_ids = st.multiselect("Select your courses", list(course_labels),
                                            format_func=course_labels.get,
                                            placeholder="Choose one or more courses")
                st.caption("Not in the list? Add it here. Press **+** to add it and type another.")
                nonce = st.session_state.get(_NONCE, 0)   # changes so the boxes clear after +
                col_code, col_title, col_add = st.columns([1.2, 2, 0.5], vertical_alignment="bottom")
                new_code = col_code.text_input("Course code", placeholder="CS101",
                                               key=f"signup_code_{nonce}")
                new_title = col_title.text_input("Course title",
                                                 placeholder="Introduction to Computer Systems",
                                                 key=f"signup_title_{nonce}")
                # only submit buttons work in forms, handled after the form
                add_clicked = col_add.form_submit_button(":material/add:", key="signup_add_course",
                                                         help="Add this course to your list")
                for i, (code, title) in enumerate(pending):
                    col_label, col_remove = st.columns([8, 1], vertical_alignment="center")
                    col_label.markdown(f"**{md(code)}** – {md(title)}")
                    if col_remove.form_submit_button(":material/close:", key=f"signup_remove_course_{i}",
                                                     type="tertiary", help="Remove this course"):
                        removed = i

            submitted = st.form_submit_button("Create account", type="primary")

        if is_teacher and add_clicked:
            self._add_pending_course(new_code, new_title, pending, courses)
            return
        if is_teacher and removed is not None:
            pending.pop(removed)
            st.rerun()

        if submitted:
            try:
                user = self._auth.register(
                    name=name, email=email, password=password, confirm_password=confirm,
                    role=role_label.lower(), course_ids=course_ids,
                    # list + whatever is still typed
                    new_courses=list(pending) if is_teacher else [],
                    new_course_code=new_code, new_course_title=new_title,
                )
            except QueueAError as exc:
                st.error(str(exc))
                return
            self.start_session(user)
            flash(f"Your {user.role} account is ready.")
            st.rerun()

    @staticmethod
    def _add_pending_course(code: str, title: str, pending: list[tuple[str, str]],
                            existing) -> None:
        """adds the course to the list (saved when the account is made)"""
        if not code.strip() and not title.strip():
            # enter also presses + so ignore empty boxes
            return
        try:
            entry = AuthManager.check_new_course(code, title)
        except QueueAError as exc:
            st.error(str(exc))
            return
        match = next((c for c in existing if c.code == entry[0]), None)
        if match is not None:
            st.error(f"{match.label} is already in the list. Select it under "
                     "\"Select your courses\" instead.")
            return
        if any(c == entry[0] for c, _ in pending):
            st.error(f"{entry[0]} is already on your list.")
            return
        pending.append(entry)
        st.session_state[_NONCE] = st.session_state.get(_NONCE, 0) + 1
        st.rerun()


# courses added with + (not saved untill create account)
_PENDING = "signup_new_courses"
_NONCE = "signup_course_nonce"
