"""Identity and profile models."""
from django.contrib.auth.models import AbstractUser
from django.core.validators import FileExtensionValidator
from django.db import models

class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        TEACHER = "teacher", "Teacher"
        STUDENT = "student", "Student"
        PARENT = "parent", "Parent"
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.STUDENT, db_index=True)
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
    photo = models.ImageField(upload_to="students/", blank=True, validators=[FileExtensionValidator(["jpg", "jpeg", "png"])])
    parents = models.ManyToManyField(ParentProfile, blank=True, related_name="children")
    class Meta:
        ordering = ("classroom", "roll_no")
        indexes = [models.Index(fields=["classroom", "roll_no"])]
    def __str__(self): return f"{self.user} ({self.roll_no})"
