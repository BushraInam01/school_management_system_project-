from datetime import date

from django.test import TestCase
from django.urls import reverse

from academics.models import Classroom
from accounts.models import ParentProfile, StudentProfile, TeacherProfile, User
from datetime import date
from decimal import Decimal
from academics.models import AcademicYear
from fees.models import FeePayment, FeeStructure


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

    def test_dashboard_fee_totals_match_fee_summary_and_include_unpaid_students(self):
        year = AcademicYear.objects.create(name="2026", start=date(2026, 1, 1), end=date(2026, 12, 31), is_current=True)
        structure = FeeStructure.objects.create(classroom=self.classroom, fee_type="Tuition", amount=5000, academic_year=year)
        admin = User.objects.create_user("feesadmin", role="admin")
        for amount in (2000, 1000):
            FeePayment.objects.create(student=self.student_profile, fee_structure=structure, amount_paid=amount, method=FeePayment.Method.CASH, received_by=admin)
        StudentProfile.objects.create(user=User.objects.create_user("unpaid", role="student"), roll_no="R002", classroom=self.classroom, admission_date=date.today())
        self.client.force_login(admin)
        dashboard = self.client.get(reverse("dashboard:home"))
        summary = self.client.get(reverse("fees:summary"))
        self.assertEqual(dashboard.context["fees"], {"due": Decimal("10000.00"), "collected": Decimal("3000.00"), "pending": Decimal("7000.00")})
        self.assertEqual(summary.context["totals"]["due"], dashboard.context["fees"]["due"])
        self.assertEqual(summary.context["totals"]["paid"], dashboard.context["fees"]["collected"])
        self.assertEqual(summary.context["totals"]["pending"], dashboard.context["fees"]["pending"])
        self.client.force_login(self.student)
        student_dashboard = self.client.get(reverse("dashboard:home"))
        self.assertEqual(student_dashboard.context["fee_dues"], {"due": Decimal("5000.00"), "collected": Decimal("3000.00"), "pending": Decimal("2000.00")})
        self.client.force_login(self.parent)
        parent_dashboard = self.client.get(reverse("dashboard:home"))
        self.assertEqual(parent_dashboard.context["child_cards"][0]["fee_due"], Decimal("2000.00"))
