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


def run_action(action: Callable[[], object], success_message: str) -> None:
    """Run a business action; show friendly errors, or flash + rerun on success."""
    try:
        action()
    except QueueAError as exc:
        st.error(str(exc))
        return
    st.session_state["_form_nonce"] = st.session_state.get("_form_nonce", 0) + 1
    flash(success_message)
    st.rerun()
