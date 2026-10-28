from datetime import date, time
from io import StringIO
from tempfile import NamedTemporaryFile

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import ParentProfile, StudentProfile, TeacherProfile, User
from academics.models import AcademicYear, ClassSubject, Classroom, Subject
from attendance.models import Attendance
from fees.models import FeePayment, FeeStructure
from grades.models import Exam, Grade, ReportCardRemark
from homework.models import Homework, Submission
from timetable.models import TimeSlot, TimetableEntry


CSV_HEADER = "first_name,last_name,username,email,roll_no,class_name,section,parent_username,parent_email\n"


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ManagementCommandTests(TestCase):
    def setUp(self):
        self.classroom = Classroom.objects.create(name="7", section="A")

    def run_import(self, content, *args):
        handle = NamedTemporaryFile(mode="w", suffix=".csv", encoding="utf-8", delete=False)
        try:
            handle.write(content)
            handle.close()
            output, errors = StringIO(), StringIO()
            call_command("import_students", handle.name, *args, stdout=output, stderr=errors)
            return output.getvalue(), errors.getvalue()
        finally:
            import os
            try:
                os.unlink(handle.name)
            except OSError:
                pass

    def test_import_students_valid_file(self):
        output, errors = self.run_import(CSV_HEADER + "Ada,Lovelace,ada,ada@example.com,R001,7,A,parent-ada,parent@example.com\n")
        self.assertIn("created=1 skipped=0 errors=0", output)
        self.assertEqual(errors, "")
        self.assertTrue(StudentProfile.objects.filter(user__username="ada", roll_no="R001").exists())

    def test_import_students_skips_duplicate_username_and_roll_number(self):
        User.objects.create_user("existing", role="student")
        StudentProfile.objects.create(user=User.objects.get(username="existing"), roll_no="OLD", classroom=self.classroom, admission_date=date.today())
        output, _ = self.run_import(CSV_HEADER + "One,User,existing,new@example.com,R001,7,A,parent1,parent1@example.com\nTwo,User,new,other@example.com,OLD,7,A,parent2,parent2@example.com\n")
        self.assertIn("created=0 skipped=2 errors=0", output)
        self.assertEqual(StudentProfile.objects.count(), 1)

    def test_import_students_reports_bad_row_number_and_missing_classroom(self):
        output, errors = self.run_import(CSV_HEADER + "Bad,Row,bad,,R001,7,A,parent,parent@example.com\nNo,Class,no-class,no-class@example.com,R002,99,Z,parent2,parent2@example.com\n")
        self.assertIn("created=0 skipped=0 errors=2", output)
        self.assertIn("Row 2: missing required value", errors)
        self.assertIn("Row 3: classroom not found", errors)

    def test_import_students_dry_run_creates_nothing(self):
        output, _ = self.run_import(CSV_HEADER + "Ada,Lovelace,ada,ada@example.com,R001,7,A,parent-ada,parent@example.com\n", "--dry-run")
        self.assertIn("created=1 skipped=0 errors=0 (rolled back)", output)
        self.assertFalse(User.objects.filter(username="ada").exists())

    def test_import_students_with_existing_valid_parent(self):
        parent_user = User.objects.create_user("existing_p", email="p@example.com", password="Pass123!", role="parent")
        p_profile = ParentProfile.objects.create(user=parent_user)
        output, errors = self.run_import(CSV_HEADER + "Child,One,child1,c1@example.com,R100,7,A,existing_p,p@example.com\n")
        self.assertIn("created=1 skipped=0 errors=0", output)
        self.assertEqual(errors, "")
        child_profile = StudentProfile.objects.get(roll_no="R100")
        self.assertTrue(child_profile.parents.filter(user=parent_user).exists())
        # Pre-existing parent credentials are NOT exposed in stdout
        self.assertNotIn("existing_p", output)

    def test_import_students_rejects_parent_username_belonging_to_student(self):
        User.objects.create_user("student_user", role="student")
        output, errors = self.run_import(CSV_HEADER + "Child,Two,child2,c2@example.com,R101,7,A,student_user,p@example.com\n")
        self.assertIn("created=0 skipped=0 errors=1", output)
        self.assertIn("incompatible role 'student'", errors)
        self.assertFalse(ParentProfile.objects.filter(user__username="student_user").exists())
        self.assertFalse(StudentProfile.objects.filter(roll_no="R101").exists())

    def test_import_students_rejects_parent_username_belonging_to_teacher(self):
        User.objects.create_user("teacher_user", role="teacher")
        output, errors = self.run_import(CSV_HEADER + "Child,Three,child3,c3@example.com,R102,7,A,teacher_user,p@example.com\n")
        self.assertIn("created=0 skipped=0 errors=1", output)
        self.assertIn("incompatible role 'teacher'", errors)
        self.assertFalse(ParentProfile.objects.filter(user__username="teacher_user").exists())
        self.assertFalse(StudentProfile.objects.filter(roll_no="R102").exists())

    def test_import_students_rejects_parent_username_belonging_to_admin(self):
        User.objects.create_user("admin_user", role="admin")
        output, errors = self.run_import(CSV_HEADER + "Child,Four,child4,c4@example.com,R103,7,A,admin_user,p@example.com\n")
        self.assertIn("created=0 skipped=0 errors=1", output)
        self.assertIn("incompatible role 'admin'", errors)
        self.assertFalse(ParentProfile.objects.filter(user__username="admin_user").exists())
        self.assertFalse(StudentProfile.objects.filter(roll_no="R103").exists())

    def test_import_students_rejects_inactive_parent(self):
        inactive_parent = User.objects.create_user("inactive_p", role="parent")
        inactive_parent.is_active = False
        inactive_parent.save()
        output, errors = self.run_import(CSV_HEADER + "Child,Five,child5,c5@example.com,R104,7,A,inactive_p,p@example.com\n")
        self.assertIn("created=0 skipped=0 errors=1", output)
        self.assertIn("inactive account", errors)
        self.assertFalse(StudentProfile.objects.filter(roll_no="R104").exists())

    def test_repeated_import_skips_valid_data(self):
        csv_data = CSV_HEADER + "Rep,Student,rep_stu,rep@example.com,R105,7,A,rep_parent,rep_p@example.com\n"
        output1, _ = self.run_import(csv_data)
        self.assertIn("created=1 skipped=0 errors=0", output1)
        output2, _ = self.run_import(csv_data)
        self.assertIn("created=0 skipped=1 errors=0", output2)

    def test_setup_roles_is_idempotent(self):
        call_command("setup_roles", verbosity=0)
        call_command("setup_roles", verbosity=0)
        self.assertEqual(Group.objects.filter(name__in=[label for _, label in User.Role.choices]).count(), 4)
        self.assertEqual(Group.objects.count(), 4)

    def test_seed_demo_data_is_idempotent_and_complete(self):
        call_command("seed_demo_data", reset=True, yes=True, verbosity=0)
        baseline = (StudentProfile.objects.count(), Attendance.objects.count(), Exam.objects.count(), Grade.objects.count(), ReportCardRemark.objects.count(), Homework.objects.count(), Submission.objects.count(), FeePayment.objects.count())
        self.assertEqual(set(Classroom.objects.values_list("name", "section")), {("Grade 6", "A"), ("Grade 6", "B"), ("Grade 7", "A"), ("Grade 7", "B")})
        self.assertFalse(Classroom.objects.filter(name="Grade 6", section="C").exists())
        self.assertEqual(StudentProfile.objects.count(), 20)
        for classroom in Classroom.objects.all():
            self.assertEqual(classroom.students.count(), 5)
        self.assertEqual(Attendance.objects.count(), StudentProfile.objects.count() * 30)
        self.assertEqual(Exam.objects.count(), 2)
        self.assertEqual(StudentProfile.objects.filter(user__username__regex=r"^student[0-9]+$").count(), 20)
        self.assertEqual(Grade.objects.count(), StudentProfile.objects.count() * 2 * 2)
        self.assertEqual(ReportCardRemark.objects.count(), StudentProfile.objects.count() * 2)
        self.assertEqual(set(Submission.objects.values_list("status", flat=True)), {"pending", "submitted", "late", "reviewed"})
        self.assertEqual(set(FeePayment.objects.values_list("status", flat=True)), {"paid", "partial", "unpaid"})
        for student in StudentProfile.objects.filter(user__username__startswith="student"):
            records = Attendance.objects.filter(student=student)
            percentage = records.filter(status=Attendance.Status.PRESENT).count() * 100 / records.count()
            self.assertGreaterEqual(percentage, 85)
            self.assertLessEqual(percentage, 95)
        parent_links = tuple(ParentProfile.objects.filter(user__username__startswith="parent").order_by("user__username").values_list("user__username", "children__user__username"))
        teacher_links = tuple(ClassSubject.objects.filter(teacher__user__username__startswith="teacher").order_by("teacher__user__username", "classroom__section", "subject__code").values_list("teacher__user__username", "classroom__section", "subject__code"))
        call_command("seed_demo_data", reset=True, yes=True, verbosity=0)
        self.assertEqual((StudentProfile.objects.count(), Attendance.objects.count(), Exam.objects.count(), Grade.objects.count(), ReportCardRemark.objects.count(), Homework.objects.count(), Submission.objects.count(), FeePayment.objects.count()), baseline)
        self.assertEqual(tuple(ParentProfile.objects.filter(user__username__startswith="parent").order_by("user__username").values_list("user__username", "children__user__username")), parent_links)
        self.assertEqual(tuple(ClassSubject.objects.filter(teacher__user__username__startswith="teacher").order_by("teacher__user__username", "classroom__section", "subject__code").values_list("teacher__user__username", "classroom__section", "subject__code")), teacher_links)

    def test_seed_uses_the_exact_mixed_class_and_parent_layout(self):
        call_command("seed_demo_data", reset=True, yes=True, verbosity=0)
        expected_classes = {
            ("Grade 6", "A"): {1, 6, 10, 14, 17},
            ("Grade 6", "B"): {4, 8, 12, 15, 19},
            ("Grade 7", "A"): {2, 3, 7, 11, 18},
            ("Grade 7", "B"): {5, 9, 13, 16, 20},
        }
        for spec, numbers in expected_classes.items():
            classroom = Classroom.objects.get(name=spec[0], section=spec[1])
            self.assertEqual(
                set(classroom.students.values_list("user__username", flat=True)),
                {f"student{number}" for number in numbers},
            )
        self.assertEqual(
            StudentProfile.objects.filter(user__username__in=("student2", "student3")).values_list("classroom__name", "classroom__section").distinct().get(),
            ("Grade 7", "A"),
        )

        expected_parents = {1: (1,), 2: (2, 3), 3: (4, 5, 6, 7), **{number: (number + 4,) for number in range(4, 17)}}
        for number, child_numbers in expected_parents.items():
            self.assertEqual(
                set(ParentProfile.objects.get(user__username=f"parent{number}").children.values_list("user__username", flat=True)),
                {f"student{child}" for child in child_numbers},
            )

        self.client.force_login(User.objects.get(username="parent3"))
        response = self.client.get(reverse("dashboard:home"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("Child switcher:", response.content.decode())
        parent3_classes = set(ParentProfile.objects.get(user__username="parent3").children.values_list("classroom__name", "classroom__section"))
        self.assertEqual(parent3_classes, set(expected_classes))
        for name, section in parent3_classes:
            self.assertIn(f"{name}-{section}", response.content.decode())

    def test_seed_corrects_demo_relationships_and_access(self):
        call_command("seed_demo_data", reset=True, yes=True, verbosity=0)
        students = {number: StudentProfile.objects.get(user__username=f"student{number}") for number in range(1, 21)}
        expected_parents = {1: (1,), 2: (2, 3), 3: (4, 5, 6, 7)}
        for number, expected_children in expected_parents.items():
            parent = ParentProfile.objects.get(user__username=f"parent{number}")
            self.assertEqual(set(parent.children.values_list("pk", flat=True)), {students[child].pk for child in expected_children})

        expected_teaching = {
            1: {("Grade 6", "A", "ENG"), ("Grade 6", "A", "URD"), ("Grade 6", "B", "ENG"), ("Grade 6", "B", "URD")},
            2: {("Grade 7", "A", "ENG"), ("Grade 7", "A", "URD"), ("Grade 7", "B", "ENG"), ("Grade 7", "B", "URD")},
            3: set(),
        }
        expected_led = {1: {("Grade 6", "A"), ("Grade 6", "B")}, 2: {("Grade 7", "A"), ("Grade 7", "B")}, 3: set()}
        for number in range(1, 4):
            teacher = TeacherProfile.objects.get(user__username=f"teacher{number}")
            self.assertEqual(set(teacher.classrooms_led.values_list("name", "section")), expected_led[number])
            self.assertEqual(set(teacher.teaching_assignments.values_list("classroom__name", "classroom__section", "subject__code")), expected_teaching[number])

        exam = Exam.objects.first()
        checks = ((1, 2), (2, 1), (2, 4), (3, 1), (3, 2))
        for parent_number, other_student_number in checks:
            self.client.force_login(User.objects.get(username=f"parent{parent_number}"))
            urls = (
                reverse("attendance:report", args=[students[other_student_number].pk]),
                f"{reverse('grades:list')}?child={students[other_student_number].pk}",
                reverse("grades:report_pdf", args=[students[other_student_number].pk, exam.pk]),
                f"{reverse('homework:list')}?child={students[other_student_number].pk}",
                reverse("fees:student", args=[students[other_student_number].pk]),
            )
            for url in urls:
                with self.subTest(parent=parent_number, url=url):
                    self.assertIn(self.client.get(url).status_code, (403, 404))

        for parent_number, has_switcher in ((1, False), (2, True), (3, True)):
            self.client.force_login(User.objects.get(username=f"parent{parent_number}"))
            self.assertEqual("Child switcher:" in self.client.get(reverse("dashboard:home")).content.decode(), has_switcher)

    def test_teacher_demo_scope_and_cross_class_access(self):
        call_command("seed_demo_data", reset=True, yes=True, verbosity=0)
        from attendance.views import permitted_classrooms
        from grades.views import allowed_assignments
        from homework.views import teacher_homework

        exam = Exam.objects.first()
        class_groups = {
            "teacher1": (("Grade 6", "A"), ("Grade 6", "B")),
            "teacher2": (("Grade 7", "A"), ("Grade 7", "B")),
        }
        for username, allowed_specs in class_groups.items():
            user = User.objects.get(username=username)
            allowed = [Classroom.objects.get(name=name, section=section) for name, section in allowed_specs]
            denied = Classroom.objects.exclude(pk__in=[classroom.pk for classroom in allowed])
            self.assertEqual(set(permitted_classrooms(user)), set(allowed))
            self.assertEqual(set(allowed_assignments(user).values_list("classroom_id", flat=True)), {classroom.pk for classroom in allowed})
            self.assertEqual(set(teacher_homework(user).values_list("classroom_id", flat=True)), {classroom.pk for classroom in allowed})
            self.client.force_login(user)
            visible = "\n".join(self.client.get(reverse("attendance:mark"), {"classroom": classroom.pk, "date": date.today()}).content.decode() for classroom in allowed)
            for student in StudentProfile.objects.filter(classroom__in=allowed):
                self.assertIn(f"{student.user.first_name} ({student.roll_no})", visible)
            for student in StudentProfile.objects.filter(classroom__in=denied):
                self.assertNotIn(f"{student.user.first_name} ({student.roll_no})", visible)
            for classroom in denied:
                subject_id = ClassSubject.objects.get(classroom=classroom, subject__code="ENG").subject_id
                homework = Homework.objects.get(classroom=classroom)
                self.assertIn(self.client.get(reverse("attendance:mark"), {"classroom": classroom.pk, "date": date.today()}).status_code, (403, 404))
                self.assertIn(self.client.get(reverse("grades:entry"), {"classroom": classroom.pk, "subject": subject_id, "exam": exam.pk}).status_code, (403, 404))
                self.assertIn(self.client.post(reverse("homework:create"), {"classroom": classroom.pk}).status_code, (403, 404))
                self.assertIn(self.client.get(reverse("homework:tracking", args=[homework.pk])).status_code, (403, 404))

            expected_students = {
                "teacher1": {1, 4, 6, 8, 10, 12, 14, 15, 17, 19},
                "teacher2": {2, 3, 5, 7, 9, 11, 13, 16, 18, 20},
            }[username]
            self.assertEqual(
                set(StudentProfile.objects.filter(classroom__in=allowed).values_list("user__username", flat=True)),
                {f"student{number}" for number in expected_students},
            )

        teacher3 = User.objects.get(username="teacher3")
        self.assertFalse(permitted_classrooms(teacher3).exists())
        self.assertFalse(allowed_assignments(teacher3).exists())
        self.assertFalse(teacher_homework(teacher3).exists())
        self.client.force_login(teacher3)
        for classroom in Classroom.objects.all():
            subject_id = ClassSubject.objects.get(classroom=classroom, subject__code="ENG").subject_id
            homework = Homework.objects.get(classroom=classroom)
            self.assertIn(self.client.get(reverse("attendance:mark"), {"classroom": classroom.pk, "date": date.today()}).status_code, (403, 404))
            self.assertIn(self.client.get(reverse("grades:entry"), {"classroom": classroom.pk, "subject": subject_id, "exam": exam.pk}).status_code, (403, 404))
            self.assertIn(self.client.post(reverse("homework:create"), {"classroom": classroom.pk}).status_code, (403, 404))
            self.assertIn(self.client.get(reverse("homework:tracking", args=[homework.pk])).status_code, (403, 404))

    def test_seed_removes_legacy_grade_6_c_student21_and_parent17_data(self):
        call_command("seed_demo_data", reset=True, yes=True, verbosity=0)
        teacher3 = TeacherProfile.objects.get(user__username="teacher3")
        legacy_class = Classroom.objects.create(name="Grade 6", section="C", class_teacher=teacher3)
        english = Subject.objects.get(code="ENG")
        ClassSubject.objects.create(classroom=legacy_class, subject=english, teacher=teacher3)
        slot = TimeSlot.objects.create(day=5, start_time=time(13), end_time=time(13, 45))
        TimetableEntry.objects.create(classroom=legacy_class, subject=english, teacher=teacher3, timeslot=slot)
        legacy_user = User.objects.create_user("student21", password="DemoPass123!", role=User.Role.STUDENT)
        legacy_student = StudentProfile.objects.create(user=legacy_user, roll_no="R021", classroom=legacy_class, admission_date=date.today())
        Attendance.objects.create(student=legacy_student, date=date.today(), status=Attendance.Status.PRESENT, marked_by=User.objects.get(username="admin"))
        Grade.objects.create(student=legacy_student, exam=Exam.objects.first(), subject=english, marks_obtained=80, total_marks=100, entered_by=teacher3.user)
        homework = Homework.objects.create(classroom=legacy_class, subject=english, title="Legacy", description="Legacy", due_date=date.today(), created_by=teacher3.user)
        Submission.objects.create(homework=homework, student=legacy_student, status=Submission.Status.PENDING)
        structure = FeeStructure.objects.create(classroom=legacy_class, fee_type="Tuition", amount=5000, academic_year=AcademicYear.objects.get(name="2026-27"))
        FeePayment.objects.create(student=legacy_student, fee_structure=structure, amount_paid=0, method=FeePayment.Method.CASH, received_by=User.objects.get(username="admin"))
        parent17 = User.objects.create_user("parent17", password="DemoPass123!", role=User.Role.PARENT)
        ParentProfile.objects.create(user=parent17).children.add(legacy_student)

        call_command("seed_demo_data", reset=True, yes=True, verbosity=0)
        self.assertFalse(Classroom.objects.filter(name="Grade 6", section="C").exists())
        self.assertFalse(User.objects.filter(username__in=("student21", "parent17")).exists())
        self.assertFalse(TimetableEntry.objects.filter(teacher=teacher3).exists())
        self.assertFalse(ClassSubject.objects.filter(teacher=teacher3).exists())
        self.assertFalse(Classroom.objects.filter(class_teacher=teacher3).exists())

    def test_seed_corrects_old_student_layout_and_regenerates_dependent_records(self):
        call_command("seed_demo_data", reset=True, yes=True, verbosity=0)
        old_classes = list(Classroom.objects.order_by("name", "section"))
        students = list(StudentProfile.objects.filter(user__username__startswith="student").order_by("user__username"))
        for index, student in enumerate(students):
            StudentProfile.objects.filter(pk=student.pk).update(classroom=old_classes[index // 5])

        call_command("seed_demo_data", reset=True, yes=True, verbosity=0)
        for student in StudentProfile.objects.select_related("classroom").filter(user__username__startswith="student"):
            self.assertEqual(student.fee_payments.filter(fee_structure__classroom=student.classroom).count(), 1)
            self.assertFalse(student.fee_payments.exclude(fee_structure__classroom=student.classroom).exists())
            self.assertFalse(student.submissions.exclude(homework__classroom=student.classroom).exists())
            expected_teacher = "teacher1" if student.classroom.name == "Grade 6" else "teacher2"
            self.assertFalse(student.grades.exclude(entered_by__username=expected_teacher).exists())
            self.assertEqual(student.attendance_records.count(), 30)

    def test_teacher_dropdowns_are_distinct_and_scoped(self):
        call_command("seed_demo_data", reset=True, yes=True, verbosity=0)
        from attendance.forms import AttendanceFilterForm
        from attendance.views import permitted_classrooms
        from homework.forms import HomeworkForm

        for username, expected_specs in {
            "teacher1": {("Grade 6", "A"), ("Grade 6", "B")},
            "teacher2": {("Grade 7", "A"), ("Grade 7", "B")},
        }.items():
            user = User.objects.get(username=username)
            teacher = user.teacher_profile
            classrooms = permitted_classrooms(user)
            attendance_form = AttendanceFilterForm(classrooms=classrooms)
            self.assertEqual({int(value) for value, _ in attendance_form.fields["classroom"].choices[1:]}, set(classrooms.values_list("pk", flat=True)))
            self.assertEqual(len(attendance_form.fields["classroom"].choices) - 1, 2)

            self.client.force_login(user)
            response = self.client.get(reverse("grades:entry"))
            assignments = response.context["assignments"]
            self.assertEqual(set(assignments.values_list("classroom__name", "classroom__section")), expected_specs)
            self.assertEqual(assignments.count(), 4)
            self.assertEqual(set(assignments.values_list("subject__code", flat=True)), {"ENG", "URD"})

            homework_form = HomeworkForm(teacher=teacher)
            choices = homework_form.fields["class_subject"].queryset
            self.assertEqual(set(choices.values_list("classroom__name", "classroom__section")), expected_specs)
            self.assertEqual(choices.count(), 4)
            self.assertEqual(set(choices.values_list("subject__code", flat=True)), {"ENG", "URD"})

class SafeSeedCommandTests(TestCase):
    def test_default_seed_preserves_manually_edited_records(self):
        call_command("seed_demo_data", reset=True, yes=True, verbosity=0)
        student = StudentProfile.objects.get(user__username="student1")
        attendance = Attendance.objects.filter(student=student).first()
        attendance.status = Attendance.Status.LEAVE; attendance.remarks = "manual attendance"; attendance.save()
        grade = Grade.objects.filter(student=student).first(); grade.marks_obtained = 12; grade.remarks = "manual grade"; grade.save()
        homework = Homework.objects.filter(classroom=student.classroom).first()
        submission = Submission.objects.filter(homework=homework, student=student).first()
        submission.status = Submission.Status.REVIEWED; submission.feedback = "manual review"; submission.save()
        payment = FeePayment.objects.filter(student=student).first(); payment.amount_paid = 123; payment.save()
        call_command("seed_demo_data", verbosity=0)
        self.assertEqual(Attendance.objects.get(pk=attendance.pk).remarks, "manual attendance")
        self.assertEqual(Grade.objects.get(pk=grade.pk).remarks, "manual grade")
        self.assertEqual(Submission.objects.get(pk=submission.pk).feedback, "manual review")
        self.assertEqual(FeePayment.objects.get(pk=payment.pk).amount_paid, 123)

    def test_reset_without_yes_makes_no_changes(self):
        call_command("seed_demo_data", verbosity=0)
        before = (User.objects.count(), StudentProfile.objects.count(), Attendance.objects.count(), Grade.objects.count())
        call_command("seed_demo_data", reset=True, verbosity=0)
        self.assertEqual(before, (User.objects.count(), StudentProfile.objects.count(), Attendance.objects.count(), Grade.objects.count()))

    def test_timetable_only_leaves_other_tables_unchanged(self):
        call_command("seed_demo_data", reset=True, yes=True, verbosity=0)
        from academics.models import AcademicYear, ClassSubject, Classroom, Subject
        from accounts.models import ParentProfile, TeacherProfile
        from fees.models import FeeStructure
        from timetable.models import TimeSlot, TimetableEntry
        tracked = [User, StudentProfile, ParentProfile, TeacherProfile, AcademicYear, ClassSubject, Classroom, Subject, Attendance, Grade, ReportCardRemark, Homework, Submission, FeeStructure, FeePayment]
        before = [model.objects.count() for model in tracked]
        call_command("seed_demo_data", timetable_only=True, verbosity=0)
        self.assertEqual(before, [model.objects.count() for model in tracked])
        self.assertEqual(TimeSlot.objects.count(), 36)
        self.assertFalse(TimetableEntry.objects.filter(teacher__in=TeacherProfile.objects.filter(user__username__in=("teacher1", "teacher2"))).values("timeslot_id", "teacher_id").annotate(n=__import__("django.db.models", fromlist=["Count"]).Count("id")).filter(n__gt=1).exists())

    def test_timetable_only_creates_six_slots_and_three_alternating_periods_per_class_day(self):
        call_command("seed_demo_data", reset=True, yes=True, verbosity=0)
        call_command("seed_demo_data", timetable_only=True, verbosity=0)
        self.assertEqual(TimeSlot.objects.count(), 36)
        self.assertEqual(set(TimeSlot.objects.values_list("start_time", flat=True)), {time(hour) for hour in range(8,14)})
        self.assertTrue(all(TimeSlot.objects.filter(day=day).count()==6 for day in range(6)))
        entries=list(TimetableEntry.objects.select_related("classroom","teacher","timeslot","subject").order_by("timeslot__day","timeslot__start_time"))
        self.assertEqual(len(entries),72)
        for classroom in Classroom.objects.filter(name__in=("Grade 6","Grade 7")):
            for day in range(6):
                daily=[entry for entry in entries if entry.classroom_id==classroom.pk and entry.timeslot.day==day]
                self.assertEqual(len(daily),3)
                self.assertEqual([entry.subject.code for entry in daily],["ENG","URD","ENG"])
        self.assertEqual(len({(entry.teacher_id,entry.timeslot_id) for entry in entries}),len(entries))
        self.assertEqual(len({(entry.classroom_id,entry.timeslot_id) for entry in entries}),len(entries))
