from django.contrib import admin
from .models import AcademicYear, Classroom, ClassSubject, Subject
class ClassSubjectInline(admin.TabularInline): model=ClassSubject; extra=1
@admin.register(Classroom)
class ClassroomAdmin(admin.ModelAdmin): inlines=[ClassSubjectInline]; list_display=("name","section","class_teacher")
admin.site.register(AcademicYear); admin.site.register(Subject); admin.site.register(ClassSubject)
