from __future__ import annotations

from models.errors import ValidationError


# courses

class Course:
    def __init__(self, code: str, title: str, course_id: str | None = None):
        code = (code or "").strip().upper()
        title = (title or "").strip()
        if not code or not title:
            raise ValidationError("A course needs both a code and a title.")
        if len(code) > 20:
            raise ValidationError("Course code must be 20 characters or fewer.")
        self._id = course_id
        self._code = code
        self._title = title

    @property
    def id(self) -> str | None:
        return self._id

    @property
    def code(self) -> str:
        return self._code

    @property
    def title(self) -> str:
        return self._title

    @property
    def label(self) -> str:
        return f"{self._code} – {self._title}"

    def to_record(self) -> dict:
        record = {"code": self._code, "title": self._title}
        if self._id:
            record["id"] = self._id
        return record

    @classmethod
    def from_record(cls, record: dict) -> Course:
        return cls(record["code"], record["title"], course_id=record.get("id"))

    def __repr__(self) -> str:
        return f"Course({self._code!r})"
