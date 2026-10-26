from django.urls import path

from . import views

app_name = "accounts"
urlpatterns = [path("students/<int:student_id>/photo/", views.student_photo, name="student_photo")]
