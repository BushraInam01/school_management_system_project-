from django.urls import path
from . import views
app_name="grades"
urlpatterns=[path("",views.grade_list,name="list"),path("entry/",views.entry,name="entry"),path("remarks/<int:student_id>/<int:exam_id>/",views.remarks,name="remarks"),path("report/<int:student_id>/<int:exam_id>/",views.report,name="report"),path("report/<int:student_id>/<int:exam_id>/pdf/",views.report_pdf,name="report_pdf")]
