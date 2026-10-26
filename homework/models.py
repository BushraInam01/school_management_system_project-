from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils import timezone
from pathlib import PurePath
from accounts.uploads import homework_attachment_upload_to, submission_upload_to

def validate_upload_size(value):
    if value.size > 5 * 1024 * 1024: raise ValidationError("Upload must not exceed 5 MB.")

class Homework(models.Model):
    classroom=models.ForeignKey("academics.Classroom",on_delete=models.CASCADE,related_name="homework_items")
    subject=models.ForeignKey("academics.Subject",on_delete=models.PROTECT)
    title=models.CharField(max_length=200)
    description=models.TextField()
    due_date=models.DateField()
    attachment=models.FileField(upload_to=homework_attachment_upload_to,blank=True,validators=[validate_upload_size,FileExtensionValidator(["pdf","doc","docx","jpg","png","txt"])])
    attachment_original_name=models.CharField(max_length=255,blank=True)
    created_by=models.ForeignKey("accounts.User",on_delete=models.PROTECT,related_name="created_homework")
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta: ordering=("due_date", "-created_at")
    def clean(self):
        """A teacher may only publish work for an assigned class/subject."""
        if self.created_by_id and self.created_by.role == "teacher":
            from academics.models import ClassSubject
            if not ClassSubject.objects.filter(classroom_id=self.classroom_id, subject_id=self.subject_id, teacher=self.created_by.teacher_profile).exists():
                raise ValidationError("You are not assigned to this class and subject.")
    def save(self,*args,**kwargs):
        if self.attachment and not self.attachment._committed:
            self.attachment_original_name=PurePath(self.attachment.name).name
        super().save(*args,**kwargs)
    def __str__(self): return self.title

class Submission(models.Model):
    class Status(models.TextChoices): PENDING="pending","Pending"; SUBMITTED="submitted","Submitted"; LATE="late","Late"; REVIEWED="reviewed","Reviewed"
    homework=models.ForeignKey(Homework,on_delete=models.CASCADE,related_name="submissions")
    student=models.ForeignKey("accounts.StudentProfile",on_delete=models.CASCADE,related_name="submissions")
    file=models.FileField(upload_to=submission_upload_to,blank=True,validators=[validate_upload_size,FileExtensionValidator(["pdf","doc","docx","jpg","png","txt"])])
    file_original_name=models.CharField(max_length=255,blank=True)
    text=models.TextField(blank=True)
    submitted_at=models.DateTimeField(null=True,blank=True)
    status=models.CharField(max_length=10,choices=Status.choices,default=Status.PENDING)
    marks=models.DecimalField(max_digits=7,decimal_places=2,null=True,blank=True)
    feedback=models.TextField(blank=True)
    class Meta: constraints=[models.UniqueConstraint(fields=["homework","student"],name="unique_homework_submission")]
    def clean(self):
        if self.file and self.file.size > 5 * 1024 * 1024: raise ValidationError("Upload must not exceed 5 MB.")
        if self.status in (self.Status.SUBMITTED, self.Status.LATE) and not self.file and not self.text: raise ValidationError("Provide a file or text submission.")
    def save(self,*args,**kwargs):
        if self.file and not self.file._committed:
            self.file_original_name=PurePath(self.file.name).name
        if (self.file or self.text) and not self.submitted_at: self.submitted_at=timezone.now()
        if self.submitted_at and self.status != self.Status.REVIEWED:
            self.status=self.Status.LATE if timezone.localdate(self.submitted_at)>self.homework.due_date else self.Status.SUBMITTED
        super().save(*args,**kwargs)
