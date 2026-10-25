from datetime import date
from django.test import TestCase
from django.urls import reverse
from accounts.models import User
from .models import AcademicYear, Classroom, Subject
class AdminCrudTests(TestCase):
    def setUp(self):
        self.admin=User.objects.create_user("admin",password="pass",role="admin")
        self.student=User.objects.create_user("student",password="pass",role="student")
    def test_non_admin_is_forbidden_from_each_crud_list(self):
        self.client.force_login(self.student)
        for name in ("student_list","teacher_list","parent_list","classroom_list","subject_list","classsubject_list","academicyear_list"):
            self.assertEqual(self.client.get(reverse(f"academics:{name}")).status_code,403)
    def test_subject_crud_smoke(self):
        self.client.force_login(self.admin)
        create=reverse("academics:subject_create")
        response=self.client.post(create,{"name":"Physics","code":"PHY"})
        self.assertEqual(response.status_code,302)
        subject=Subject.objects.get(code="PHY")
        self.assertEqual(self.client.post(reverse("academics:subject_update",args=[subject.pk]),{"name":"Physics II","code":"PHY"}).status_code,302)
        self.assertEqual(self.client.post(reverse("academics:subject_delete",args=[subject.pk])).status_code,302)
        self.assertFalse(Subject.objects.filter(pk=subject.pk).exists())
    def test_classroom_and_year_create(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(reverse("academics:classroom_create"),{"name":"Grade 7","section":"A","class_teacher":""}).status_code,302)
        self.assertEqual(self.client.post(reverse("academics:academicyear_create"),{"name":"2030","start":"2030-01-01","end":"2030-12-31","is_current":""}).status_code,302)
