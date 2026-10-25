from django.contrib import admin
from .models import Exam, Grade, ReportCardRemark
class GradeInline(admin.TabularInline): model=Grade; extra=0
@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin): inlines=[GradeInline]
admin.site.register(ReportCardRemark)
