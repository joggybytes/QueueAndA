"""Login and sign-up (AuthManager)."""

from __future__ import annotations

import re

from core.datastore import DataStore
from core.models import AuthError, Course, Student, Teacher, User, ValidationError

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AuthManager:
    """Hides the details of checking credentials and creating accounts."""

    ROLES = {Teacher.ROLE: Teacher, Student.ROLE: Student}

    def __init__(self, store: DataStore):
        self._store = store

    def login(self, email: str, password: str) -> User:
        email = (email or "").strip().lower()
        if not email or not password:
            raise AuthError("Enter your email and password.")
        user = self._store.get_user_by_email(email)
        # Same message for "no such user" and "wrong password" so the login
        # screen doesn't reveal which emails are registered.
        if user is None or not user.verify_password(password):
            raise AuthError("Incorrect email or password.")
        return user

    def register(self, *, name: str, email: str, password: str, confirm_password: str,
                 role: str, course_ids: list[str] | None = None,
                 new_course_code: str = "", new_course_title: str = "") -> User:
        user_cls = self.ROLES.get(role)
        if user_cls is None:
            raise ValidationError("Choose whether you are a teacher or a student.")

        email = (email or "").strip().lower()
        if not _EMAIL.match(email):
            raise ValidationError("Enter a valid email address.")
        if password != confirm_password:
            raise ValidationError("The passwords don't match.")

        user = user_cls(name=name, email=email)
        user.set_password(password)  # validates length and hashes it

        if self._store.get_user_by_email(email) is not None:
            raise AuthError("An account with this email already exists. Log in instead.")

        course_ids = list(course_ids or [])
        if isinstance(user, Teacher):
            if new_course_code.strip() or new_course_title.strip():
                course_ids.append(self._get_or_create_course(new_course_code, new_course_title).id)
            if not course_ids:
                raise ValidationError("Select at least one course that you handle.")
        else:
            course_ids = []

        return self._store.add_user(user, course_ids)

    def get_user(self, user_id: str) -> User | None:
        return self._store.get_user(user_id)

    def _get_or_create_course(self, code: str, title: str) -> Course:
        course = Course(code, title)  # validates both fields
        existing = self._store.get_course_by_code(course.code)
        return existing or self._store.add_course(course)
