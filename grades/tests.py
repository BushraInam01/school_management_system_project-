from decimal import Decimal
from datetime import date
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from accounts.models import ParentProfile, StudentProfile, TeacherProfile, User
from academics.models import AcademicYear, Classroom, ClassSubject, Subject
from .models import Exam, Grade
class GradeTests(SimpleTestCase):
    def test_letter_grade(self):
        grade=Grade(marks_obtained=Decimal("90"),total_marks=Decimal("100")); self.assertEqual(grade.letter_grade,"A+")

class GradeWorkflowTests(TestCase):
    def setUp(self):
        year=AcademicYear.objects.create(name="2026",start=date(2026,1,1),end=date(2026,12,31),is_current=True)
        self.exam=Exam.objects.create(name="Final",academic_year=year,term="Term 1",start_date=date(2026,5,1))
        teacher_user=User.objects.create_user("teacher",role="teacher"); self.teacher=TeacherProfile.objects.create(user=teacher_user,employee_id="T1"); self.teacher_user=teacher_user
        self.classroom=Classroom.objects.create(name="8",section="A"); self.subject=Subject.objects.create(name="Math",code="MATH"); self.assignment=ClassSubject.objects.create(classroom=self.classroom,subject=self.subject,teacher=self.teacher)
        self.one=StudentProfile.objects.create(user=User.objects.create_user("one",role="student"),roll_no="R1",classroom=self.classroom,admission_date=date.today())
        self.two=StudentProfile.objects.create(user=User.objects.create_user("two",role="student"),roll_no="R2",classroom=self.classroom,admission_date=date.today())
    def payload(self,first="90",second="80"):
        return {"class_subject":self.assignment.pk,"exam":self.exam.pk,"grades-TOTAL_FORMS":"2","grades-INITIAL_FORMS":"0","grades-MIN_NUM_FORMS":"0","grades-MAX_NUM_FORMS":"1000","grades-0-marks_obtained":first,"grades-0-total_marks":"100","grades-0-remarks":"good","grades-1-marks_obtained":second,"grades-1-total_marks":"100","grades-1-remarks":"fine"}
    def test_formset_saves_multiple_and_rejects_invalid_marks(self):
        self.client.force_login(self.teacher_user); url=reverse("grades:entry")
        self.assertEqual(self.client.post(url,self.payload()).status_code,302); self.assertEqual(Grade.objects.count(),2)
        Grade.objects.all().delete()
        response=self.client.post(url,self.payload("101")); self.assertEqual(response.status_code,200); self.assertContains(response,"Marks must be between")

    def test_resaving_existing_grades_changes_only_submitted_grade(self):
        first = Grade.objects.create(student=self.one, exam=self.exam, subject=self.subject, marks_obtained=90, total_marks=100, entered_by=self.teacher_user)
        second = Grade.objects.create(student=self.two, exam=self.exam, subject=self.subject, marks_obtained=80, total_marks=100, entered_by=self.teacher_user)
        self.client.force_login(self.teacher_user)
        payload = {"class_subject": self.assignment.pk, "exam": self.exam.pk, "grades-TOTAL_FORMS": "2", "grades-INITIAL_FORMS": "2", "grades-MIN_NUM_FORMS": "0", "grades-MAX_NUM_FORMS": "1000",
                   "grades-0-id": first.pk, "grades-0-student": self.one.pk, "grades-0-marks_obtained": "95", "grades-0-total_marks": "100", "grades-0-remarks": "changed",
                   "grades-1-id": second.pk, "grades-1-student": self.two.pk, "grades-1-marks_obtained": "80", "grades-1-total_marks": "100", "grades-1-remarks": "fine"}
        response = self.client.post(reverse("grades:entry"), payload)
        self.assertEqual(response.status_code, 302)
        first.refresh_from_db(); second.refresh_from_db()
        self.assertEqual(first.marks_obtained, Decimal("95"))
        self.assertEqual(second.marks_obtained, Decimal("80"))
        payload["grades-0-marks_obtained"] = "101"
        self.assertEqual(self.client.post(reverse("grades:entry"), payload).status_code, 200)

    def test_invalid_exam_selection_returns_not_found(self):
        self.client.force_login(self.teacher_user)
        response = self.client.get(reverse("grades:entry"), {"class_subject": self.assignment.pk, "exam": 999999})
        self.assertEqual(response.status_code, 404)
        malformed = self.client.get(reverse("grades:entry"), {"class_subject": self.assignment.pk, "exam": "abc"})
        self.assertEqual(malformed.status_code, 404)
    def test_boundaries_and_rank(self):
        self.assertEqual([Grade(marks_obtained=Decimal(v),total_marks=Decimal("100")).letter_grade for v in ("90","80","70","60","50","49")],["A+","A","B","C","D","F"])
        Grade.objects.create(student=self.one,exam=self.exam,subject=self.subject,marks_obtained=90,total_marks=100,entered_by=self.teacher_user)
        Grade.objects.create(student=self.two,exam=self.exam,subject=self.subject,marks_obtained=80,total_marks=100,entered_by=self.teacher_user)
        self.client.force_login(self.one.user); response=self.client.get(reverse("grades:report",args=[self.one.pk,self.exam.pk])); self.assertEqual(response.context["rank"],1)
        Grade.objects.filter(student=self.two).update(marks_obtained=90)
        self.assertEqual(__import__("grades.views",fromlist=["report_data"]).report_data(self.one,self.exam)["rank"],1)
        self.assertEqual(__import__("grades.views",fromlist=["report_data"]).report_data(self.two,self.exam)["rank"],1)
    def test_pdf_and_private_access(self):
        Grade.objects.create(student=self.one,exam=self.exam,subject=self.subject,marks_obtained=90,total_marks=100,entered_by=self.teacher_user)
        self.client.force_login(self.one.user); response=self.client.get(reverse("grades:report_pdf",args=[self.one.pk,self.exam.pk])); self.assertEqual(response.status_code,200); self.assertEqual(response["Content-Type"],"application/pdf"); self.assertTrue(b"".join(response.streaming_content).startswith(b"%PDF"))
        self.assertEqual(self.client.get(reverse("grades:report_pdf",args=[self.two.pk,self.exam.pk])).status_code,403)
        parent_user=User.objects.create_user("parent",role="parent"); parent=ParentProfile.objects.create(user=parent_user); self.one.parents.add(parent); self.client.force_login(parent_user); self.assertEqual(self.client.get(reverse("grades:report_pdf",args=[self.two.pk,self.exam.pk])).status_code,403)

    def test_report_card_pdf_still_returns_pdf(self):
        self.client.force_login(self.one.user)
        response=self.client.get(reverse("grades:report_pdf",args=[self.one.pk,self.exam.pk]))
        self.assertEqual(response.status_code,200)
        self.assertTrue(b"".join(response.streaming_content).startswith(b"%PDF"))


class GradeClassSubjectSelectionTests(TestCase):
    def setUp(self):
        year=AcademicYear.objects.create(name="2026",start=date(2026,1,1),end=date(2026,12,31),is_current=True)
        self.exam=Exam.objects.create(name="Final",academic_year=year,term="Term 1",start_date=date(2026,5,1))
        self.teacher1_user=User.objects.create_user("teacher1",role="teacher"); self.teacher1=TeacherProfile.objects.create(user=self.teacher1_user,employee_id="T1")
        self.teacher2_user=User.objects.create_user("teacher2",role="teacher"); self.teacher2=TeacherProfile.objects.create(user=self.teacher2_user,employee_id="T2")
        self.teacher3_user=User.objects.create_user("teacher3",role="teacher"); TeacherProfile.objects.create(user=self.teacher3_user,employee_id="T3")
        english=Subject.objects.create(name="English",code="ENG"); urdu=Subject.objects.create(name="Urdu",code="URD")
        self.teacher1_assignments=[]; self.teacher2_assignments=[]
        for name, teacher, bucket in (("6",self.teacher1,self.teacher1_assignments),("7",self.teacher2,self.teacher2_assignments)):
            for section in ("A","B"):
                classroom=Classroom.objects.create(name=name,section=section)
                for subject in (english,urdu): bucket.append(ClassSubject.objects.create(classroom=classroom,subject=subject,teacher=teacher))
        for number in range(5):
            StudentProfile.objects.create(user=User.objects.create_user(f"student{number}",role="student"),roll_no=f"R{number}",classroom=self.teacher1_assignments[0].classroom,admission_date=date.today())

    def test_each_teacher_sees_only_four_assigned_pairs_and_unassigned_teacher_sees_empty_state(self):
        url=reverse("grades:entry")
        self.client.force_login(self.teacher1_user); response=self.client.get(url)
        self.assertEqual(list(response.context["assignments"]),self.teacher1_assignments)
        for assignment in self.teacher1_assignments: self.assertContains(response, f'value="{assignment.pk}"')
        self.client.force_login(self.teacher2_user); response=self.client.get(url)
        self.assertEqual(response.context["assignments"].count(),4); self.assertNotContains(response,"6-A")
        self.client.force_login(self.teacher3_user); response=self.client.get(url)
        self.assertEqual(response.context["assignments"].count(),0); self.assertContains(response,"No class and subject assignments are available.")

    def test_foreign_assignment_is_forbidden_and_selected_assignment_loads_five_students(self):
        self.client.force_login(self.teacher1_user); url=reverse("grades:entry")
        self.assertEqual(self.client.get(url,{"class_subject":self.teacher2_assignments[0].pk,"exam":self.exam.pk}).status_code,403)
        response=self.client.get(url,{"class_subject":self.teacher1_assignments[0].pk,"exam":self.exam.pk})
        self.assertEqual(response.status_code,200); self.assertEqual(len(response.context["formset"].forms),5)
        payload={"class_subject":self.teacher1_assignments[0].pk,"exam":self.exam.pk,"grades-TOTAL_FORMS":"5","grades-INITIAL_FORMS":"0","grades-MIN_NUM_FORMS":"0","grades-MAX_NUM_FORMS":"1000"}
        for number in range(5): payload.update({f"grades-{number}-marks_obtained":"80",f"grades-{number}-total_marks":"100",f"grades-{number}-remarks":"good"})
        self.assertEqual(self.client.post(url,payload).status_code,302); self.assertEqual(Grade.objects.filter(subject=self.teacher1_assignments[0].subject).count(),5)
        payload["grades-0-marks_obtained"]="101"; self.assertEqual(self.client.post(url,payload).status_code,200); self.assertContains(self.client.post(url,payload),"Marks must be between")


class GradeSecurityAndIntegrityTests(TestCase):
    def setUp(self):
        self.year = AcademicYear.objects.create(name="2026-SEC", start=date(2026, 1, 1), end=date(2026, 12, 31), is_current=True)
        self.exam = Exam.objects.create(name="Midterm", academic_year=self.year, term="T1", start_date=date(2026, 3, 1))
        self.teacher_user = User.objects.create_user("sec_teacher", role="teacher")
        self.teacher = TeacherProfile.objects.create(user=self.teacher_user, employee_id="SEC_T1")
        self.unprofiled_teacher = User.objects.create_user("noprofile_teacher", role="teacher")

        self.class_a = Classroom.objects.create(name="9", section="A")
        self.class_b = Classroom.objects.create(name="9", section="B")
        self.subject = Subject.objects.create(name="Science", code="SCI")

        self.assignment_a = ClassSubject.objects.create(classroom=self.class_a, subject=self.subject, teacher=self.teacher)

        self.student_a1_user = User.objects.create_user("a1", role="student")
        self.student_a1 = StudentProfile.objects.create(user=self.student_a1_user, roll_no="A01", classroom=self.class_a, admission_date=date.today())
        self.student_a2_user = User.objects.create_user("a2", role="student")
        self.student_a2 = StudentProfile.objects.create(user=self.student_a2_user, roll_no="A02", classroom=self.class_a, admission_date=date.today())

        self.student_b1_user = User.objects.create_user("b1", role="student")
        self.student_b1 = StudentProfile.objects.create(user=self.student_b1_user, roll_no="B01", classroom=self.class_b, admission_date=date.today())

    def test_student_id_tampering_on_extra_form_is_rejected(self):
        self.client.force_login(self.teacher_user)
        url = reverse("grades:entry")
        # Both a1 and a2 are missing grades.
        # Index 0 expected a1, Index 1 expected a2.
        # Malicious POST modifies student_id of index 0 to point to student_b1 (from class B)
        payload = {
            "class_subject": self.assignment_a.pk,
            "exam": self.exam.pk,
            "grades-TOTAL_FORMS": "2",
            "grades-INITIAL_FORMS": "0",
            "grades-MIN_NUM_FORMS": "0",
            "grades-MAX_NUM_FORMS": "1000",
            "grades-0-student_id": self.student_b1.pk,  # Tampered!
            "grades-0-marks_obtained": "88",
            "grades-0-total_marks": "100",
            "grades-1-student_id": self.student_a2.pk,
            "grades-1-marks_obtained": "75",
            "grades-1-total_marks": "100",
        }
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Student ID mismatch")
        # Crucial: NO partial save of either grade occurred
        self.assertEqual(Grade.objects.filter(exam=self.exam).count(), 0)

    def test_student_id_swapping_between_classmates_is_rejected(self):
        self.client.force_login(self.teacher_user)
        url = reverse("grades:entry")
        # Swap a1 and a2 student_ids
        payload = {
            "class_subject": self.assignment_a.pk,
            "exam": self.exam.pk,
            "grades-TOTAL_FORMS": "2",
            "grades-INITIAL_FORMS": "0",
            "grades-MIN_NUM_FORMS": "0",
            "grades-MAX_NUM_FORMS": "1000",
            "grades-0-student_id": self.student_a2.pk,  # Swapped
            "grades-0-marks_obtained": "88",
            "grades-0-total_marks": "100",
            "grades-1-student_id": self.student_a1.pk,  # Swapped
            "grades-1-marks_obtained": "75",
            "grades-1-total_marks": "100",
        }
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Student ID mismatch")
        self.assertEqual(Grade.objects.filter(exam=self.exam).count(), 0)

    def test_unauthorized_grade_tampering_on_existing_grade_is_rejected(self):
        grade_a1 = Grade.objects.create(
            student=self.student_a1, exam=self.exam, subject=self.subject,
            marks_obtained=90, total_marks=100, entered_by=self.teacher_user
        )
        self.client.force_login(self.teacher_user)
        url = reverse("grades:entry")
        # Submit form 0 with a1's Grade ID, but tampered student_id pointing to a2
        payload = {
            "class_subject": self.assignment_a.pk,
            "exam": self.exam.pk,
            "grades-TOTAL_FORMS": "2",
            "grades-INITIAL_FORMS": "1",
            "grades-MIN_NUM_FORMS": "0",
            "grades-MAX_NUM_FORMS": "1000",
            "grades-0-id": grade_a1.pk,
            "grades-0-student_id": self.student_a2.pk,  # Tampered!
            "grades-0-marks_obtained": "95",
            "grades-0-total_marks": "100",
            "grades-1-student_id": self.student_a2.pk,
            "grades-1-marks_obtained": "80",
            "grades-1-total_marks": "100",
        }
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Student ID mismatch")
        # Original grade preserved untouched
        grade_a1.refresh_from_db()
        self.assertEqual(grade_a1.marks_obtained, Decimal("90"))
        self.assertFalse(Grade.objects.filter(student=self.student_a2).exists())

    def test_missing_teacher_profile_handled_safely(self):
        self.client.force_login(self.unprofiled_teacher)
        # Entry page renders empty assignments safely
        entry_resp = self.client.get(reverse("grades:entry"))
        self.assertEqual(entry_resp.status_code, 200)
        self.assertContains(entry_resp, "No class and subject assignments are available.")

        # Attempting remarks without teacher profile raises 403, not 500
        remarks_resp = self.client.get(reverse("grades:remarks", args=[self.student_a1.pk, self.exam.pk]))
        self.assertEqual(remarks_resp.status_code, 403)

    def test_student_and_unauthorized_teacher_forbidden_from_remarks(self):
        self.client.force_login(self.student_a1_user)
        # Student cannot access remarks
        self.assertEqual(self.client.get(reverse("grades:remarks", args=[self.student_a1.pk, self.exam.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("grades:entry")).status_code, 403)
