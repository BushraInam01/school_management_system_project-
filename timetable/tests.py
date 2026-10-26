from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.urls import reverse
from .models import TimeSlot, TimetableEntry
from django.core.exceptions import ValidationError
from datetime import date, time
from accounts.models import ParentProfile, StudentProfile, TeacherProfile, User
from academics.models import Classroom, ClassSubject, Subject
class SlotTests(TestCase):
    def test_slot_end_must_follow_start(self):
        with self.assertRaises(ValidationError): TimeSlot(day=0,start_time=time(9),end_time=time(8)).clean()

    def test_overlapping_slots_rejected_adjacent_allowed_and_edit_ignores_self(self):
        base=TimeSlot.objects.create(day=0,start_time=time(9),end_time=time(10))
        overlap=TimeSlot(day=0,start_time=time(9,30),end_time=time(10,30))
        with self.assertRaises(ValidationError): overlap.full_clean()
        adjacent=TimeSlot(day=0,start_time=time(10),end_time=time(11)); adjacent.full_clean()
        base.start_time=time(9,15); base.full_clean()

class TimetableAccessAndClashTests(TestCase):
    def setUp(self):
        self.teacher_user=User.objects.create_user("teacher",role="teacher"); self.teacher=TeacherProfile.objects.create(user=self.teacher_user,employee_id="T1")
        self.other_teacher=TeacherProfile.objects.create(user=User.objects.create_user("teacher2",role="teacher"),employee_id="T2")
        self.subject=Subject.objects.create(name="Math",code="MAT")
        self.class_a=Classroom.objects.create(name="6",section="A"); self.class_b=Classroom.objects.create(name="6",section="B")
        ClassSubject.objects.create(classroom=self.class_a,subject=self.subject,teacher=self.teacher); ClassSubject.objects.create(classroom=self.class_b,subject=self.subject,teacher=self.teacher)
        self.slot=TimeSlot.objects.create(day=0,start_time=time(8),end_time=time(9))
        self.entry=TimetableEntry.objects.create(classroom=self.class_a,subject=self.subject,teacher=self.teacher,timeslot=self.slot)
    def test_teacher_and_class_clashes_are_invalid(self):
        teacher_clash=TimetableEntry(classroom=self.class_b,subject=self.subject,teacher=self.teacher,timeslot=self.slot)
        with self.assertRaises(ValidationError): teacher_clash.full_clean()
        other_slot=TimeSlot.objects.create(day=1,start_time=time(8),end_time=time(9))
        class_clash=TimetableEntry(classroom=self.class_a,subject=self.subject,teacher=self.teacher,timeslot=self.slot)
        with self.assertRaises(ValidationError): class_clash.full_clean()
        self.assertTrue(other_slot.pk)

    def test_overlapping_slots_cannot_double_book_teacher_or_class(self):
        overlapping=TimeSlot.objects.create(day=0,start_time=time(8,30),end_time=time(9,30))
        teacher_clash=TimetableEntry(classroom=self.class_b,subject=self.subject,teacher=self.teacher,timeslot=overlapping)
        with self.assertRaises(ValidationError): teacher_clash.full_clean()
        other_subject=Subject.objects.create(name="Science",code="SCI")
        ClassSubject.objects.create(classroom=self.class_a,subject=other_subject,teacher=self.other_teacher)
        teacher_clash.classroom=self.class_a; teacher_clash.subject=other_subject; teacher_clash.teacher=self.other_teacher
        with self.assertRaises(ValidationError): teacher_clash.full_clean()

    def test_admin_slot_form_shows_overlap_error_and_grid_bad_classroom_is_safe(self):
        from accounts.models import User
        admin=User.objects.create_user("admin",role="admin")
        TimeSlot.objects.create(day=0,start_time=time(9),end_time=time(10))
        self.client.force_login(admin)
        response=self.client.post(reverse("timetable:slot_create"),{"day":0,"start_time":"09:30","end_time":"10:30"})
        self.assertEqual(response.status_code,200)
        self.assertContains(response,"overlap",status_code=200)
        self.assertEqual(self.client.get(reverse("timetable:grid"),{"classroom":"xyz"}).status_code,200)
    def test_student_and_parent_grid_are_scoped(self):
        student_user=User.objects.create_user("s1",role="student"); student=StudentProfile.objects.create(user=student_user,roll_no="R1",classroom=self.class_a,admission_date=date.today())
        other_user=User.objects.create_user("s2",role="student"); StudentProfile.objects.create(user=other_user,roll_no="R2",classroom=self.class_b,admission_date=date.today())
        parent_user=User.objects.create_user("p1",role="parent"); parent=ParentProfile.objects.create(user=parent_user); student.parents.add(parent)
        self.client.force_login(student_user); response=self.client.get(reverse("timetable:grid")); self.assertContains(response,"6-A"); self.assertNotContains(response,"6-B")
        self.client.force_login(parent_user); response=self.client.get(reverse("timetable:grid")); self.assertContains(response,"6-A"); self.assertNotContains(response,"6-B")

    def test_grid_uses_one_row_for_each_unique_time_pair(self):
        admin = User.objects.create_user("admin", role="admin")
        other_day = TimeSlot.objects.create(day=1, start_time=time(8), end_time=time(9))
        self.client.force_login(admin)
        response = self.client.get(reverse("timetable:grid"), {"classroom": self.class_a.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["rows"]), 1)
        self.assertEqual(len(response.context["rows"][0]["cells"]), 6)

    def test_grid_shows_six_unique_time_rows_for_six_daily_periods(self):
        self.entry.delete()
        self.slot.delete()
        for day in range(6):
            for hour in range(8, 14):
                TimeSlot.objects.create(day=day, start_time=time(hour), end_time=time(hour, 45))
        admin = User.objects.create_user("admin_grid", role="admin")
        self.client.force_login(admin)
        response = self.client.get(reverse("timetable:grid"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["rows"]), 6)
