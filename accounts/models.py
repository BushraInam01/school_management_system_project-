"""Identity and profile models."""
from pathlib import PurePath
from django.contrib.auth.models import AbstractUser, Group
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models
from .uploads import student_photo_upload_to


def validate_photo_size(value):
    if value.size > 2 * 1024 * 1024:
        raise ValidationError("Photo file size must not exceed 2 MB.")


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        TEACHER = "teacher", "Teacher"
        STUDENT = "student", "Student"
        PARENT = "parent", "Parent"
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.STUDENT, db_index=True)
    def save(self,*args,**kwargs):
        if self.is_superuser:
            self.role=self.Role.ADMIN
        super().save(*args,**kwargs)
        if self.is_superuser:
            group,_=Group.objects.get_or_create(name="Admin")
            self.groups.add(group)
    def __str__(self): return self.get_full_name() or self.username


class ParentProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="parent_profile")
    phone = models.CharField(max_length=30, blank=True)
    address = models.TextField(blank=True)
    def __str__(self): return str(self.user)


class TeacherProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="teacher_profile")
    employee_id = models.CharField(max_length=30, unique=True)
    phone = models.CharField(max_length=30, blank=True)
    subjects = models.ManyToManyField("academics.Subject", blank=True, related_name="specialist_teachers")
    def __str__(self): return f"{self.user} ({self.employee_id})"


class StudentProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="student_profile")
    roll_no = models.CharField(max_length=30, unique=True)
    classroom = models.ForeignKey("academics.Classroom", on_delete=models.PROTECT, related_name="students")
    date_of_birth = models.DateField(null=True, blank=True)
    admission_date = models.DateField()
    is_active = models.BooleanField(default=True, db_index=True)
    photo = models.ImageField(
        upload_to=student_photo_upload_to,
        blank=True,
        validators=[validate_photo_size, FileExtensionValidator(["jpg", "jpeg", "png"])],
    )
    photo_original_name = models.CharField(max_length=255, blank=True)
    parents = models.ManyToManyField(ParentProfile, blank=True, related_name="children")
    class Meta:
        ordering = ("classroom", "roll_no")
        indexes = [models.Index(fields=["classroom", "roll_no"])]
    def __str__(self): return f"{self.user} ({self.roll_no})"

    def archive(self):
        """Safely archive student without destroying historical records."""
        self.is_active = False
        self.save(update_fields=["is_active"])
        if self.user_id:
            self.user.is_active = False
            self.user.save(update_fields=["is_active"])

    def delete(self, *args, **kwargs):
        """Prevent accidental hard deletion of students with historical academic/financial records."""
        has_grades = getattr(self, "grades", None) and self.grades.exists()
        has_attendance = getattr(self, "attendance_records", None) and self.attendance_records.exists()
        has_fees = getattr(self, "fee_payments", None) and self.fee_payments.exists()
        has_submissions = getattr(self, "submissions", None) and self.submissions.exists()
        if has_grades or has_attendance or has_fees or has_submissions:
            raise ValidationError("Cannot permanently delete a student with existing grades, attendance, fee, or homework records. Archive the student instead.")
        super().delete(*args, **kwargs)

    def save(self,*args,**kwargs):
        if self.photo and not self.photo._committed:
            self.photo_original_name=PurePath(self.photo.name).name
        super().save(*args,**kwargs)
