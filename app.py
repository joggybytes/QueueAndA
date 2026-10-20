from __future__ import annotations

from pathlib import Path

import streamlit as st  # pyright: ignore[reportMissingImports]

# tab icon, its the symbol from the logo
_TAB_ICON = Path(__file__).resolve().parent / "assets" / "queue_a_icon.png"

st.set_page_config(page_title="Queue&A", page_icon=str(_TAB_ICON), layout="wide")

from utils import timeutil
from controllers.auth_controller import AuthManager
from models.cached_datastore import CachingDataStore, SharedCache
from models.datastore import SupabaseDataStore
from controllers.booking_controller import BookingManager
from models.errors import QueueAError
from views.common import apply_theme
from views.login_view import LoginScreen
from views.base_view import BaseView

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
    # one supabase client for the whole server
    return SupabaseDataStore.connect(url, key)


@st.cache_resource(show_spinner=False)
def _shared_cache() -> SharedCache:
    # courses and teachers are shared for 30 secs so we dont fetch them all the time
    return SharedCache(ttl=30.0)


def main() -> None:
    apply_theme()
    url, key, tz_name = _read_settings()
    timeutil.configure(tz_name)
    # new cache every page load so nothing gets fetched twice
    store = CachingDataStore(_connect(url, key), _shared_cache())
    auth = AuthManager(store)
    manager = BookingManager(store)

    user = None
    user_id = st.session_state.get("user_id")
    if user_id:
        user = auth.get_user(user_id)
        if user is None:  # account got deleted while logged in
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
