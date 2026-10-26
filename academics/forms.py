"""Admin-facing forms for people and academic configuration."""
from django import forms
from django.contrib.auth.password_validation import validate_password
from accounts.models import ParentProfile, StudentProfile, TeacherProfile, User
from .models import AcademicYear, Classroom, ClassSubject, Subject

class ProfileMixin:
    user_fields=("username","first_name","last_name","email")
    def clean(self):
        cleaned=super().clean()
        password=cleaned.get("password1")
        confirmation=cleaned.get("password2")
        if password or confirmation:
            if password != confirmation:
                self.add_error("password2","The two password fields did not match.")
            elif password:
                user=getattr(self.instance,"user",None) or User(role=self.user_role)
                for field in self.user_fields:
                    if field in cleaned: setattr(user,field,cleaned[field])
                try: validate_password(password,user)
                except forms.ValidationError as error: self.add_error("password1",error)
        elif not getattr(self.instance,"pk",None):
            self.add_error("password1","A password is required for a new user.")
        return cleaned
    def populate_user(self,role):
        user=getattr(self.instance,"user",None) or User(role=role)
        for field in self.user_fields: setattr(user,field,self.cleaned_data[field])
        password=self.cleaned_data.get("password1")
        if password: user.set_password(password)
        user.save(); return user

class StudentForm(ProfileMixin,forms.ModelForm):
    user_role="student"
    username=forms.CharField(); first_name=forms.CharField(required=False); last_name=forms.CharField(required=False); email=forms.EmailField(required=False)
    password1=forms.CharField(label="Password",widget=forms.PasswordInput,required=False,help_text="Set a password for this account; leave blank when editing to keep the current password.")
    password2=forms.CharField(label="Confirm password",widget=forms.PasswordInput,required=False)
    class Meta: model=StudentProfile; fields=("roll_no","classroom","date_of_birth","admission_date","photo","parents"); widgets={"photo":forms.FileInput}
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
    user_role="teacher"
    class Meta: model=TeacherProfile; fields=("employee_id","phone","subjects")
    def save(self,commit=True): self.instance.user=self.populate_user("teacher"); return forms.ModelForm.save(self,commit)

class ParentForm(StudentForm):
    user_role="parent"
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
