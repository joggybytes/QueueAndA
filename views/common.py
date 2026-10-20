from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

import streamlit as st

from models.booking import BookingStatus
from models.errors import QueueAError

STATUS_ICONS = {
    BookingStatus.PENDING: "🟡",
    BookingStatus.CONFIRMED: "🟢",
    BookingStatus.DECLINED: "🔴",
    BookingStatus.COMPLETED: "🔵",
    BookingStatus.CANCELLED: "⚪",
}

_MD_SPECIAL = re.compile(r"([\\`*_{}\[\]()#+\-!|<>~$])")


def md(text: str | None) -> str:
    """escape text so markdown doesnt mess it up"""
    return _MD_SPECIAL.sub(r"\\\1", text or "")


def status_badge(status: BookingStatus) -> str:
    return f"{STATUS_ICONS.get(status, '')} **{status.value}**"


# logo
ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
LOGO_SIDEBAR = ASSETS_DIR / "queue_a_logo.png"       # white logo for the sidebar
LOGO_FULL = ASSETS_DIR / "queue_a_logo_full.png"     # dark logo for the login screen


# theme stuff that config.toml cant do (red menu, cards, red buttons)
_RED = "#a00000"        # red
_RED_DARK = "#7a0000"
_CHARCOAL = "#262626"
_BORDER = "#cdcdcd"
_SIDE_PAD = "1.25rem"
_NAV_INSET = "0.5rem"     # space around the menu highlight
_SIDEBAR_LINE = "#3d3d3d"   # same as config.toml

THEME_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&display=swap');

/* sidebar menu, current page is red */
[data-testid="stSidebarContent"] {{
    padding-left: 0 !important;
    padding-right: 0 !important;
}}
[data-testid="stSidebarHeader"],
[data-testid="stSidebarUserContent"] {{
    padding-left: {_SIDE_PAD} !important;
    padding-right: {_SIDE_PAD} !important;
}}
[data-testid="stSidebarNavItems"] {{
    padding: 0 !important;
}}
[data-testid="stSidebarNavLink"] {{
    /* a bit rounded */
    border-radius: 6px !important;
    margin: 0.1rem {_NAV_INSET} !important;
    padding: 0.6rem calc({_SIDE_PAD} - {_NAV_INSET}) !important;
    background-color: transparent !important;
}}
[data-testid="stSidebarNavLink"],
[data-testid="stSidebarNavLink"] * {{
    color: #ffffff !important;
}}
[data-testid="stSidebarNavLink"]:hover {{
    background-color: #3a3a3a !important;
}}
[data-testid="stSidebarNavLink"][aria-current="page"],
[data-testid="stSidebarNavLink"][aria-current="page"]:hover {{
    background-color: {_RED} !important;
}}
[data-testid="stSidebarNavLink"][aria-current="page"] span {{
    font-weight: 700 !important;
}}

/* no logo on top when sidebar is closed */
[data-testid="stHeaderLogo"],
[data-testid="stLogoLink"]:has([data-testid="stHeaderLogo"]) {{
    display: none !important;
}}

/* sidebar logo centered, close button on the top right */
[data-testid="stSidebarHeader"] {{
    position: relative !important;
    height: auto !important;
    justify-content: center !important;
    padding-top: 1.25rem !important;
    padding-bottom: 1rem !important;
    margin-bottom: 0.75rem !important;
    /* line under the logo */
    border-bottom: 1px solid {_SIDEBAR_LINE};
}}
[data-testid="stSidebarLogo"] {{
    height: 6rem !important;
    max-height: 6rem !important;
    width: auto !important;
    object-position: center !important;
}}
[data-testid="stSidebarCollapseButton"] {{
    position: absolute !important;
    top: 0.5rem;
    right: 0.5rem;
}}

/* small spinner insted of running/stop */
[data-testid="stStatusWidget"]:has([data-testid="stStatusWidgetRunningIcon"]) > * {{
    display: none !important;
}}
[data-testid="stStatusWidget"]:has([data-testid="stStatusWidgetRunningIcon"])::after {{
    content: "";
    display: block;
    width: 1.1rem;
    height: 1.1rem;
    margin-right: 0.75rem;
    border: 2.5px solid {_BORDER};
    border-top-color: {_RED};
    border-radius: 50%;
    animation: qa-spin 0.7s linear infinite;
}}
@keyframes qa-spin {{
    to {{ transform: rotate(360deg); }}
}}
@media (prefers-reduced-motion: reduce) {{
    [data-testid="stStatusWidget"]:has([data-testid="stStatusWidgetRunningIcon"])::after {{
        animation-duration: 2s;
    }}
}}

/* make the student/teacher choice red */
.st-key-signup_role [data-testid="stRadioOption"][data-selected] > div > div:first-child,
.st-key-signup_role [data-selected] [data-testid="stRadioOption"] > div > div:first-child {{
    background-color: {_RED} !important;
    border-color: {_RED} !important;
}}
.st-key-signup_role [data-testid="stRadioOption"][data-hovered] > div > div:first-child {{
    border-color: {_RED} !important;
}}

/* page titles */
[data-testid="stMain"] h1,
[data-testid="stMain"] h2 {{
    font-family: 'Source Serif 4', Georgia, 'Times New Roman', serif !important;
    font-weight: 400 !important;
    color: {_CHARCOAL} !important;
}}
[data-testid="stMain"] h2 {{
    border-bottom: 1px solid {_BORDER};
    padding-bottom: 0.75rem !important;   /* space above the line */
    margin-bottom: 1rem !important;       /* space below the line */
}}

/* white cards */
[class*="st-key-qacard"],
[data-testid="stForm"],
[data-testid="stMetric"] {{
    background-color: #ffffff !important;
}}
[data-testid="stMetric"] {{
    border: 1px solid {_BORDER};
    border-radius: 4px;
    padding: 0.75rem 1rem;
}}

/* red buttons */
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
    box-shadow: 0 0 0 0.2rem rgba(160, 0, 0, 0.4) !important;
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


# hides the sidebar on the login screen, it stays open after logout otherwise
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
    """container with red buttons"""
    return st.container(key=f"qared_{action}_{item_id}", width="content")


def card(key: str):
    """white card, key has to be unique"""
    return st.container(border=True, key=f"qacard_{key}")


def end_aligned(parent, key: str):
    """puts stuff on the right side of the box"""
    return parent.container(key=f"qaend_{key}", horizontal_alignment="right")


# flash messages

def flash(message: str, kind: str = "success") -> None:
    st.session_state["_flash"] = (kind, message)


def show_flash() -> None:
    kind, message = st.session_state.pop("_flash", (None, None))
    if message:
        getattr(st, kind, st.info)(message)


# form keys

def form_key(name: str) -> str:
    """form key that changes after saving so the form clears"""
    return f"{name}_{st.session_state.get('_form_nonce', 0)}"


def bump_forms() -> None:
    """clears the forms next run"""
    st.session_state["_form_nonce"] = st.session_state.get("_form_nonce", 0) + 1


def run_action(action: Callable[[], object], success_message: str) -> None:
    """runs an action, shows error or success"""
    try:
        action()
    except QueueAError as exc:
        st.error(str(exc))
        return
    bump_forms()
    flash(success_message)
    st.rerun()
