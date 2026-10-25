from django.urls import path
from . import views
app_name="attendance"
urlpatterns=[path("mark/",views.mark,name="mark"),path("my-report/",views.my_report,name="my_report"),path("report/<int:student_id>/",views.report,name="report"),path("class/<int:classroom_id>/report/",views.class_report,name="class_report")]
