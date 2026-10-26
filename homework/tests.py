from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.files.storage import default_storage
from django.test import override_settings
from tempfile import TemporaryDirectory
from django.test import TestCase
from django.urls import reverse

from accounts.models import ParentProfile, StudentProfile, TeacherProfile, User
from academics.models import Classroom, ClassSubject, Subject
from .forms import HomeworkForm, SubmissionForm
from .models import Homework, Submission


class HomeworkWorkflowTests(TestCase):
    def setUp(self):
        self.teacher_user = User.objects.create_user("teacher", role="teacher")
        self.teacher = TeacherProfile.objects.create(user=self.teacher_user, employee_id="T1")
        self.other_teacher_user = User.objects.create_user("other-teacher", role="teacher")
        self.other_teacher = TeacherProfile.objects.create(user=self.other_teacher_user, employee_id="T2")
        self.classroom = Classroom.objects.create(name="8", section="A")
        self.other_classroom = Classroom.objects.create(name="8", section="B")
        self.subject = Subject.objects.create(name="Math", code="MATH")
        ClassSubject.objects.create(classroom=self.classroom, subject=self.subject, teacher=self.teacher)
        ClassSubject.objects.create(classroom=self.other_classroom, subject=self.subject, teacher=self.other_teacher)
        self.first = StudentProfile.objects.create(user=User.objects.create_user("first", role="student"), roll_no="R1", classroom=self.classroom, admission_date=date.today())
        self.second = StudentProfile.objects.create(user=User.objects.create_user("second", role="student"), roll_no="R2", classroom=self.classroom, admission_date=date.today())
        self.homework = Homework.objects.create(classroom=self.classroom, subject=self.subject, title="Algebra", description="Solve", due_date=date.today() + timedelta(days=1), created_by=self.teacher_user)

    def test_late_detection_after_due_date(self):
        overdue = Homework.objects.create(classroom=self.classroom, subject=self.subject, title="Old", description="Solve", due_date=date.today() - timedelta(days=1), created_by=self.teacher_user)
        submission = Submission.objects.create(homework=overdue, student=self.first, text="done")
        self.assertEqual(submission.status, Submission.Status.LATE)

    def test_lateness_uses_local_submission_date(self):
        due = date(2026, 1, 1)
        homework = Homework.objects.create(classroom=self.classroom, subject=self.subject, title="Local deadline", description="Solve", due_date=due, created_by=self.teacher_user)
        next_day_early = Submission.objects.create(homework=homework, student=self.first, text="done", submitted_at=datetime(2026, 1, 2, 2, 0, tzinfo=ZoneInfo("Asia/Karachi")))
        due_day_late = Submission.objects.create(homework=homework, student=self.second, text="done", submitted_at=datetime(2026, 1, 1, 23, 30, tzinfo=ZoneInfo("Asia/Karachi")))
        self.assertEqual(next_day_early.status, Submission.Status.LATE)
        self.assertEqual(due_day_late.status, Submission.Status.SUBMITTED)

    def test_upload_rejects_bad_extension_and_oversize_file(self):
        bad = SimpleUploadedFile("answer.exe", b"data")
        form = SubmissionForm(data={"text": ""}, files={"file": bad}, instance=Submission(homework=self.homework, student=self.first))
        self.assertFalse(form.is_valid())
        huge = SimpleUploadedFile("answer.pdf", b"x" * (5 * 1024 * 1024 + 1))
        assignment = ClassSubject.objects.get(classroom=self.classroom, subject=self.subject)
        form = HomeworkForm(data={"class_subject": assignment.pk, "title": "Large", "description": "x", "due_date": date.today()}, files={"attachment": huge}, teacher=self.teacher)
        self.assertFalse(form.is_valid())

    def test_resubmission_allowed_before_review_and_blocked_after_review(self):
        url = reverse("homework:submit", args=[self.homework.pk])
        self.client.force_login(self.first.user)
        self.assertEqual(self.client.post(url, {"text": "first"}).status_code, 302)
        self.assertEqual(self.client.post(url, {"text": "second"}).status_code, 302)
        submission = Submission.objects.get(homework=self.homework, student=self.first)
        self.assertEqual(submission.text, "second")
        submission.status = Submission.Status.REVIEWED
        submission.save()
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_teacher_cannot_edit_another_teachers_homework(self):
        self.client.force_login(self.other_teacher_user)
        self.assertEqual(self.client.get(reverse("homework:edit", args=[self.homework.pk])).status_code, 403)

    def test_admin_has_full_homework_workflow_access(self):
        admin = User.objects.create_user("hw-admin", role="admin")
        assignment = ClassSubject.objects.get(classroom=self.other_classroom, subject=self.subject)
        other_homework = Homework.objects.create(classroom=self.other_classroom, subject=self.subject, title="Other", description="Task", due_date=date.today(), created_by=self.other_teacher_user)
        submission = Submission.objects.create(homework=other_homework, student=self.first, text="Answer")
        self.client.force_login(admin)
        for name, args in (("list", []), ("create", []), ("tracking", [other_homework.pk]), ("edit", [other_homework.pk]), ("delete", [other_homework.pk]), ("submission_detail", [other_homework.pk, submission.pk]), ("review", [other_homework.pk, submission.pk])):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(f"homework:{name}", args=args)).status_code, 200)
        create_response = self.client.get(reverse("homework:create"))
        self.assertEqual(list(create_response.context["form"].fields["class_subject"].queryset), list(ClassSubject.objects.order_by("classroom__name", "classroom__section", "subject__name")))
        self.assertEqual(self.client.post(reverse("homework:create"), {"class_subject": assignment.pk, "title": "Admin task", "description": "Task", "due_date": date.today().isoformat()}).status_code, 302)
        self.assertEqual(Homework.objects.get(title="Admin task").created_by, admin)

    def test_homework_form_lists_only_the_teachers_class_subject_pairs(self):
        own_assignment = ClassSubject.objects.get(classroom=self.classroom, subject=self.subject)
        other_assignment = ClassSubject.objects.get(classroom=self.other_classroom, subject=self.subject)
        own_form = HomeworkForm(teacher=self.teacher)
        other_form = HomeworkForm(teacher=self.other_teacher)
        self.assertEqual(list(own_form.fields["class_subject"].queryset), [own_assignment])
        self.assertEqual(list(other_form.fields["class_subject"].queryset), [other_assignment])
        self.assertEqual(own_form.fields["class_subject"].label_from_instance(own_assignment), "8-A: Math")
        forbidden_form = HomeworkForm(data={"class_subject": other_assignment.pk, "title": "Nope", "description": "x", "due_date": date.today()}, teacher=self.teacher)
        self.assertFalse(forbidden_form.is_valid())

    def test_student_cannot_view_another_students_submission(self):
        submission = Submission.objects.create(homework=self.homework, student=self.first, text="private")
        self.client.force_login(self.second.user)
        response = self.client.get(reverse("homework:submit", args=[self.homework.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["submission"].student_id, self.second.pk)
        self.assertNotEqual(response.context["submission"].pk, submission.pk)

    def test_tracking_counts_are_correct(self):
        Submission.objects.create(homework=self.homework, student=self.first, text="on time")
        late_homework = Homework.objects.create(classroom=self.classroom, subject=self.subject, title="Old", description="x", due_date=date.today() - timedelta(days=1), created_by=self.teacher_user)
        Submission.objects.create(homework=late_homework, student=self.first, text="late")
        self.client.force_login(self.teacher_user)
        response = self.client.get(reverse("homework:tracking", args=[self.homework.pk]))
        self.assertEqual(response.context["counts"], {"submitted": 1, "pending": 1, "late": 0})
        response = self.client.get(reverse("homework:tracking", args=[late_homework.pk]))
        self.assertEqual(response.context["counts"], {"submitted": 0, "pending": 1, "late": 1})

    def test_parent_child_filter_limits_homework_to_the_selected_child(self):
        other_student = StudentProfile.objects.create(
            user=User.objects.create_user("other-student", role="student"),
            roll_no="R3", classroom=self.other_classroom, admission_date=date.today(),
        )
        other_homework = Homework.objects.create(
            classroom=self.other_classroom, subject=self.subject, title="Geometry",
            description="Solve", due_date=date.today(), created_by=self.other_teacher_user,
        )
        parent_user = User.objects.create_user("parent", role="parent")
        parent = ParentProfile.objects.create(user=parent_user)
        self.first.parents.add(parent)
        other_student.parents.add(parent)
        self.client.force_login(parent_user)

        response = self.client.get(reverse("homework:list"), {"child": other_student.pk})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["items"]), [other_homework])
        self.assertEqual(response.context["items"][0].child.pk, other_student.pk)

    def test_reviewed_submission_list_and_detail_are_visible_to_its_student(self):
        submission = Submission.objects.create(
            homework=self.homework, student=self.first, text="My solution",
            status=Submission.Status.REVIEWED, marks="8.50", feedback="Good work.",
        )
        self.client.force_login(self.first.user)

        response = self.client.get(reverse("homework:list"), {"tab": "reviewed"})
        self.assertContains(response, "View Review")
        self.assertNotContains(response, '>Submit<', html=False)

        response = self.client.get(reverse("homework:submission_detail", args=[self.homework.pk, submission.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "8.50")
        self.assertContains(response, "Good work.")
        self.assertEqual(self.client.get(reverse("homework:submit", args=[self.homework.pk])).status_code, 403)

    def test_submission_detail_is_limited_to_owner_and_linked_parent(self):
        submission = Submission.objects.create(
            homework=self.homework, student=self.first, text="My solution",
            status=Submission.Status.REVIEWED, marks="9", feedback="Excellent.",
        )
        url = reverse("homework:submission_detail", args=[self.homework.pk, submission.pk])

        self.client.force_login(self.second.user)
        self.assertIn(self.client.get(url).status_code, (403, 404))

        parent_user = User.objects.create_user("parent", role="parent")
        parent = ParentProfile.objects.create(user=parent_user)
        self.first.parents.add(parent)
        self.client.force_login(parent_user)
        self.assertEqual(self.client.get(url).status_code, 200)
        response = self.client.get(reverse("homework:list"), {"child": self.first.pk})
        self.assertContains(response, "View Review")

        other_parent_user = User.objects.create_user("other-parent", role="parent")
        ParentProfile.objects.create(user=other_parent_user)
        self.client.force_login(other_parent_user)
        self.assertIn(self.client.get(url).status_code, (403, 404))

    def test_unreviewed_submission_detail_shows_awaiting_review(self):
        submission = Submission.objects.create(homework=self.homework, student=self.first, text="My solution")
        self.client.force_login(self.first.user)
        response = self.client.get(reverse("homework:submission_detail", args=[self.homework.pk, submission.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Awaiting review")

    def test_submission_file_download_is_private_and_uses_opaque_filename(self):
        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            submission=Submission.objects.create(homework=self.homework,student=self.first,text="answer",file=SimpleUploadedFile("my-answer.pdf",b"private bytes"))
            self.assertNotIn("my-answer.pdf",submission.file.name)
            url=reverse("homework:submission_download",args=[submission.pk])
            self.client.force_login(self.first.user)
            response=self.client.get(url); self.assertEqual(response.status_code,200); self.assertEqual(b"".join(response.streaming_content),b"private bytes")
            self.assertEqual(self.client.get(f"/media/{submission.file.name}").status_code,404)
            self.client.force_login(self.second.user); self.assertEqual(self.client.get(url).status_code,403)
            parent_user=User.objects.create_user("linked-parent",role="parent"); parent=ParentProfile.objects.create(user=parent_user); self.first.parents.add(parent)
            self.client.force_login(parent_user); self.assertEqual(self.client.get(url).status_code,200)
            unlinked_user=User.objects.create_user("unlinked-parent",role="parent"); ParentProfile.objects.create(user=unlinked_user)
            self.client.force_login(unlinked_user); self.assertEqual(self.client.get(url).status_code,403)
            self.client.force_login(self.teacher_user); self.assertEqual(self.client.get(url).status_code,200)
            self.client.force_login(self.other_teacher_user); self.assertEqual(self.client.get(url).status_code,403)
            admin=User.objects.create_user("download-admin",role="admin")
            self.client.force_login(admin); self.assertEqual(self.client.get(url).status_code,200)
            self.client.logout(); self.assertEqual(self.client.get(url).status_code,302)

    def test_homework_attachment_download_checks_classroom_and_owner(self):
        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            self.homework.attachment=SimpleUploadedFile("worksheet.pdf",b"worksheet"); self.homework.save()
            self.assertNotIn("worksheet.pdf",self.homework.attachment.name)
            url=reverse("homework:attachment_download",args=[self.homework.pk])
            self.client.force_login(self.first.user); self.assertEqual(self.client.get(url).status_code,200)
            parent_user=User.objects.create_user("class-parent",role="parent"); parent=ParentProfile.objects.create(user=parent_user); self.first.parents.add(parent)
            self.client.force_login(parent_user); self.assertEqual(self.client.get(url).status_code,200)
            self.client.force_login(self.teacher_user); self.assertEqual(self.client.get(url).status_code,200)
            self.client.force_login(self.other_teacher_user); self.assertEqual(self.client.get(url).status_code,403)
            outside_user=User.objects.create_user("outside",role="student")
            StudentProfile.objects.create(user=outside_user,roll_no="R99",classroom=self.other_classroom,admission_date=date.today())
            self.client.force_login(outside_user); self.assertEqual(self.client.get(url).status_code,403)
            admin=User.objects.create_user("attachment-admin",role="admin")
            self.client.force_login(admin); self.assertEqual(self.client.get(url).status_code,200)
            self.client.logout(); self.assertEqual(self.client.get(url).status_code,302)

    def test_download_rejects_storage_path_outside_media_root(self):
        submission=Submission.objects.create(homework=self.homework,student=self.first,text="answer")
        Submission.objects.filter(pk=submission.pk).update(file="../secret.pdf")
        self.client.force_login(self.first.user)
        response=self.client.get(reverse("homework:submission_download",args=[submission.pk]))
        self.assertEqual(response.status_code,404)
