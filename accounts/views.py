from django.contrib.auth import logout
import hashlib

from django.contrib.auth.views import LoginView
from django.contrib.auth.views import PasswordChangeView
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.contrib.auth.decorators import login_required
from .downloads import protected_file_response
from .models import StudentProfile

class RoleLoginView(LoginView):
    template_name="login.html"
    failure_limit=5
    failure_window=15*60
    block_window=15*60
    throttle_message="Too many failed login attempts. Please try again in 15 minutes."

    def _throttle_keys(self):
        username=(self.request.POST.get("username") or "").strip().casefold()
        ip=self.request.META.get("REMOTE_ADDR", "")
        digest=hashlib.sha256(f"{username}\0{ip}".encode()).hexdigest()
        return f"login-failures:{digest}", f"login-block:{digest}"

    def dispatch(self,request,*args,**kwargs):
        if request.method=="POST":
            self.request=request
            _,block_key=self._throttle_keys()
            if cache.get(block_key):
                self._blocked_attempt=True
                form=self.get_form()
                form.add_error(None,self.throttle_message)
                return self.form_invalid(form)
        return super().dispatch(request,*args,**kwargs)

    def form_invalid(self,form):
        username=(self.request.POST.get("username") or "").strip()
        password=self.request.POST.get("password") or ""
        if username and password and not getattr(self,"_blocked_attempt",False):
            count_key,block_key=self._throttle_keys()
            try:
                if cache.add(count_key,1,self.failure_window):
                    failures=1
                else:
                    failures=cache.incr(count_key)
            except ValueError:
                cache.set(count_key,1,self.failure_window)
                failures=1
            if failures>=self.failure_limit:
                cache.set(block_key,True,self.block_window)
                form.add_error(None,self.throttle_message)
        return super().form_invalid(form)

    def form_valid(self,form):
        count_key,block_key=self._throttle_keys()
        cache.delete_many((count_key,block_key))
        return super().form_valid(form)

    def get_success_url(self):
        redirect_to=self.get_redirect_url()
        if redirect_to and url_has_allowed_host_and_scheme(redirect_to,allowed_hosts={self.request.get_host()},require_https=self.request.is_secure()):
            return redirect_to
        return reverse_lazy("dashboard:home")

class AccountPasswordChangeView(PasswordChangeView):
    template_name="accounts/password_change.html"
    success_url=reverse_lazy("password_change_done")


@login_required
def student_photo(request,student_id):
    student=get_object_or_404(StudentProfile.objects.select_related("user","classroom"),pk=student_id)
    user=request.user
    allowed=user.role=="admin"
    if user.role=="student":
        allowed=student.user_id==user.pk
    elif user.role=="parent":
        parent=getattr(user,"parent_profile",None)
        allowed=bool(parent and student.parents.filter(pk=parent.pk).exists())
    elif user.role=="teacher":
        teacher=getattr(user,"teacher_profile",None)
        allowed=bool(teacher and (student.classroom.class_teacher_id==teacher.pk or student.classroom.class_subjects.filter(teacher=teacher).exists()))
    if not allowed:
        raise PermissionDenied
    return protected_file_response(student.photo,student.photo_original_name)

def logout_view(request):
    if request.method == "POST": logout(request)
    return redirect("login")
def error_403(request, exception=None): return render(request,"403.html",status=403)
def error_404(request, exception=None): return render(request,"404.html",status=404)
def error_500(request): return render(request,"500.html",status=500)
