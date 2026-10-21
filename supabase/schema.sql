-- queue&a database tables
-- run this whole file in supabase: sql editor -> new query
-- its safe to run again, nothing gets deleted

-- users (teachers and students), passwords are hashed not plain text
create table if not exists public.users (
    id             uuid primary key default gen_random_uuid(),
    name           text not null check (char_length(trim(name)) > 0),
    email          text not null unique check (email = lower(email)),
    role           text not null check (role in ('teacher', 'student')),
    password_hash  text not null,
    created_at     timestamptz not null default now(),
    deleted_at     timestamptz            -- set when the account is deleted
);

-- for databases made before deleted_at was added
alter table public.users add column if not exists deleted_at timestamptz;

-- courses and wich teacher handles wich course
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

-- time slots teachers post
-- open = can be booked, booked = accepted, removed = taken down (kept for history)
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

-- bookings
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

-- only one confirmed booking per slot
create unique index if not exists bookings_one_confirmed_per_slot
    on public.bookings (slot_id) where status = 'Confirmed';

-- a student can only request the same slot once
create unique index if not exists bookings_one_active_per_student_slot
    on public.bookings (slot_id, student_id) where status in ('Pending', 'Confirmed');

-- security: blocks the public key, the app uses the service_role key from secrets
alter table public.users           enable row level security;
alter table public.courses         enable row level security;
alter table public.teacher_courses enable row level security;
alter table public.schedule_slots  enable row level security;
alter table public.bookings        enable row level security;

-- no starter courses, teachers add thier own
