"""Queue&A: Teacher-Student Consultation Booking System.

Run with:  streamlit run app.py
"""

from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="Queue&A", page_icon="🗓️", layout="wide")

from core import timeutil  # noqa: E402
from core.auth import AuthManager  # noqa: E402
from core.datastore import SupabaseDataStore  # noqa: E402
from core.manager import BookingManager  # noqa: E402
from core.models import QueueAError  # noqa: E402
from ui.login import LoginScreen  # noqa: E402
from ui.views import BaseView  # noqa: E402

SETUP_HELP = """
**Queue&A isn't connected to Supabase yet.**

1. Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`.
2. Fill in your Supabase **Project URL** and **service_role key**
   (Supabase Dashboard → Project Settings → API).
3. Run `supabase/schema.sql` once in the Supabase SQL Editor.
4. Restart the app.
"""


def _read_settings() -> tuple[str, str, str | None]:
    try:
        supabase = st.secrets["supabase"]
        url, key = str(supabase["url"]).strip(), str(supabase["key"]).strip()
    except Exception:
        st.error(SETUP_HELP)
        st.stop()
    if not url or not key or "YOUR-PROJECT" in url:
        st.error(SETUP_HELP)
        st.stop()
    try:
        tz_name = st.secrets.get("app", {}).get("timezone")
    except Exception:
        tz_name = None
    return url, key, tz_name


@st.cache_resource(show_spinner=False)
def _connect(url: str, key: str) -> SupabaseDataStore:
    # One Supabase client for the whole server, shared by every session.
    return SupabaseDataStore.connect(url, key)


def main() -> None:
    url, key, tz_name = _read_settings()
    timeutil.configure(tz_name)
    store = _connect(url, key)
    auth = AuthManager(store)
    manager = BookingManager(store)

    user = None
    user_id = st.session_state.get("user_id")
    if user_id:
        user = auth.get_user(user_id)
        if user is None:  # account was deleted while logged in
            st.session_state.clear()

    if user is None:
        LoginScreen(auth, manager).render()
    else:
        BaseView.for_user(user, manager).render()


try:
    main()
except QueueAError as exc:
    st.error(str(exc))
