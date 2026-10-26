"""Root URL configuration."""
from django.contrib import admin
from django.urls import include, path
from django.shortcuts import redirect
from accounts.views import AccountPasswordChangeView, RoleLoginView, logout_view
from django.contrib.auth import views as auth_views

handler403 = "accounts.views.error_403"
handler404 = "accounts.views.error_404"
handler500 = "accounts.views.error_500"
def root_redirect(request):
    return redirect("dashboard:home") if request.user.is_authenticated else redirect("login")

urlpatterns = [path("admin/", admin.site.urls), path("", root_redirect, name="root"), path("dashboard/", include("dashboard.urls")), path("login/", RoleLoginView.as_view(), name="login"), path("accounts/login/", lambda request: redirect("login")), path("accounts/logout/", logout_view, name="logout"), path("accounts/password-change/", AccountPasswordChangeView.as_view(), name="password_change"), path("accounts/password-change/done/", auth_views.PasswordChangeDoneView.as_view(template_name="accounts/password_change_done.html"), name="password_change_done"), path("accounts/", include("accounts.urls")), path("academics/", include("academics.urls")), path("timetable/", include("timetable.urls")), path("attendance/", include("attendance.urls")), path("grades/", include("grades.urls")), path("homework/", include("homework.urls")), path("fees/", include("fees.urls"))]
