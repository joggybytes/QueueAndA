"""the screens. importing this also loads the teacher and student views"""

from views.base_view import BaseView, PageSpec
from views.login_view import LoginScreen
from views.student_view import StudentView
from views.teacher_view import TeacherView

__all__ = ["BaseView", "LoginScreen", "PageSpec", "StudentView", "TeacherView"]
