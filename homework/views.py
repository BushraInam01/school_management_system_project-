from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import F, Prefetch
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, UpdateView

from accounts.mixins import RoleRequiredMixin
from accounts.downloads import protected_file_response
from academics.models import ClassSubject, Classroom
from .forms import HomeworkForm, ReviewForm, SubmissionForm
from .models import Homework, Submission


def teacher_homework(user):
    teacher=getattr(user,"teacher_profile",None)
    if teacher is None: return Homework.objects.none()
    return Homework.objects.filter(created_by=user, classroom__class_subjects__teacher=teacher, classroom__class_subjects__subject=F("subject")).select_related("classroom", "subject").distinct()


def teacher_can_manage(user, homework):
    return user.role == "teacher" and homework.created_by_id == user.id and ClassSubject.objects.filter(classroom=homework.classroom, subject=homework.subject, teacher=user.teacher_profile).exists()


class TeacherHomeworkFormMixin(RoleRequiredMixin):
    allowed_roles = ("teacher", "admin")
    form_class = HomeworkForm
    template_name = "homework/form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["teacher"] = getattr(self.request.user, "teacher_profile", None) if self.request.user.role == "teacher" else None
        return kwargs


class HomeworkCreate(TeacherHomeworkFormMixin, CreateView):
    model = Homework
    success_url = reverse_lazy("homework:list")

    def post(self, request, *args, **kwargs):
        # Reject legacy/manipulated classroom fields as well as the scoped form choice.
        class_subject_id=request.POST.get("class_subject")
        if request.user.role == "teacher" and class_subject_id and not ClassSubject.objects.filter(pk=class_subject_id,teacher=request.user.teacher_profile).exists(): raise PermissionDenied
        classroom_id=request.POST.get("classroom")
        if request.user.role == "teacher" and classroom_id and not ClassSubject.objects.filter(classroom_id=classroom_id,teacher=request.user.teacher_profile).exists(): raise PermissionDenied
        return super().post(request,*args,**kwargs)

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, "Homework saved.")
        return super().form_valid(form)


class HomeworkUpdate(TeacherHomeworkFormMixin, UpdateView):
    model = Homework
    success_url = reverse_lazy("homework:list")

    def get_queryset(self):
        return Homework.objects.all() if self.request.user.role == "admin" else teacher_homework(self.request.user)

    def get_object(self, queryset=None):
        obj = get_object_or_404(Homework, pk=self.kwargs["pk"])
        if self.request.user.role != "admin" and not teacher_can_manage(self.request.user, obj):
            raise PermissionDenied
        return obj

    def form_valid(self, form):
        messages.success(self.request, "Homework updated.")
        return super().form_valid(form)


class HomeworkDelete(RoleRequiredMixin, DeleteView):
    allowed_roles = ("teacher", "admin")
    model = Homework
    template_name = "homework/confirm_delete.html"
    success_url = reverse_lazy("homework:list")

    def get_queryset(self):
        return Homework.objects.all() if self.request.user.role == "admin" else teacher_homework(self.request.user)

    def get_object(self, queryset=None):
        obj = get_object_or_404(Homework, pk=self.kwargs["pk"])
        if self.request.user.role != "admin" and not teacher_can_manage(self.request.user, obj):
            raise PermissionDenied
        return obj

    def form_valid(self, form):
        messages.success(self.request, "Homework deleted.")
        return super().form_valid(form)


def list_homework(request):
    if not request.user.is_authenticated:
        return redirect("login")
    base = Homework.objects.select_related("classroom", "subject", "created_by")
    context = {"items": base.none()}
    if request.user.role == "admin":
        items = base.all()
        classroom_id, status = request.GET.get("classroom"), request.GET.get("status")
        if classroom_id: items = items.filter(classroom_id=classroom_id)
        if status: items = items.filter(submissions__status=status).distinct()
        context.update(items=items, classrooms=Classroom.objects.all(), selected_classroom=classroom_id or "", selected_status=status or "")
    elif request.user.role == "teacher":
        context["items"] = teacher_homework(request.user)
        if getattr(request.user,"teacher_profile",None) is None:
            context["profile_message"]="Your teacher profile is not set up yet. Please contact a school administrator."
    elif request.user.role == "student":
        student = getattr(request.user,"student_profile",None)
        if student is None:
            context["profile_message"]="Your student profile is not set up yet. Please contact a school administrator."
            return render(request,"homework/list.html",context)
        items = list(base.filter(classroom=student.classroom).prefetch_related(Prefetch("submissions", queryset=Submission.objects.filter(student=student), to_attr="student_submissions")))
        tab, today, selected = request.GET.get("tab", "pending"), timezone.localdate(), []
        for item in items:
            item.student_submission = item.student_submissions[0] if item.student_submissions else None
            status = item.student_submission.status if item.student_submission else Submission.Status.PENDING
            include = (tab == "overdue" and status == Submission.Status.PENDING and item.due_date < today) or (tab == "pending" and status == Submission.Status.PENDING and item.due_date >= today) or (tab in (Submission.Status.SUBMITTED, Submission.Status.REVIEWED) and status == tab)
            if include: selected.append(item)
        context.update(items=selected, tab=tab)
    elif request.user.role == "parent":
        rows = []
        parent=getattr(request.user,"parent_profile",None)
        children = parent.children.select_related("user", "classroom") if parent else []
        if not children:
            context["profile_message"]="No children are linked to your account yet. Please contact a school administrator."
            return render(request,"homework/list.html",context)
        selected_child_id = request.GET.get("child")
        if selected_child_id:
            children = children.filter(pk=selected_child_id)
            if not children.exists(): raise PermissionDenied
        for child in children:
            for item in base.filter(classroom=child.classroom).prefetch_related(Prefetch("submissions", queryset=Submission.objects.filter(student=child), to_attr="child_submissions")):
                item.child, item.child_submission = child, (item.child_submissions[0] if item.child_submissions else None)
                rows.append(item)
        context.update(items=rows, parent_view=True)
    else:
        raise PermissionDenied
    return render(request, "homework/list.html", context)


def submit(request, homework_id):
    if not request.user.is_authenticated or request.user.role != "student": raise PermissionDenied
    student = request.user.student_profile
    homework = get_object_or_404(Homework.objects.select_related("classroom", "subject"), pk=homework_id, classroom=student.classroom)
    submission, _ = Submission.objects.get_or_create(homework=homework, student=student)
    if submission.status == Submission.Status.REVIEWED: raise PermissionDenied
    form = SubmissionForm(request.POST or None, request.FILES or None, instance=submission)
    if request.method == "POST" and form.is_valid():
        submitted = form.save(commit=False); submitted.submitted_at = timezone.now(); submitted.save()
        messages.success(request, "Homework submitted.")
        return redirect("homework:list")
    return render(request, "homework/submit.html", {"homework": homework, "submission": submission, "form": form})


def submission_detail(request, homework_id, submission_id):
    """Show a submission only to the student, linked parent, owning teacher, or admin."""
    if not request.user.is_authenticated:
        return redirect("login")

    submissions = Submission.objects.select_related(
        "homework__classroom", "homework__subject", "student__user"
    )
    if request.user.role == "student":
        submissions = submissions.filter(student=request.user.student_profile)
    elif request.user.role == "parent":
        submissions = submissions.filter(student__parents=request.user.parent_profile)
    elif request.user.role == "teacher":
        submissions = submissions.filter(homework__in=teacher_homework(request.user))
    elif request.user.role != "admin":
        raise PermissionDenied

    submission = get_object_or_404(
        submissions, pk=submission_id, homework_id=homework_id
    )
    # Homework does not currently define a maximum mark, but support one if
    # it is supplied by a future homework type without inventing a total.
    return render(
        request,
        "homework/submission_detail.html",
        {"submission": submission, "marks_total": getattr(submission.homework, "total_marks", None)},
    )


@login_required
def submission_download(request,submission_id):
    submission=get_object_or_404(Submission.objects.select_related("homework__created_by","student__user"),pk=submission_id)
    user=request.user
    allowed=user.role=="admin"
    if user.role=="student":
        student=getattr(user,"student_profile",None)
        allowed=bool(student and submission.student_id==student.pk)
    elif user.role=="parent":
        parent=getattr(user,"parent_profile",None)
        allowed=bool(parent and submission.student.parents.filter(pk=parent.pk).exists())
    elif user.role=="teacher":
        allowed=submission.homework.created_by_id==user.pk
    if not allowed:
        raise PermissionDenied
    return protected_file_response(submission.file,submission.file_original_name)


@login_required
def attachment_download(request,homework_id):
    homework=get_object_or_404(Homework.objects.select_related("classroom","created_by"),pk=homework_id)
    user=request.user
    allowed=user.role=="admin"
    if user.role=="student":
        student=getattr(user,"student_profile",None)
        allowed=bool(student and student.classroom_id==homework.classroom_id)
    elif user.role=="parent":
        parent=getattr(user,"parent_profile",None)
        allowed=bool(parent and parent.children.filter(classroom_id=homework.classroom_id).exists())
    elif user.role=="teacher":
        allowed=homework.created_by_id==user.pk
    if not allowed:
        raise PermissionDenied
    return protected_file_response(homework.attachment,homework.attachment_original_name)


def tracking(request, homework_id):
    homework = get_object_or_404(Homework.objects.select_related("classroom", "subject", "created_by"), pk=homework_id)
    if not request.user.is_authenticated or not (request.user.role == "admin" or teacher_can_manage(request.user, homework)): raise PermissionDenied
    students = list(homework.classroom.students.select_related("user").order_by("roll_no").prefetch_related(Prefetch("submissions", queryset=Submission.objects.filter(homework=homework), to_attr="homework_submissions")))
    counts = {"submitted": 0, "pending": 0, "late": 0}
    for student in students:
        student.submission = student.homework_submissions[0] if student.homework_submissions else None
        status = student.submission.status if student.submission else Submission.Status.PENDING
        student.homework_status = status
        if status in counts: counts[status] += 1
    return render(request, "homework/tracking.html", {"homework": homework, "students": students, "counts": counts})


def review(request, homework_id, submission_id):
    homework = get_object_or_404(Homework.objects.select_related("classroom", "subject", "created_by"), pk=homework_id)
    if not request.user.is_authenticated or not (request.user.role == "admin" or teacher_can_manage(request.user, homework)): raise PermissionDenied
    submission = get_object_or_404(Submission.objects.select_related("student__user"), pk=submission_id, homework=homework)
    form = ReviewForm(request.POST or None, instance=submission)
    if request.method == "POST" and form.is_valid():
        reviewed = form.save(commit=False); reviewed.status = Submission.Status.REVIEWED; reviewed.save()
        messages.success(request, "Submission reviewed.")
        return redirect("homework:tracking", homework_id=homework.pk)
    return render(request, "homework/review.html", {"homework": homework, "submission": submission, "form": form})
