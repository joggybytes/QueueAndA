class StudentUser:
    def __init__(self, name: str, student_id: str):
        self._name = name
        self._student_id = student_id

    @property
    def name(self):
        return self._name

class TeacherModel:
    def __init__(self, name: str, department: str, courses: list):
        self.name = name
        self.department = department
        self.courses = courses

# mock teachers for ui
MOCK_TEACHERS = [
    TeacherModel("Teacher1", "Subject1", ["CODE101"]),
    TeacherModel("Teacher2", "Subject2", ["CODE102"]),
    TeacherModel("Teacher3", "Subject3", ["CODE103", "CODE104"]),
    TeacherModel("Teacher5", "Subject4", ["CODE105"]),
    TeacherModel("Teacher6", "Subject4", ["CODE105"]),
    TeacherModel("Teacher7", "Subject4", ["CODE105"]),
    TeacherModel("Teacher8", "Subject4", ["CODE105"]),
    TeacherModel("Teacher9", "Subject4", ["CODE105"]),
    TeacherModel("Teacher10", "Subject4", ["CODE105"]),
]