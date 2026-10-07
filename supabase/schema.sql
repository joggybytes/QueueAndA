-- =====================================================================
-- Queue&A: Supabase database schema
-- Run this whole file once in Supabase: Dashboard -> SQL Editor -> New query.
-- It is safe to re-run: every statement uses "if not exists" / "on conflict".
-- =====================================================================

-- ---------------------------------------------------------------------
-- Users (teachers and students). Passwords are stored as PBKDF2 hashes,
-- never as plain text (see core/models.py -> User.set_password).
-- ---------------------------------------------------------------------
create table if not exists public.users (
    id             uuid primary key default gen_random_uuid(),
    name           text not null check (char_length(trim(name)) > 0),
    email          text not null unique check (email = lower(email)),
    role           text not null check (role in ('teacher', 'student')),
    password_hash  text not null,
    created_at     timestamptz not null default now()
);

-- ---------------------------------------------------------------------
-- Courses, and which teacher handles which course (many-to-many).
-- ---------------------------------------------------------------------
create table if not exists public.courses (
    id     uuid primary key default gen_random_uuid(),
    code   text not null unique check (code = upper(code)),
    title  text not null
);

create table if not exists public.teacher_courses (
    teacher_id  uuid not null references public.users(id)   on delete cascade,
    course_id   uuid not null references public.courses(id) on delete cascade,
    primary key (teacher_id, course_id)
);

-- ---------------------------------------------------------------------
-- Consultation schedule slots published by teachers.
-- status: open    -> students can request it
--         booked  -> a booking was accepted (locked)
--         removed -> teacher took it down (kept so history stays intact)
-- ---------------------------------------------------------------------
create table if not exists public.schedule_slots (
    id          uuid primary key default gen_random_uuid(),
    teacher_id  uuid not null references public.users(id) on delete cascade,
    start_time  timestamptz not null,
    end_time    timestamptz not null,
    status      text not null default 'open' check (status in ('open', 'booked', 'removed')),
    created_at  timestamptz not null default now(),
    check (end_time > start_time)
);

create index if not exists schedule_slots_teacher_idx on public.schedule_slots (teacher_id, start_time);

-- ---------------------------------------------------------------------
-- Bookings (consultation requests).
-- ---------------------------------------------------------------------
create table if not exists public.bookings (
    id            uuid primary key default gen_random_uuid(),
    student_id    uuid not null references public.users(id) on delete cascade,
    teacher_id    uuid not null references public.users(id) on delete cascade,
    slot_id       uuid not null references public.schedule_slots(id) on delete cascade,
    course_id     uuid not null references public.courses(id),
    purpose       text not null check (char_length(trim(purpose)) between 1 and 200),
    status        text not null default 'Pending'
                  check (status in ('Pending', 'Confirmed', 'Declined', 'Completed', 'Cancelled')),
    meeting_link  text,
    note          text,
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now()
);

create index if not exists bookings_student_idx on public.bookings (student_id);
create index if not exists bookings_teacher_idx on public.bookings (teacher_id);
create index if not exists bookings_slot_idx    on public.bookings (slot_id);

-- Business rule enforced by the database itself:
-- a slot can have only ONE confirmed booking (no double-booking) ...
create unique index if not exists bookings_one_confirmed_per_slot
    on public.bookings (slot_id) where status = 'Confirmed';

-- ... and a student can have only one active request for the same slot.
create unique index if not exists bookings_one_active_per_student_slot
    on public.bookings (slot_id, student_id) where status in ('Pending', 'Confirmed');

-- ---------------------------------------------------------------------
-- Security: turn on Row Level Security with NO policies.
-- This blocks the public "anon" key from reading or writing anything.
-- The Streamlit app runs on the server and connects with the
-- "service_role" key (kept in .streamlit/secrets.toml), which bypasses RLS.
-- ---------------------------------------------------------------------
alter table public.users           enable row level security;
alter table public.courses         enable row level security;
alter table public.teacher_courses enable row level security;
alter table public.schedule_slots  enable row level security;
alter table public.bookings        enable row level security;

-- ---------------------------------------------------------------------
-- Starter courses (teachers can add more when they sign up).
-- ---------------------------------------------------------------------
insert into public.courses (code, title) values
    ('CS101',   'Introduction to Computing'),
    ('CS102',   'Computer Programming 1'),
    ('CS103',   'Computer Programming 2'),
    ('CS201',   'Data Structures and Algorithms'),
    ('CS202',   'Object-Oriented Programming'),
    ('IT201',   'Database Management Systems'),
    ('MATH101', 'Calculus 1'),
    ('ENG101',  'Purposive Communication')
on conflict (code) do nothing;
