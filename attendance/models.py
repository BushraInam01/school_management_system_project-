from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

class Attendance(models.Model):
    class Status(models.TextChoices): PRESENT="present","Present"; ABSENT="absent","Absent"; LATE="late","Late"; LEAVE="leave","Leave"
    student=models.ForeignKey("accounts.StudentProfile",on_delete=models.PROTECT,related_name="attendance_records")
    date=models.DateField(db_index=True)
    status=models.CharField(max_length=10,choices=Status.choices,default=Status.PRESENT)
    marked_by=models.ForeignKey("accounts.User",on_delete=models.PROTECT,related_name="marked_attendance")
    remarks=models.CharField(max_length=255,blank=True)
    class Meta:
        ordering=("-date",)
        constraints=[models.UniqueConstraint(fields=["student","date"],name="unique_student_attendance")]
    def clean(self):
        if self.date > timezone.localdate(): raise ValidationError("Attendance cannot be marked in the future.")
    def __str__(self): return f"{self.student} {self.date}"
