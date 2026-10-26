from django.contrib import admin
from django import forms
from django.db import models
from .models import Homework, Submission

@admin.register(Homework)
class HomeworkAdmin(admin.ModelAdmin):
    formfield_overrides={models.FileField:{"widget":forms.FileInput}}

@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    formfield_overrides={models.FileField:{"widget":forms.FileInput}}
