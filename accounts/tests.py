from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.exceptions import ValidationError
from django.test import override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.cache import cache
from io import StringIO
from tempfile import TemporaryDirectory
from pathlib import Path
from .models import User, StudentProfile, TeacherProfile, ParentProfile
from academics.forms import StudentForm
from academics.models import AcademicYear, Classroom
from datetime import date
import os
import subprocess
import sys
class AccessTests(TestCase):
    def test_login_page_is_available(self): self.assertEqual(self.client.get(reverse("login")).status_code,200)
    def test_unauthenticated_dashboard_redirects(self): self.assertEqual(self.client.get(reverse("dashboard:home")).status_code,302)

    def test_superuser_gets_admin_role_and_group(self):
        user=User.objects.create_superuser("root", "root@example.com", "StrongPass123!")
        self.assertEqual(user.role, User.Role.ADMIN)
        self.assertTrue(user.groups.filter(name="Admin").exists())

    def test_login_honors_only_safe_next(self):
        user=User.objects.create_user("loginstudent", password="StrongPass123!", role="student")
        safe=self.client.post(reverse("login"), {"username":user.username,"password":"StrongPass123!","next":"/fees/"})
        self.assertRedirects(safe,"/fees/",fetch_redirect_response=False)
        self.client.logout()
        unsafe=self.client.post(reverse("login"), {"username":user.username,"password":"StrongPass123!","next":"https://evil.example/"})
        self.assertRedirects(unsafe,reverse("dashboard:home"),fetch_redirect_response=False)

    def test_student_admin_form_password_can_log_in_and_change_password_page_available(self):
        classroom=Classroom.objects.create(name="4",section="A")
        form=StudentForm(data={"username":"createdstudent","first_name":"New","last_name":"Student","email":"new@example.com","password1":"ValidStrongPass8!","password2":"ValidStrongPass8!","roll_no":"NEW1","classroom":classroom.pk,"admission_date":date.today().isoformat(),"parents":[]})
        self.assertTrue(form.is_valid(),form.errors)
        form.save()
        self.assertTrue(self.client.login(username="createdstudent",password="ValidStrongPass8!"))
        self.assertEqual(self.client.get(reverse("password_change")).status_code,200)

    def test_import_prints_login_usable_temporary_password(self):
        Classroom.objects.create(name="5",section="A")
        with TemporaryDirectory() as directory:
            csv_path=Path(directory)/"students.csv"
            csv_path.write_text("first_name,last_name,username,email,roll_no,class_name,section,parent_username,parent_email\nImported,Student,imported,imported@example.com,IMP1,5,A,parentimported,parent@example.com\n")
            output=StringIO(); call_command("import_students",str(csv_path),stdout=output)
        row=next(line for line in output.getvalue().splitlines() if line.startswith("imported,"))
        _,password=row.split(",",1)
        self.assertTrue(self.client.login(username="imported",password=password))

    def test_import_dry_run_never_writes_credentials_file(self):
        Classroom.objects.create(name="7",section="A")
        with TemporaryDirectory() as directory:
            csv_path=Path(directory)/"students.csv"; credentials=Path(directory)/"credentials.csv"
            csv_path.write_text("first_name,last_name,username,email,roll_no,class_name,section,parent_username,parent_email\nDry,Student,dryimport,dry@example.com,DRY1,7,A,dryparent,dryparent@example.com\n")
            output=StringIO(); call_command("import_students",str(csv_path),"--dry-run","--credentials-file",str(credentials),stdout=output)
            self.assertFalse(credentials.exists())
            self.assertNotIn("temporary_password",output.getvalue())

    def test_environment_settings_are_loaded(self):
        environment=os.environ.copy()
        environment.update({"SECRET_KEY":"configured-secret","DEBUG":"false","ALLOWED_HOSTS":"school.example,localhost","DATABASE_PATH":"/tmp/school-env-test.sqlite3"})
        code="from django.conf import settings; print(settings.SECRET_KEY); print(settings.DEBUG); print(','.join(settings.ALLOWED_HOSTS)); print(settings.DATABASES['default']['NAME'])"
        result=subprocess.run([sys.executable,"-c",code],env=environment,capture_output=True,text=True,check=True)
        self.assertEqual(result.stdout.splitlines(),["configured-secret","False","school.example,localhost","/tmp/school-env-test.sqlite3"])

    def test_profile_deletion_deactivates_user(self):
        classroom=Classroom.objects.create(name="6",section="A")
        student_user=User.objects.create_user("deletedstudent")
        student=StudentProfile.objects.create(user=student_user,roll_no="DEL1",classroom=classroom,admission_date=date.today())
        student.delete(); student_user.refresh_from_db(); self.assertFalse(student_user.is_active)

    def test_password_validators_are_configured(self):
        from django.conf import settings
        self.assertEqual(len(settings.AUTH_PASSWORD_VALIDATORS),4)

    def test_login_is_blocked_after_five_failures_for_username_and_ip(self):
        cache.clear()
        user=User.objects.create_user("limited",password="StrongPassword92!")
        url=reverse("login")
        for _ in range(5):
            self.assertEqual(self.client.post(url,{"username":user.username,"password":"wrong"}).status_code,200)
        blocked=self.client.post(url,{"username":user.username,"password":"StrongPassword92!"})
        self.assertEqual(blocked.status_code,200)
        self.assertContains(blocked,"Too many failed login attempts")

    def test_successful_login_resets_failed_login_counter(self):
        cache.clear()
        user=User.objects.create_user("reset-limit",password="StrongPassword92!")
        url=reverse("login")
        for _ in range(4): self.client.post(url,{"username":user.username,"password":"wrong"})
        self.assertEqual(self.client.post(url,{"username":user.username,"password":"StrongPassword92!"}).status_code,302)
        self.client.logout()
        for _ in range(4): self.client.post(url,{"username":user.username,"password":"wrong"})
        self.assertEqual(self.client.post(url,{"username":user.username,"password":"StrongPassword92!"}).status_code,302)


class ProtectedStudentPhotoTests(TestCase):
    def setUp(self):
        from academics.models import Classroom, ClassSubject, Subject
        from accounts.models import TeacherProfile
        self.classroom=Classroom.objects.create(name="3",section="A")
        other_classroom=Classroom.objects.create(name="3",section="B")
        self.student_user=User.objects.create_user("photo-student",role="student")
        self.student=StudentProfile.objects.create(user=self.student_user,roll_no="PH1",classroom=self.classroom,admission_date=date.today(),photo=SimpleUploadedFile("portrait.png",b"private image"))
        self.other_student_user=User.objects.create_user("photo-other",role="student")
        StudentProfile.objects.create(user=self.other_student_user,roll_no="PH2",classroom=other_classroom,admission_date=date.today())
        self.parent_user=User.objects.create_user("photo-parent",role="parent"); self.parent=ParentProfile.objects.create(user=self.parent_user); self.student.parents.add(self.parent)
        self.unlinked_parent=User.objects.create_user("photo-unlinked",role="parent"); ParentProfile.objects.create(user=self.unlinked_parent)
        subject=Subject.objects.create(name="Art",code="ART")
        self.teacher_user=User.objects.create_user("photo-teacher",role="teacher"); self.teacher=TeacherProfile.objects.create(user=self.teacher_user,employee_id="PH-T1")
        self.other_teacher_user=User.objects.create_user("photo-other-teacher",role="teacher"); TeacherProfile.objects.create(user=self.other_teacher_user,employee_id="PH-T2")
        ClassSubject.objects.create(classroom=self.classroom,subject=subject,teacher=self.teacher)

    def test_student_photo_download_access_is_scoped_and_opaque(self):
        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            # Re-save within the temporary storage root used by this test.
            self.student.photo=SimpleUploadedFile("portrait.png",b"private image"); self.student.save()
            self.assertNotIn("portrait.png",self.student.photo.name)
            url=reverse("accounts:student_photo",args=[self.student.pk])
            self.client.force_login(self.student_user); self.assertEqual(self.client.get(url).status_code,200)
            self.client.force_login(self.parent_user); self.assertEqual(self.client.get(url).status_code,200)
            self.client.force_login(self.unlinked_parent); self.assertEqual(self.client.get(url).status_code,403)
            self.client.force_login(self.other_student_user); self.assertEqual(self.client.get(url).status_code,403)
            self.client.force_login(self.teacher_user); self.assertEqual(self.client.get(url).status_code,200)
            self.client.force_login(self.other_teacher_user); self.assertEqual(self.client.get(url).status_code,403)
            admin=User.objects.create_user("photo-admin",role="admin")
            self.client.force_login(admin); self.assertEqual(self.client.get(url).status_code,200)
            self.client.logout(); self.assertEqual(self.client.get(url).status_code,302)
            self.assertEqual(self.client.get(f"/media/{self.student.photo.name}").status_code,404)
