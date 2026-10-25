from django.contrib import messages
from django.db.models import Q
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView
from accounts.mixins import RoleRequiredMixin
from accounts.models import ParentProfile, StudentProfile, TeacherProfile
from .forms import AcademicYearForm, ClassSubjectForm, ClassroomForm, ParentForm, StudentForm, SubjectForm, TeacherForm
from .models import AcademicYear, Classroom, ClassSubject, Subject

class AdminOnly(RoleRequiredMixin): allowed_roles=("admin",)
class SearchList(AdminOnly,ListView):
    paginate_by=10; template_name="academics/crud_list.html"; search_fields=()
    def get_queryset(self):
        qs=super().get_queryset().order_by("pk"); term=self.request.GET.get("q","").strip()
        if term:
            condition=Q()
            for field in self.search_fields: condition|=Q(**{f"{field}__icontains":term})
            qs=qs.filter(condition)
        return qs
    def get_context_data(self,**kwargs):
        ctx=super().get_context_data(**kwargs); ctx.update(title=self.title,create_url=self.create_url,edit_name=self.edit_name,delete_name=self.delete_name); return ctx
class Saved(AdminOnly):
    template_name="academics/crud_form.html"
    def form_valid(self,form): messages.success(self.request,"Saved successfully."); return super().form_valid(form)
class Removed(AdminOnly,DeleteView):
    template_name="academics/confirm_delete.html"
    def form_valid(self,form): messages.success(self.request,"Deleted successfully."); return super().form_valid(form)
def crud(prefix,model,form,search,queryset=None):
    key=prefix.lower(); query=queryset or model.objects.all()
    return (type(prefix+"List",(SearchList,),{"model":model,"queryset":query,"search_fields":search,"title":prefix,"create_url":f"academics:{key}_create","edit_name":f"academics:{key}_update","delete_name":f"academics:{key}_delete"}),type(prefix+"Create",(Saved,CreateView),{"model":model,"form_class":form,"success_url":reverse_lazy(f"academics:{key}_list")}),type(prefix+"Update",(Saved,UpdateView),{"model":model,"form_class":form,"success_url":reverse_lazy(f"academics:{key}_list")}),type(prefix+"Delete",(Removed,),{"model":model,"success_url":reverse_lazy(f"academics:{key}_list")}))
StudentList,StudentCreate,StudentUpdate,StudentDelete=crud("Student",StudentProfile,StudentForm,("roll_no","user__username"),StudentProfile.objects.select_related("user","classroom").prefetch_related("parents"))
TeacherList,TeacherCreate,TeacherUpdate,TeacherDelete=crud("Teacher",TeacherProfile,TeacherForm,("employee_id","user__username"),TeacherProfile.objects.select_related("user").prefetch_related("subjects").order_by("pk"))
ParentList,ParentCreate,ParentUpdate,ParentDelete=crud("Parent",ParentProfile,ParentForm,("user__username","phone"),ParentProfile.objects.select_related("user").order_by("pk"))
ClassroomList,ClassroomCreate,ClassroomUpdate,ClassroomDelete=crud("Classroom",Classroom,ClassroomForm,("name","section"),Classroom.objects.select_related("class_teacher__user"))
SubjectList,SubjectCreate,SubjectUpdate,SubjectDelete=crud("Subject",Subject,SubjectForm,("name","code"))
ClassSubjectList,ClassSubjectCreate,ClassSubjectUpdate,ClassSubjectDelete=crud("ClassSubject",ClassSubject,ClassSubjectForm,("classroom__name","subject__name"),ClassSubject.objects.select_related("classroom","subject","teacher__user").order_by("pk"))
AcademicYearList,AcademicYearCreate,AcademicYearUpdate,AcademicYearDelete=crud("AcademicYear",AcademicYear,AcademicYearForm,("name",))
