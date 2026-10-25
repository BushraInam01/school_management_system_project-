from django.contrib.auth import logout
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render

class RoleLoginView(LoginView):
    template_name="login.html"
    def get_success_url(self): return "/"

def logout_view(request):
    if request.method == "POST": logout(request)
    return redirect("login")
def error_403(request, exception=None): return render(request,"403.html",status=403)
def error_404(request, exception=None): return render(request,"404.html",status=404)
def error_500(request): return render(request,"500.html",status=500)
