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
