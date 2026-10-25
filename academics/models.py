from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

class AcademicYear(models.Model):
    name = models.CharField(max_length=20, unique=True)
    start = models.DateField()
    end = models.DateField()
    is_current = models.BooleanField(default=False)
    class Meta:
        ordering = ("-start",)
        constraints = [models.UniqueConstraint(fields=["is_current"], condition=Q(is_current=True), name="one_current_year")]
    def clean(self):
        if self.start >= self.end: raise ValidationError("End date must be after start date.")
    def __str__(self): return self.name

class Subject(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)
    class Meta: ordering = ("name",)
    def __str__(self): return f"{self.name} ({self.code})"

class Classroom(models.Model):
    name = models.CharField(max_length=30)
    section = models.CharField(max_length=10)
    class_teacher = models.ForeignKey("accounts.TeacherProfile", on_delete=models.SET_NULL, null=True, blank=True, related_name="classrooms_led")
    class Meta:
        ordering = ("name", "section")
        constraints = [models.UniqueConstraint(fields=["name", "section"], name="unique_class_section")]
    def __str__(self): return f"{self.name}-{self.section}"

class ClassSubject(models.Model):
    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE, related_name="class_subjects")
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT)
    teacher = models.ForeignKey("accounts.TeacherProfile", on_delete=models.PROTECT, related_name="teaching_assignments")
    class Meta:
        constraints = [models.UniqueConstraint(fields=["classroom", "subject"], name="unique_class_subject")]
    def __str__(self): return f"{self.classroom}: {self.subject}"
