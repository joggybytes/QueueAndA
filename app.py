from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="Queue&A", page_icon="🗓️", layout="wide")

from core import timeutil  
from core.auth import AuthManager  
from core.datastore import SupabaseDataStore  
from core.manager import BookingManager  
from core.models import QueueAError  
from ui.common import apply_theme  
from ui.login import LoginScreen  
from ui.views import BaseView  

def _read_settings() -> tuple[str, str, str | None]:
    try:
        supabase = st.secrets["supabase"]
        url, key = str(supabase["url"]).strip(), str(supabase["key"]).strip()
    except Exception:
        st.stop()
    if not url or not key or "YOUR-PROJECT" in url:
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
    apply_theme()
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
        login = st.Page(LoginScreen(auth, manager).render, title="Log in",
                        icon=":material/login:", url_path="login", default=True)
        st.navigation([login], position="hidden").run()
    else:
        BaseView.for_user(user, manager, auth).render()


try:
    main()
except QueueAError as exc:
    st.error(str(exc))
