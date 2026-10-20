from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, ClassVar

import streamlit as st  # pyright: ignore[reportMissingImports]

from controllers.auth_controller import AuthManager
from controllers.booking_controller import BookingDetails, BookingManager
from models.booking import BookingStatus
from models.errors import QueueAError
from models.user import User
from utils import timeutil
from views.common import (LOGO_SIDEBAR, card, flash, form_key, md, red_button_area, run_action,
                          show_flash)


@dataclass(frozen=True)
class PageSpec:
    """one item in the sidebar menu"""

    key: str                      # url path
    title: str
    icon: str                     # icon
    render: Callable[[], None]
    badge: int = 0                # number next to the title
    heading: str | None = None    # page title if its diffrent


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
        """picks teacher or student view"""
        return cls._views[type(user)](user, manager, auth)

    # each view fills these in
    @abstractmethod
    def pages(self) -> list[PageSpec]:
        """menu items in order, first one is the home page"""

    @abstractmethod
    def counterpart_label(self) -> str:
        """the other role"""

    @abstractmethod
    def counterpart(self, d: BookingDetails) -> str: ...

    @abstractmethod
    def deletion_summary(self) -> str:
        """what gets deleted with the account"""

    # layout
    STATUS_REFRESH_SECONDS: ClassVar[float] = 60.0

    def render(self) -> None:
        self._refresh_statuses_if_due()

        specs = self.pages() + [
            PageSpec("account", "Account", ":material/manage_accounts:", self.render_account),
        ]
        self._nav_pages = {
            spec.key: st.Page(self._page_runner(spec),
                              title=spec.title + (f" ({spec.badge})" if spec.badge else ""),
                              icon=spec.icon, url_path=spec.key, default=(i == 0))
            for i, spec in enumerate(specs)
        }
        st.logo(str(LOGO_SIDEBAR), size="large")
        current = st.navigation(list(self._nav_pages.values()))

        # no divider here, theres already a line
        with st.sidebar:
            st.markdown(f"**{md(self.user.name)}**  \n{self.user.role_label} · {md(self.user.email)}")
            if st.button("Log out", icon=":material/logout:"):
                self.end_session()

        current.run()

    def _refresh_statuses_if_due(self) -> None:
        """updates old bookings, only once a minute"""
        now = time.monotonic()
        last = st.session_state.get("_status_refreshed_at")
        if last is None or now - last >= self.STATUS_REFRESH_SECONDS:
            self.manager.refresh_statuses(self.user)
            st.session_state["_status_refreshed_at"] = now

    # load everything first then draw so the page shows all at once
    def _page_runner(self, spec: PageSpec) -> Callable[[], None]:
        def run() -> None:
            self._current_spec = spec
            spec.render()
        return run

    def page_header(self) -> None:
        """page title and flash message"""
        spec = self._current_spec
        st.header(spec.heading or spec.title)
        show_flash()

    def end_session(self, message: str | None = None) -> None:
        """log out and go back to the login screen"""
        home = next(iter(self._nav_pages.values()))
        st.session_state.clear()
        if message:
            flash(message)
        st.switch_page(home)

    # account page
    def render_account(self) -> None:
        self.page_header()  # user is already loaded
        with card("account"):
            st.markdown(f"**Name:** {md(self.user.name)}  \n"
                        f"**Email:** {md(self.user.email)}  \n"
                        f"**Role:** {self.user.role_label}")
            if self.user.created_at:
                st.caption(f"Member since {timeutil.fmt_date(self.user.created_at)}")

        st.subheader("Edit profile")
        with st.form(form_key("edit_profile")):
            name = st.text_input("Full name", value=self.user.name)
            email = st.text_input("Email", value=self.user.email)
            current = st.text_input("Enter your password to save changes", type="password")
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
        """go to another page"""
        st.switch_page(self._nav_pages[key])

    def render_history(self) -> None:
        history = self.manager.details(self.user.view_history(self.manager), newest_first=True)
        self.page_header()
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
