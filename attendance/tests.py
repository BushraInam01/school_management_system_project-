from datetime import date, timedelta
from django.test import TestCase
from django.urls import reverse
from accounts.models import ParentProfile, StudentProfile, TeacherProfile, User
from academics.models import Classroom, ClassSubject, Subject
from .models import Attendance

class AttendanceWorkflowTests(TestCase):
    def setUp(self):
        self.teacher_user=User.objects.create_user("teacher",role="teacher")
        self.teacher=TeacherProfile.objects.create(user=self.teacher_user,employee_id="T1")
        self.unassigned_user=User.objects.create_user("other",role="teacher")
        TeacherProfile.objects.create(user=self.unassigned_user,employee_id="T2")
        self.classroom=Classroom.objects.create(name="7",section="A")
        self.other_class=Classroom.objects.create(name="7",section="B")
        subject=Subject.objects.create(name="English",code="ENG")
        ClassSubject.objects.create(classroom=self.classroom,subject=subject,teacher=self.teacher)
        self.first=StudentProfile.objects.create(user=User.objects.create_user("s1",role="student"),roll_no="R1",classroom=self.classroom,admission_date=date.today())
        self.second=StudentProfile.objects.create(user=User.objects.create_user("s2",role="student"),roll_no="R2",classroom=self.classroom,admission_date=date.today())
        self.outsider=StudentProfile.objects.create(user=User.objects.create_user("s3",role="student"),roll_no="R3",classroom=self.other_class,admission_date=date.today())
        self.day=date.today()-timedelta(days=1)
    def post_rows(self,status="present"):
        return {"classroom":str(self.classroom.pk),"date":str(self.day),"attendance-TOTAL_FORMS":"2","attendance-INITIAL_FORMS":"0","attendance-MIN_NUM_FORMS":"0","attendance-MAX_NUM_FORMS":"1000","attendance-0-student_id":str(self.first.pk),"attendance-0-status":status,"attendance-0-remarks":"ok","attendance-1-student_id":str(self.second.pk),"attendance-1-status":"absent","attendance-1-remarks":"away"}
    def test_bulk_marking_creates_all_students_and_resubmission_updates(self):
        self.client.force_login(self.teacher_user)
        self.assertEqual(self.client.post(reverse("attendance:mark"),self.post_rows()).status_code,302)
        self.assertEqual(Attendance.objects.filter(date=self.day).count(),2)
        self.client.post(reverse("attendance:mark"),self.post_rows("late"))
        self.assertEqual(Attendance.objects.filter(date=self.day).count(),2)
        self.assertEqual(Attendance.objects.get(student=self.first,date=self.day).status,"late")
    def test_future_date_is_rejected(self):
        self.client.force_login(self.teacher_user); payload=self.post_rows(); payload["date"]=str(date.today()+timedelta(days=1))
        response=self.client.post(reverse("attendance:mark"),payload)
        self.assertEqual(response.status_code,200); self.assertEqual(Attendance.objects.count(),0)
    def test_unassigned_teacher_cannot_mark(self):
        self.client.force_login(self.unassigned_user)
        self.assertEqual(self.client.get(reverse("attendance:mark"),{"classroom":self.classroom.pk,"date":self.day}).status_code,403)
        self.assertEqual(self.client.post(reverse("attendance:mark"),self.post_rows()).status_code,403)
        self.assertEqual(Attendance.objects.count(),0)
    def test_student_and_parent_cannot_access_other_reports(self):
        self.client.force_login(self.first.user); self.assertEqual(self.client.get(reverse("attendance:report",args=[self.outsider.pk])).status_code,403)
        parent_user=User.objects.create_user("parent",role="parent"); parent=ParentProfile.objects.create(user=parent_user); self.first.parents.add(parent)
        self.client.force_login(parent_user); self.assertEqual(self.client.get(reverse("attendance:report",args=[self.outsider.pk])).status_code,403)

    def test_sunday_shows_warning_without_blocking(self):
        self.client.force_login(self.teacher_user)
        sunday = date.today() - timedelta(days=(date.today().weekday() + 1) % 7 or 7)
        response = self.client.get(reverse("attendance:mark"), {"classroom": self.classroom.pk, "date": sunday})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "selected date is a Sunday")
    def test_percentage_calculation(self):
        Attendance.objects.create(student=self.first,date=self.day,status="present",marked_by=self.teacher_user)
        Attendance.objects.create(student=self.first,date=self.day-timedelta(days=1),status="absent",marked_by=self.teacher_user)
        self.client.force_login(self.first.user); response=self.client.get(reverse("attendance:report",args=[self.first.pk]),{"month":self.day.month,"year":self.day.year})
        self.assertEqual(response.context["summary"]["percentage"],50)
