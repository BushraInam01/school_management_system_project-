from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django import forms
from django.db import models
from .models import User, ParentProfile, StudentProfile, TeacherProfile
class StudentInline(admin.StackedInline):
    model=StudentProfile; extra=0
    formfield_overrides={models.ImageField:{"widget":forms.FileInput}}
class ParentInline(admin.StackedInline): model=ParentProfile; extra=0
class TeacherInline(admin.StackedInline): model=TeacherProfile; extra=0
@admin.register(User)
class SchoolUserAdmin(UserAdmin):
    inlines=[StudentInline,ParentInline,TeacherInline]
    list_display=("username","email","role","is_active")
    list_filter=("role","is_active")
    formfield_overrides={models.ImageField:{"widget":forms.FileInput}}
@admin.register(StudentProfile)
class StudentAdmin(admin.ModelAdmin):
    list_display=("roll_no","user","classroom"); search_fields=("roll_no","user__username"); list_filter=("classroom",)
    formfield_overrides={models.ImageField:{"widget":forms.FileInput}}
admin.site.register(ParentProfile)
admin.site.register(TeacherProfile)
