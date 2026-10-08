"""Small helpers shared by every screen."""

from __future__ import annotations

import re
from typing import Callable

import streamlit as st

from core.models import BookingStatus, QueueAError

STATUS_ICONS = {
    BookingStatus.PENDING: "🟡",
    BookingStatus.CONFIRMED: "🟢",
    BookingStatus.DECLINED: "🔴",
    BookingStatus.COMPLETED: "🔵",
    BookingStatus.CANCELLED: "⚪",
}

_MD_SPECIAL = re.compile(r"([\\`*_{}\[\]()#+\-!|<>~$])")


def md(text: str | None) -> str:
    """Escape user-typed text so Markdown/LaTeX characters show literally."""
    return _MD_SPECIAL.sub(r"\\\1", text or "")


def status_badge(status: BookingStatus) -> str:
    return f"{STATUS_ICONS.get(status, '')} **{status.value}**"


# ---- button theme -----------------------------------------------------
# Buttons use the green primary colour from .streamlit/config.toml. Buttons
# for "negative" actions (Cancel, Decline, Remove) are placed inside a keyed
# container (CSS class "st-key-qared_…") and this stylesheet makes them red.
_RED = "#dc2626"
_RED_DARK = "#b91c1c"

THEME_CSS = f"""
<style>
[class*="st-key-qared"] button {{
    background-color: {_RED} !important;
    border-color: {_RED} !important;
    color: #ffffff !important;
}}
[class*="st-key-qared"] button:hover,
[class*="st-key-qared"] button:active {{
    background-color: {_RED_DARK} !important;
    border-color: {_RED_DARK} !important;
    color: #ffffff !important;
}}
[class*="st-key-qared"] button:focus-visible {{
    box-shadow: 0 0 0 0.2rem rgba(220, 38, 38, 0.4) !important;
}}
[class*="st-key-qared"] button p {{
    color: #ffffff !important;
}}
[class*="st-key-qaend"],
[class*="st-key-qaend"] [data-testid="stMarkdownContainer"],
[class*="st-key-qaend"] [data-testid="stCaptionContainer"] {{
    text-align: right;
}}
[class*="st-key-qared"] button:disabled {{
    opacity: 0.45 !important;
    cursor: not-allowed !important;
}}
</style>
"""


def apply_theme() -> None:
    st.markdown(THEME_CSS, unsafe_allow_html=True)


# Streamlit keeps the sidebar panel open after a rerun even when nothing is
# drawn in it, so after logging out an empty sidebar would remain on the
# login screen. This stylesheet is only added while the login screen is
# shown; the sidebar returns automatically once someone logs in.
HIDE_SIDEBAR_CSS = """
<style>
section[data-testid="stSidebar"],
[data-testid="stSidebarCollapsedControl"],
[data-testid="stExpandSidebarButton"],
[data-testid="stSidebarCollapseButton"] {
    display: none !important;
}
</style>
"""


def hide_sidebar() -> None:
    st.markdown(HIDE_SIDEBAR_CSS, unsafe_allow_html=True)


def red_button_area(action: str, item_id: str):
    """Container whose buttons are styled red (Cancel, Decline, Remove).

    ``action`` + ``item_id`` keep the container key unique on the page. The
    container is only as wide as its button, so it follows the alignment of
    whatever it is placed in (e.g. ``end_aligned``).
    """
    return st.container(key=f"qared_{action}_{item_id}", width="content")


def end_aligned(parent, key: str):
    """A container inside ``parent`` whose buttons, badges and captions line
    up on the right-hand edge of the box."""
    return parent.container(key=f"qaend_{key}", horizontal_alignment="right")


# ---- flash messages that survive st.rerun() ---------------------------

def flash(message: str, kind: str = "success") -> None:
    st.session_state["_flash"] = (kind, message)


def show_flash() -> None:
    kind, message = st.session_state.pop("_flash", (None, None))
    if message:
        getattr(st, kind, st.info)(message)


# ---- form keys that reset after a successful action -------------------

def form_key(name: str) -> str:
    """Return a form key that changes after each successful action, so the
    form comes back empty instead of keeping the last values typed."""
    return f"{name}_{st.session_state.get('_form_nonce', 0)}"


def bump_forms() -> None:
    """Make every form on the page start empty on the next run."""
    st.session_state["_form_nonce"] = st.session_state.get("_form_nonce", 0) + 1


def run_action(action: Callable[[], object], success_message: str) -> None:
    """Run a business action; show friendly errors, or flash + rerun on success."""
    try:
        action()
    except QueueAError as exc:
        st.error(str(exc))
        return
    bump_forms()
    flash(success_message)
    st.rerun()
