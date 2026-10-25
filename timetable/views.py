from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, render
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView
from accounts.mixins import RoleRequiredMixin
from academics.models import Classroom
from .forms import TimeSlotForm, TimetableEntryForm
from .models import TimeSlot, TimetableEntry
@login_required
def grid(request):
    qs=TimetableEntry.objects.select_related("classroom","subject","teacher__user","timeslot")
    selected=None; children=None; classrooms=None
    if request.user.role=="student":
        student=getattr(request.user,"student_profile",None)
        if student is None: return render(request,"timetable/grid.html",{"rows":[],"profile_message":"Your student profile is not set up yet. Please contact a school administrator."})
        qs=qs.filter(classroom=student.classroom)
    elif request.user.role=="teacher":
        teacher=getattr(request.user,"teacher_profile",None)
        if teacher is None: return render(request,"timetable/grid.html",{"rows":[],"profile_message":"Your teacher profile is not set up yet. Please contact a school administrator."})
        qs=qs.filter(teacher=teacher)
    elif request.user.role=="parent":
        parent=getattr(request.user,"parent_profile",None)
        children=parent.children.select_related("user","classroom") if parent else []
        child=children.filter(pk=request.GET.get("child")).first() or children.first()
        if child is None: return render(request,"timetable/grid.html",{"rows":[],"profile_message":"No children are linked to your account yet. Please contact a school administrator.","children":children})
        qs=qs.filter(classroom=child.classroom) if child else qs.none(); selected=child.pk if child else None
    elif request.user.role=="admin":
        classrooms=Classroom.objects.all(); classroom_id=request.GET.get("classroom")
        if classroom_id:
            qs=qs.filter(classroom_id=classroom_id); selected=int(classroom_id)
    slots=list(TimeSlot.objects.order_by("start_time","end_time","day"))
    row_pairs=sorted({(slot.start_time,slot.end_time) for slot in slots})
    rows=[{"start":start,"end":end,"cells":{}} for start,end in row_pairs]
    row_map={(row["start"],row["end"]):row for row in rows}
    for entry in qs:
        row=row_map.get((entry.timeslot.start_time,entry.timeslot.end_time))
        if row: row["cells"][entry.timeslot.day]=entry
    for row in rows: row["cells"]=[row["cells"].get(day) for day in range(6)]
    return render(request,"timetable/grid.html",{"rows":rows,"children":children,"classrooms":classrooms,"selected":selected})

class AdminOnly(RoleRequiredMixin): allowed_roles=("admin",)
class SlotList(AdminOnly,ListView): model=TimeSlot; paginate_by=10; template_name="timetable/list.html"
class EntryList(AdminOnly,ListView):
    model=TimetableEntry; paginate_by=10; template_name="timetable/list.html"
    def get_queryset(self): return TimetableEntry.objects.select_related("classroom","subject","teacher__user","timeslot")
class Saved(AdminOnly):
    template_name="timetable/form.html"
    def form_valid(self,form): messages.success(self.request,"Saved successfully."); return super().form_valid(form)
class Removed(AdminOnly,DeleteView):
    template_name="timetable/confirm_delete.html"
    def form_valid(self,form): messages.success(self.request,"Deleted successfully."); return super().form_valid(form)
TimeSlotCreate=type("TimeSlotCreate",(Saved,CreateView),{"model":TimeSlot,"form_class":TimeSlotForm,"success_url":reverse_lazy("timetable:slot_list")})
TimeSlotUpdate=type("TimeSlotUpdate",(Saved,UpdateView),{"model":TimeSlot,"form_class":TimeSlotForm,"success_url":reverse_lazy("timetable:slot_list")})
TimeSlotDelete=type("TimeSlotDelete",(Removed,),{"model":TimeSlot,"success_url":reverse_lazy("timetable:slot_list")})
EntryCreate=type("EntryCreate",(Saved,CreateView),{"model":TimetableEntry,"form_class":TimetableEntryForm,"success_url":reverse_lazy("timetable:entry_list")})
EntryUpdate=type("EntryUpdate",(Saved,UpdateView),{"model":TimetableEntry,"form_class":TimetableEntryForm,"success_url":reverse_lazy("timetable:entry_list")})
EntryDelete=type("EntryDelete",(Removed,),{"model":TimetableEntry,"success_url":reverse_lazy("timetable:entry_list")})
