"""Reusable server-side role gates."""
from functools import wraps
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied

class RoleRequiredMixin(LoginRequiredMixin):
    allowed_roles=()
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated: return self.handle_no_permission()
        if self.allowed_roles and request.user.role not in self.allowed_roles: raise PermissionDenied
        return super().dispatch(request,*args,**kwargs)

def role_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped(request,*args,**kwargs):
            if not request.user.is_authenticated: from django.contrib.auth.views import redirect_to_login; return redirect_to_login(request.get_full_path())
            if roles and request.user.role not in roles: raise PermissionDenied
            return view(request,*args,**kwargs)
        return wrapped
    return decorator
