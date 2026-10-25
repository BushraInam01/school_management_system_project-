from datetime import date, time
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from accounts.models import StudentProfile, TeacherProfile, User
from academics.models import AcademicYear, Classroom, ClassSubject, Subject
from fees.models import FeePayment, FeeStructure
from grades.models import Exam
from homework.models import Homework, Submission
from timetable.models import TimeSlot, TimetableEntry


class AdminNamedUrlAccessAuditTests(TestCase):
    """Audit GET access to the named school workflows as the administrator."""

    def setUp(self):
        self.admin = User.objects.create_user("audit-admin", role="admin")
        teacher_user = User.objects.create_user("audit-teacher", role="teacher")
        teacher = TeacherProfile.objects.create(user=teacher_user, employee_id="AUD-T1")
        self.student = StudentProfile.objects.create(
            user=User.objects.create_user("audit-student", role="student"),
            roll_no="AUD-S1", classroom=Classroom.objects.create(name="7", section="A"),
            admission_date=date.today(),
        )
        self.classroom = self.student.classroom
        self.subject = Subject.objects.create(name="English", code="AUD-ENG")
        self.assignment = ClassSubject.objects.create(classroom=self.classroom, subject=self.subject, teacher=teacher)
        self.year = AcademicYear.objects.create(name="Audit Year", start=date(2025, 1, 1), end=date(2027, 1, 1), is_current=True)
        self.exam = Exam.objects.create(name="Audit Exam", academic_year=self.year, term="Term 1", start_date=date.today())
        self.homework = Homework.objects.create(classroom=self.classroom, subject=self.subject, title="Audit HW", description="Task", due_date=date.today(), created_by=self.admin)
        self.submission = Submission.objects.create(homework=self.homework, student=self.student, text="Answer")
        self.fee_structure = FeeStructure.objects.create(classroom=self.classroom, fee_type="Tuition", amount=Decimal("100.00"), academic_year=self.year)
        self.payment = FeePayment.objects.create(student=self.student, fee_structure=self.fee_structure, amount_due=Decimal("100.00"), amount_paid=Decimal("20.00"), method="cash", received_by=self.admin)
        self.slot = TimeSlot.objects.create(day=0, start_time=time(8), end_time=time(9))
        self.entry = TimetableEntry.objects.create(classroom=self.classroom, subject=self.subject, teacher=teacher, timeslot=self.slot)

    def test_admin_can_get_every_named_school_workflow(self):
        self.client.force_login(self.admin)
        urls = [
            reverse("dashboard:home"),
            reverse("attendance:mark"), reverse("attendance:report", args=[self.student.pk]),
            reverse("attendance:class_report", args=[self.classroom.pk]),
            reverse("grades:entry"), reverse("grades:report", args=[self.student.pk, self.exam.pk]),
            reverse("grades:report_pdf", args=[self.student.pk, self.exam.pk]),
            reverse("grades:remarks", args=[self.student.pk, self.exam.pk]),
            reverse("homework:list"), reverse("homework:create"),
            reverse("homework:tracking", args=[self.homework.pk]),
            reverse("homework:submission_detail", args=[self.homework.pk, self.submission.pk]),
            reverse("homework:review", args=[self.homework.pk, self.submission.pk]),
            reverse("fees:list"), reverse("fees:summary"), reverse("fees:student", args=[self.student.pk]),
            reverse("fees:receipt", args=[self.payment.pk]), reverse("fees:receipt_pdf", args=[self.payment.pk]),
            reverse("fees:payment_create"), reverse("fees:structure_list"),
            reverse("fees:structure_create"), reverse("fees:structure_edit", args=[self.fee_structure.pk]),
            reverse("fees:structure_delete", args=[self.fee_structure.pk]),
            reverse("timetable:grid"), reverse("timetable:slot_list"), reverse("timetable:slot_create"),
            reverse("timetable:slot_update", args=[self.slot.pk]), reverse("timetable:slot_delete", args=[self.slot.pk]),
            reverse("timetable:entry_list"), reverse("timetable:entry_create"),
            reverse("timetable:entry_update", args=[self.entry.pk]), reverse("timetable:entry_delete", args=[self.entry.pk]),
        ]
        for resource in ("student", "teacher", "parent", "classroom", "subject", "classsubject", "academicyear"):
            urls.extend((
                reverse(f"academics:{resource}_list"), reverse(f"academics:{resource}_create"),
            ))
        for resource, obj in (("student", self.student), ("classroom", self.classroom), ("subject", self.subject), ("classsubject", self.assignment), ("academicyear", self.year)):
            urls.extend((reverse(f"academics:{resource}_update", args=[obj.pk]), reverse(f"academics:{resource}_delete", args=[obj.pk])))
        teacher = TeacherProfile.objects.get(user__username="audit-teacher")
        urls.extend((reverse("academics:teacher_update", args=[teacher.pk]), reverse("academics:teacher_delete", args=[teacher.pk])))
        from accounts.models import ParentProfile
        parent = ParentProfile.objects.create(user=User.objects.create_user("audit-parent", role="parent"))
        urls.extend((reverse("academics:parent_update", args=[parent.pk]), reverse("academics:parent_delete", args=[parent.pk])))

        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertNotEqual(response.status_code, 403, f"Admin denied access to {url}")
