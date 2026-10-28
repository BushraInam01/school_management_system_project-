from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import models

class Exam(models.Model):
    name=models.CharField(max_length=100)
    academic_year=models.ForeignKey("academics.AcademicYear",on_delete=models.PROTECT)
    term=models.CharField(max_length=50)
    start_date=models.DateField()
    class Meta: ordering=("-start_date",)
    def __str__(self): return f"{self.name} ({self.term})"

class Grade(models.Model):
    student=models.ForeignKey("accounts.StudentProfile",on_delete=models.PROTECT,related_name="grades")
    exam=models.ForeignKey(Exam,on_delete=models.CASCADE,related_name="grades")
    subject=models.ForeignKey("academics.Subject",on_delete=models.PROTECT)
    marks_obtained=models.DecimalField(max_digits=7,decimal_places=2)
    total_marks=models.DecimalField(max_digits=7,decimal_places=2)
    remarks=models.TextField(blank=True)
    entered_by=models.ForeignKey("accounts.User",on_delete=models.PROTECT)
    class Meta:
        ordering=("exam","subject")
        constraints=[models.UniqueConstraint(fields=["student","exam","subject"],name="unique_student_exam_subject")]
    def clean(self):
        if self.total_marks <= 0 or self.marks_obtained < 0 or self.marks_obtained > self.total_marks: raise ValidationError("Marks must be between zero and total marks.")
    @property
    def percentage(self): return (self.marks_obtained / self.total_marks * 100) if self.total_marks else Decimal("0")
    @property
    def letter_grade(self):
        p=self.percentage
        return "A+" if p>=90 else "A" if p>=80 else "B" if p>=70 else "C" if p>=60 else "D" if p>=50 else "F"
    def __str__(self): return f"{self.student} {self.subject}"

class ReportCardRemark(models.Model):
    student=models.ForeignKey("accounts.StudentProfile",on_delete=models.PROTECT,related_name="report_remarks")
    exam=models.ForeignKey(Exam,on_delete=models.CASCADE)
    teacher_remark=models.TextField(blank=True)
    principal_remark=models.TextField(blank=True)
    class Meta: constraints=[models.UniqueConstraint(fields=["student","exam"],name="unique_report_remark")]
