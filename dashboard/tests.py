from datetime import date

from django.test import TestCase
from django.urls import reverse

from academics.models import Classroom
from accounts.models import ParentProfile, StudentProfile, TeacherProfile, User


class DashboardAndSidebarTests(TestCase):
    def setUp(self):
        self.classroom = Classroom.objects.create(name="6", section="A")
        self.admin = User.objects.create_user("admin", role="admin")
        self.teacher = User.objects.create_user("teacher", role="teacher")
        TeacherProfile.objects.create(user=self.teacher, employee_id="T001")
        self.student = User.objects.create_user("student", role="student")
        self.student_profile = StudentProfile.objects.create(user=self.student, roll_no="R001", classroom=self.classroom, admission_date=date.today())
        self.parent = User.objects.create_user("parent", role="parent")
        parent_profile = ParentProfile.objects.create(user=self.parent)
        self.student_profile.parents.add(parent_profile)

    def response_for(self, user):
        self.client.force_login(user)
        return self.client.get(reverse("dashboard:home"))

    def test_dashboards_are_available_for_every_role(self):
        for user in (self.admin, self.teacher, self.student, self.parent):
            with self.subTest(role=user.role):
                self.assertEqual(self.response_for(user).status_code, 200)

    def test_root_redirects_to_login_or_dashboard(self):
        anonymous = self.client.get("/")
        self.assertRedirects(anonymous, reverse("login"))
        self.client.force_login(self.admin)
        self.assertRedirects(self.client.get("/"), reverse("dashboard:home"))

    def test_login_routes_and_legacy_redirect(self):
        self.assertEqual(self.client.get(reverse("login")).status_code, 200)
        self.assertRedirects(self.client.get("/accounts/login/"), reverse("login"))

    def test_student_without_profile_gets_dashboard_message(self):
        student = User.objects.create_user("unprofiled", role="student")
        response = self.response_for(student)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Your student profile is not set up yet")

    def test_sidebar_links_are_scoped_by_role(self):
        student_content = self.response_for(self.student).content.decode()
        parent_content = self.response_for(self.parent).content.decode()
        teacher_content = self.response_for(self.teacher).content.decode()
        admin_content = self.response_for(self.admin).content.decode()
        self.assertIn("Grades / Report Card", student_content)
        self.assertIn("Grades / Report Card", parent_content)
        self.assertNotIn(">Fees<", teacher_content)
        self.assertNotIn(">Academics<", admin_content)
        for label in ("Students", "Teachers", "Parents", "Classrooms", "Subjects", "Class Subjects", "Academic Years", "Fee Summary", "Attendance Reports"):
            with self.subTest(label=label):
                self.assertIn(f">{label}<", admin_content)
