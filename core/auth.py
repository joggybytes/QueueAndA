from __future__ import annotations

import re
from typing import TYPE_CHECKING

from core.datastore import DataStore
from core.models import (AuthError, ConflictError, Course, Student, Teacher, User,
                         ValidationError)

if TYPE_CHECKING:
    from core.manager import BookingManager

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
        if user is None or user.is_deleted or not user.verify_password(password):
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

    def update_profile(self, user: User, *, name: str, email: str,
                       current_password: str = "") -> User:
        """Change name and/or email. Changing the email needs the current password."""
        fresh = self._require_active(user)
        new_email = (email or "").strip().lower()
        email_changed = new_email != fresh.email
        if email_changed:
            if not _EMAIL.match(new_email):
                raise ValidationError("Enter a valid email address.")
            if not current_password:
                raise AuthError("Enter your current password to change your email.")
            if not fresh.verify_password(current_password):
                raise AuthError("Incorrect current password.")
            taken = self._store.get_user_by_email(new_email)
            if taken is not None and taken.id != fresh.id:
                raise AuthError("Another account already uses this email.")
        fresh.update_details(name, new_email)  # validates the name
        try:
            return self._store.update_user(fresh)
        except ConflictError as exc:
            if email_changed:
                raise AuthError("Another account already uses this email.") from exc
            raise

    def change_password(self, user: User, *, current_password: str, new_password: str,
                        confirm_password: str) -> None:
        fresh = self._require_active(user)
        if not fresh.verify_password(current_password or ""):
            raise AuthError("Incorrect current password.")
        if new_password != confirm_password:
            raise ValidationError("The new passwords don't match.")
        if new_password == current_password:
            raise ValidationError("Choose a new password that's different from your current one.")
        fresh.set_password(new_password)  # validates length and hashes it
        self._store.update_user(fresh)

    def _require_active(self, user: User) -> User:
        fresh = self.get_user(user.id)
        if fresh is None:
            raise AuthError("This account no longer exists.")
        return fresh

    def get_user(self, user_id: str) -> User | None:
        """The logged-in user, or None if the account no longer exists."""
        user = self._store.get_user(user_id)
        return None if user is None or user.is_deleted else user

    def delete_account(self, user: User, password: str, confirmed: bool,
                       manager: BookingManager) -> None:
        """Delete the user's own account after re-checking their password."""
        fresh = self.get_user(user.id)
        if fresh is None:
            raise AuthError("This account no longer exists.")
        if not confirmed:
            raise ValidationError("Tick the box to confirm that you want to delete your account.")
        if not fresh.verify_password(password or ""):
            raise AuthError("Incorrect password.")
        manager.close_account(fresh)
        self._store.delete_user(fresh)

    def _get_or_create_course(self, code: str, title: str) -> Course:
        course = Course(code, title)  # validates both fields
        existing = self._store.get_course_by_code(course.code)
        return existing or self._store.add_course(course)
