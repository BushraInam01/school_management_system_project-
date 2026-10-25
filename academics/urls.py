from django.urls import path
from . import views
app_name="academics"
urlpatterns=[]
for key, prefix in {"student":"Student","teacher":"Teacher","parent":"Parent","classroom":"Classroom","subject":"Subject","classsubject":"ClassSubject","academicyear":"AcademicYear"}.items():
    urlpatterns += [path(f"{key}s/",getattr(views,prefix+"List").as_view(),name=f"{key}_list"),path(f"{key}s/new/",getattr(views,prefix+"Create").as_view(),name=f"{key}_create"),path(f"{key}s/<int:pk>/edit/",getattr(views,prefix+"Update").as_view(),name=f"{key}_update"),path(f"{key}s/<int:pk>/delete/",getattr(views,prefix+"Delete").as_view(),name=f"{key}_delete")]
urlpatterns += [path("students/",views.StudentList.as_view(),name="students")]
