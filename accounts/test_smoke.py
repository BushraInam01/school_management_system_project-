from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from academics.models import AcademicYear, ClassSubject, Classroom, Subject
from accounts.models import ParentProfile, StudentProfile, TeacherProfile, User
from fees.models import FeePayment, FeeStructure
from grades.models import Exam
from homework.models import Homework, Submission
from timetable.models import TimeSlot, TimetableEntry


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class RoleUrlSmokeTests(TestCase):
    """Every named application URL is exercised as every supported role."""
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo_data", verbosity=0)

    def test_all_application_urls_return_a_handled_response_for_each_role(self):
        student = StudentProfile.objects.order_by("pk").first()
        other_student = StudentProfile.objects.exclude(pk=student.pk).first()
        classroom, subject, assignment = Classroom.objects.first(), Subject.objects.first(), ClassSubject.objects.first()
        year, teacher = AcademicYear.objects.first(), TeacherProfile.objects.first()
        slot, entry = TimeSlot.objects.first(), TimetableEntry.objects.first()
        exam = Exam.objects.first()
        structure, payment = FeeStructure.objects.first(), FeePayment.objects.first()
        targets = [
            reverse("dashboard:home"), reverse("login"), reverse("logout"), "/admin/",
            reverse("academics:student_list"), reverse("academics:student_create"), reverse("academics:student_update", args=[student.pk]), reverse("academics:student_delete", args=[student.pk]),
            reverse("academics:teacher_list"), reverse("academics:teacher_create"), reverse("academics:teacher_update", args=[teacher.pk]), reverse("academics:teacher_delete", args=[teacher.pk]),
            reverse("academics:parent_list"), reverse("academics:parent_create"), reverse("academics:parent_update", args=[ParentProfile.objects.first().pk]), reverse("academics:parent_delete", args=[ParentProfile.objects.first().pk]),
            reverse("academics:classroom_list"), reverse("academics:classroom_create"), reverse("academics:classroom_update", args=[classroom.pk]), reverse("academics:classroom_delete", args=[classroom.pk]),
            reverse("academics:subject_list"), reverse("academics:subject_create"), reverse("academics:subject_update", args=[subject.pk]), reverse("academics:subject_delete", args=[subject.pk]),
            reverse("academics:classsubject_list"), reverse("academics:classsubject_create"), reverse("academics:classsubject_update", args=[assignment.pk]), reverse("academics:classsubject_delete", args=[assignment.pk]),
            reverse("academics:academicyear_list"), reverse("academics:academicyear_create"), reverse("academics:academicyear_update", args=[year.pk]), reverse("academics:academicyear_delete", args=[year.pk]),
            reverse("academics:students"), reverse("timetable:grid"), reverse("timetable:slot_list"), reverse("timetable:slot_create"), reverse("timetable:slot_update", args=[slot.pk]), reverse("timetable:slot_delete", args=[slot.pk]), reverse("timetable:entry_list"), reverse("timetable:entry_create"), reverse("timetable:entry_update", args=[entry.pk]), reverse("timetable:entry_delete", args=[entry.pk]),
            reverse("attendance:mark"), reverse("attendance:my_report"), reverse("attendance:report", args=[student.pk]), reverse("attendance:class_report", args=[classroom.pk]),
            reverse("grades:list"), reverse("grades:entry"), reverse("grades:remarks", args=[student.pk, exam.pk]), reverse("grades:report", args=[student.pk, exam.pk]), reverse("grades:report_pdf", args=[student.pk, exam.pk]),
            reverse("homework:list"), reverse("homework:create"),
            reverse("fees:list"), reverse("fees:summary"), reverse("fees:structure_list"), reverse("fees:structure_create"), reverse("fees:structure_edit", args=[structure.pk]), reverse("fees:structure_delete", args=[structure.pk]), reverse("fees:payment_create"), reverse("fees:student", args=[student.pk]), reverse("fees:receipt", args=[payment.pk]), reverse("fees:receipt_pdf", args=[payment.pk]),
        ]
        role_users = [User.objects.get(username="admin"), Homework.objects.first().created_by, User.objects.get(username="student1"), User.objects.get(username="parent1")]
        for user in role_users:
            self.client.force_login(user)
            homework = Homework.objects.filter(created_by=user).first() or Homework.objects.filter(classroom=student.classroom).first() or Homework.objects.first()
            submission = Submission.objects.filter(homework=homework).first()
            homework_targets = [reverse("homework:edit", args=[homework.pk]), reverse("homework:delete", args=[homework.pk]), reverse("homework:submit", args=[homework.pk]), reverse("homework:tracking", args=[homework.pk])]
            if submission: homework_targets.append(reverse("homework:review", args=[homework.pk, submission.pk]))
            for target in targets + homework_targets:
                with self.subTest(role=user.role, url=target):
                    self.assertIn(self.client.get(target).status_code, (200, 302, 403, 404))
