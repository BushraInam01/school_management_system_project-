"""Root URL configuration."""
from django.contrib import admin
from django.urls import include, path, reverse_lazy
from django.shortcuts import redirect
from accounts.views import AccountPasswordChangeView, RoleLoginView, logout_view
from django.contrib.auth import views as auth_views

handler403 = "accounts.views.error_403"
handler404 = "accounts.views.error_404"
handler500 = "accounts.views.error_500"


def root_redirect(request):
    return redirect("dashboard:home") if request.user.is_authenticated else redirect("login")


urlpatterns = [
    path("admin/", admin.site.urls),
    path("", root_redirect, name="root"),
    path("dashboard/", include("dashboard.urls")),
    path("login/", RoleLoginView.as_view(), name="login"),
    path("accounts/login/", lambda request: redirect("login")),
    path("accounts/logout/", logout_view, name="logout"),
    path("accounts/password-change/", AccountPasswordChangeView.as_view(), name="password_change"),
    path(
        "accounts/password-change/done/",
        auth_views.PasswordChangeDoneView.as_view(template_name="accounts/password_change_done.html"),
        name="password_change_done",
    ),
    path(
        "accounts/password-reset/",
        auth_views.PasswordResetView.as_view(
            template_name="accounts/password_reset_form.html",
            email_template_name="accounts/password_reset_email.html",
            subject_template_name="accounts/password_reset_subject.txt",
            success_url=reverse_lazy("password_reset_done"),
        ),
        name="password_reset",
    ),
    path(
        "accounts/password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(template_name="accounts/password_reset_done.html"),
        name="password_reset_done",
    ),
    path(
        "accounts/password-reset-confirm/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="accounts/password_reset_confirm.html",
            success_url=reverse_lazy("password_reset_complete"),
        ),
        name="password_reset_confirm",
    ),
    path(
        "accounts/password-reset/complete/",
        auth_views.PasswordResetCompleteView.as_view(template_name="accounts/password_reset_complete.html"),
        name="password_reset_complete",
    ),
    path("accounts/", include("accounts.urls")),
    path("academics/", include("academics.urls")),
    path("timetable/", include("timetable.urls")),
    path("attendance/", include("attendance.urls")),
    path("grades/", include("grades.urls")),
    path("homework/", include("homework.urls")),
    path("fees/", include("fees.urls")),
]
