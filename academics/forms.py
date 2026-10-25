"""Admin-facing forms for people and academic configuration."""
from django import forms
from accounts.models import ParentProfile, StudentProfile, TeacherProfile, User
from .models import AcademicYear, Classroom, ClassSubject, Subject

class ProfileMixin:
    user_fields=("username","first_name","last_name","email")
    def populate_user(self,role):
        user=getattr(self.instance,"user",None) or User(role=role)
        for field in self.user_fields: setattr(user,field,self.cleaned_data[field])
        if not user.pk: user.set_unusable_password()
        user.save(); return user

class StudentForm(ProfileMixin,forms.ModelForm):
    username=forms.CharField(); first_name=forms.CharField(required=False); last_name=forms.CharField(required=False); email=forms.EmailField(required=False)
    class Meta: model=StudentProfile; fields=("roll_no","classroom","date_of_birth","admission_date","photo","parents")
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        if self.instance.pk:
            for field in self.user_fields: self.fields[field].initial=getattr(self.instance.user,field)
    def clean_username(self):
        value=self.cleaned_data["username"]
        if User.objects.exclude(pk=getattr(self.instance,"user_id",None)).filter(username=value).exists(): raise forms.ValidationError("Username already exists.")
        return value
    def save(self,commit=True): self.instance.user=self.populate_user("student"); return super().save(commit)

class TeacherForm(StudentForm):
    class Meta: model=TeacherProfile; fields=("employee_id","phone","subjects")
    def save(self,commit=True): self.instance.user=self.populate_user("teacher"); return forms.ModelForm.save(self,commit)

class ParentForm(StudentForm):
    class Meta: model=ParentProfile; fields=("phone","address")
    def save(self,commit=True): self.instance.user=self.populate_user("parent"); return forms.ModelForm.save(self,commit)

class ClassroomForm(forms.ModelForm):
    class Meta: model=Classroom; fields="__all__"
class SubjectForm(forms.ModelForm):
    class Meta: model=Subject; fields="__all__"
class ClassSubjectForm(forms.ModelForm):
    class Meta: model=ClassSubject; fields="__all__"
class AcademicYearForm(forms.ModelForm):
    class Meta: model=AcademicYear; fields="__all__"
