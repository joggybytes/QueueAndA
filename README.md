# Queue&A

A teacher-student consultation booking system built with **Python (OOP)**, **Streamlit**, and **Supabase**.

- **Login screen:** log in or sign up as a Teacher or a Student.
- **Teacher end:** Dashboard (ongoing bookings), Publish Availability, Booking Requests (accept with a meeting link, or decline), Consultation History.
- **Student end:** Dashboard (ongoing bookings), Book a Consultation (search teachers, pick a schedule and course, write a short purpose), Consultation History.

---

## 1. Set up Supabase

1. Create a free project at <https://supabase.com>.
2. Open **SQL Editor → New query**, paste the whole contents of `supabase/schema.sql`, and click **Run**.
   This creates the tables, the rules that prevent double-booking, and a few starter courses.
3. Open **Project Settings → API Keys** and copy:
   - the **Project URL** (e.g. `https://abcd1234.supabase.co`)
   - the **secret key** (`sb_secret_...`) or, on older projects, the legacy **service_role** key.

> The app runs on the server, so the secret key is never sent to the browser. Row Level Security is on with no policies, so the public anon/publishable key cannot read anything.

## 2. Run the app

```bash
cd queue_a
python -m venv .venv
# Windows: .venv\Scripts\activate     macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

# Add your Supabase details
copy .streamlit\secrets.toml.example .streamlit\secrets.toml     # Windows
cp .streamlit/secrets.toml.example .streamlit/secrets.toml       # macOS/Linux
# then edit .streamlit/secrets.toml with your URL and key

streamlit run app.py
```

The app opens at <http://localhost:8501>. Sign up one teacher and one student (use two browsers or an incognito window to be both at once) and try the full flow.

## 3. Run the tests

The business rules are tested without Streamlit or Supabase, using an in-memory version of the data store:

```bash
python -m unittest discover tests
```

---

## How the code maps to the conceptual framework

| Framework class | File | What it does |
|---|---|---|
| `User` (abstract) | `core/models.py` | ID, name, email, private password hash, `set_password()`, `verify_password()`; abstract `view_dashboard()` / `view_history()` |
| `Teacher`, `Student` | `core/models.py` | Subclasses of `User` that override the dashboard and history methods |
| `AuthManager` | `core/auth.py` | `login()` and `register()` |
| `Course` | `core/models.py` | Course code and title |
| `ScheduleSlot` | `core/models.py` | A published time block; `lock()`, `release()`, `remove()` |
| `Booking` | `core/models.py` | Private status and meeting link; `accept()`, `decline()`, `cancel()`, `complete()` |
| `BookingManager` | `core/manager.py` | All business rules: publishing, validation, slot locking, auto-complete |
| `DataStore` | `core/datastore.py` | Abstract storage interface, with `SupabaseDataStore` as the real implementation |

The screens live in `ui/`: `login.py` is the login screen, and `views.py` holds `BaseView` with its `TeacherView` and `StudentView` subclasses.

### OOP principles in the code

- **Encapsulation:** `User._password_hash`, `Booking._status`, and `Booking._meeting_link` are private. Status is a read-only property and only changes through `accept()`, `decline()`, `cancel()`, and `complete()`, which reject invalid moves (for example, you can't accept a declined request).
- **Inheritance:** `Teacher` and `Student` inherit from `User`, and `TeacherView` and `StudentView` inherit the sidebar and history page from `BaseView`.
- **Polymorphism:** `Teacher.view_dashboard()` returns confirmed consultations, while `Student.view_dashboard()` returns pending and confirmed ones. `app.py` calls `BaseView.for_user(user)` and `view.render()` without checking the role.
- **Abstraction:** `User` and `DataStore` are abstract base classes. `BookingManager` hides validation and locking behind simple methods such as `accept_booking()`.

## Booking rules

- Students can only book **future, open** schedules, and only for a **course that teacher handles**. The purpose (1–200 characters) is required.
- A teacher's schedules can't overlap. Each must be 10 minutes to 4 hours long.
- Several students may request the same schedule. When the teacher **accepts** one, the slot is locked and the other requests are **declined automatically**. The database also enforces "one confirmed booking per slot".
- A student can't hold two active bookings at overlapping times.
- Either side can cancel a pending or confirmed booking. Cancelling a confirmed booking re-opens the schedule.
- A confirmed booking becomes **Completed** once its time has passed. A request the teacher never answered is marked **Cancelled (expired)** when the schedule starts.
- Removing a schedule declines its pending requests. Schedules with a confirmed booking can't be removed until that booking is cancelled.

## Notes

- Passwords are hashed with PBKDF2-SHA256 (200,000 iterations, random salt) before they are stored.
- Login lasts for the browser session. Refreshing the page logs you out, which is normal for Streamlit apps without cookies.
- If you see `Invalid API key` from Supabase, upgrade the client (`pip install -U supabase`) or use the legacy service_role key.
- To deploy on Streamlit Community Cloud, push the folder to GitHub **without** `secrets.toml`, then paste its contents into the app's **Settings → Secrets**.
