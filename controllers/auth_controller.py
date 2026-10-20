from __future__ import annotations

import re
from typing import TYPE_CHECKING

from models.course import Course
from models.datastore import DataStore
from models.errors import AuthError, ConflictError, ValidationError
from models.user import Student, Teacher, User

if TYPE_CHECKING:
    from controllers.booking_controller import BookingManager


_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AuthManager:
    """login and accounts"""

    ROLES = {Teacher.ROLE: Teacher, Student.ROLE: Student}

    def __init__(self, store: DataStore):
        self._store = store

    def login(self, email: str, password: str) -> User:
        email = (email or "").strip().lower()
        if not email or not password:
            raise AuthError("Enter your email and password.")
        user = self._store.get_user_by_email(email)
        # same message so people cant tell which emails exist
        if user is None or user.is_deleted or not user.verify_password(password):
            raise AuthError("Incorrect email or password.")
        return user

    def register(self, *, name: str, email: str, password: str, confirm_password: str,
                 role: str, course_ids: list[str] | None = None,
                 new_courses: list[tuple[str, str]] | None = None,
                 new_course_code: str = "", new_course_title: str = "") -> User:
        """makes a new account"""
        user_cls = self.ROLES.get(role)
        if user_cls is None:
            raise ValidationError("Choose whether you are a teacher or a student.")

        email = (email or "").strip().lower()
        if not _EMAIL.match(email):
            raise ValidationError("Enter a valid email address.")
        if password != confirm_password:
            raise ValidationError("The passwords don't match.")

        user = user_cls(name=name, email=email)
        user.set_password(password)  # checks length and hashes

        if self._store.get_user_by_email(email) is not None:
            raise AuthError("An account with this email already exists. Log in instead.")

        course_ids = list(course_ids or [])
        if isinstance(user, Teacher):
            pairs = list(new_courses or [])
            if new_course_code.strip() or new_course_title.strip():
                pairs.append((new_course_code, new_course_title))
            # check all of them first before saving
            to_add = self._validate_new_courses(pairs)
            if not course_ids and not to_add:
                raise ValidationError("Select at least one course that you handle.")
            for course in to_add:
                course_id = self._get_or_create_course(course).id
                if course_id not in course_ids:
                    course_ids.append(course_id)
        else:
            course_ids = []

        return self._store.add_user(user, course_ids)

    @staticmethod
    def check_new_course(code: str, title: str) -> tuple[str, str]:
        """checks a new course, dosent save it"""
        course = Course(code, title)  # error if something is missing
        return course.code, course.title

    @staticmethod
    def _validate_new_courses(pairs: list[tuple[str, str]]) -> list[Course]:
        """checks the new courses, skips empty rows"""
        courses: list[Course] = []
        seen: set[str] = set()
        for code, title in pairs:
            code, title = (code or "").strip(), (title or "").strip()
            if not code and not title:
                continue
            if not code or not title:
                raise ValidationError("Enter both a course code and a course title for "
                                      f"the new course \u201c{code or title}\u201d.")
            course = Course(code, title)  # checks the code
            if course.code in seen:
                continue
            seen.add(course.code)
            courses.append(course)
        return courses

    def update_profile(self, user: User, *, name: str, email: str,
                       current_password: str = "") -> User:
        """change name or email, needs password"""
        fresh = self._require_active(user)
        if not current_password:
            raise AuthError("Enter your current password to save changes.")
        if not fresh.verify_password(current_password):
            raise AuthError("Incorrect current password.")
        new_email = (email or "").strip().lower()
        email_changed = new_email != fresh.email
        if email_changed:
            if not _EMAIL.match(new_email):
                raise ValidationError("Enter a valid email address.")
            taken = self._store.get_user_by_email(new_email)
            if taken is not None and taken.id != fresh.id:
                raise AuthError("Another account already uses this email.")
        fresh.update_details(name, new_email)  # checks the name
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
        fresh.set_password(new_password)  # checks length and hashes
        self._store.update_user(fresh)

    def _require_active(self, user: User) -> User:
        fresh = self.get_user(user.id)
        if fresh is None:
            raise AuthError("This account no longer exists.")
        return fresh

    def get_user(self, user_id: str) -> User | None:
        """current user or none"""
        user = self._store.get_user(user_id)
        return None if user is None or user.is_deleted else user

    def delete_account(self, user: User, password: str, confirmed: bool,
                       manager: BookingManager) -> None:
        """deletes the account"""
        fresh = self._require_active(user)
        if not confirmed:
            raise ValidationError("Tick the box to confirm that you want to delete your account.")
        if not fresh.verify_password(password or ""):
            raise AuthError("Incorrect password.")
        manager.close_account(fresh)
        self._store.delete_user(fresh)

    def _get_or_create_course(self, course: Course) -> Course:
        """uses the saved course if the code exists, otherwise saves this one"""
        return self._store.get_course_by_code(course.code) or self._store.add_course(course)
