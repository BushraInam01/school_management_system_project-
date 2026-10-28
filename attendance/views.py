from datetime import date
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from accounts.models import StudentProfile
from academics.models import Classroom
from .forms import AttendanceFilterForm, AttendanceFormSet
from .models import Attendance
from school_project.query_params import safe_int


def report_period(request):
    today = timezone.localdate()
    month = safe_int(request.GET.get("month"), today.month, minimum=1, maximum=12)
    year = safe_int(request.GET.get("year"), today.year, minimum=1900, maximum=2100)
    return month, year


def permitted_classrooms(user):
    if user.role == "admin":
        return Classroom.objects.all()
    if user.role != "teacher":
        return Classroom.objects.none()
    teacher = getattr(user, "teacher_profile", None)
    if teacher is None:
        return Classroom.objects.none()
    return Classroom.objects.filter(
        Q(class_subjects__teacher=teacher) | Q(class_teacher=teacher)
    ).distinct()


def attendance_summary(records):
    total = records.count()
    present = records.filter(status="present").count()
    return {
        "present": present,
        "absent": records.filter(status="absent").count(),
        "late": records.filter(status="late").count(),
        "leave": records.filter(status="leave").count(),
        "total": total,
        "percentage": (present * 100 / total if total else 0),
    }


@login_required
def mark(request):
    if request.user.role not in ("teacher", "admin"):
        raise PermissionDenied
    classrooms = permitted_classrooms(request.user)
    filter_form = AttendanceFilterForm(request.POST or request.GET or None, classrooms=classrooms)
    raw_classroom = (request.POST or request.GET).get("classroom")
    classroom_id = safe_int(raw_classroom, minimum=1, maximum=2_147_483_647) if raw_classroom else None
    if raw_classroom and (not classroom_id or not classrooms.filter(pk=classroom_id).exists()):
        raise PermissionDenied
    students = StudentProfile.objects.none()
    selected_date = timezone.localdate()
    if filter_form.is_valid() and filter_form.cleaned_data.get("classroom"):
        classroom_id = filter_form.cleaned_data["classroom"]
        selected_date = filter_form.cleaned_data["date"]
        students = (
            StudentProfile.objects.filter(classroom_id=classroom_id, is_active=True)
            .select_related("user")
            .order_by("roll_no")
        )
    existing = {
        record.student_id: record
        for record in Attendance.objects.filter(student__in=students, date=selected_date)
    }
    initial = [
        {
            "student_id": student.pk,
            "status": existing.get(student.pk).status if student.pk in existing else "present",
            "remarks": existing.get(student.pk).remarks if student.pk in existing else "",
        }
        for student in students
    ]
    formset = AttendanceFormSet(request.POST or None, prefix="attendance", initial=initial)
    if request.method == "POST" and students and filter_form.is_valid() and formset.is_valid():
        with transaction.atomic():
            allowed_ids = set(students.values_list("pk", flat=True))
            for row in formset.cleaned_data:
                if not row:
                    continue
                if row["student_id"] not in allowed_ids:
                    raise PermissionDenied
                Attendance.objects.update_or_create(
                    student_id=row["student_id"],
                    date=selected_date,
                    defaults={
                        "status": row["status"],
                        "remarks": row.get("remarks", ""),
                        "marked_by": request.user,
                    },
                )
        messages.success(request, "Attendance saved.")
        return redirect(f"{request.path}?classroom={classroom_id}&date={selected_date}")
    return render(
        request,
        "attendance/mark.html",
        {
            "filter_form": filter_form,
            "formset": formset,
            "students": students,
            "attendance_rows": zip(students, formset),
            "sunday_warning": bool(
                filter_form.is_valid()
                and filter_form.cleaned_data.get("date")
                and filter_form.cleaned_data["date"].weekday() == 6
            ),
        },
    )


@login_required
def report(request, student_id):
    student = get_object_or_404(StudentProfile.objects.select_related("user", "classroom"), pk=student_id)
    allowed = (
        request.user.role == "admin"
        or (request.user.role == "student" and student.user_id == request.user.id)
        or (request.user.role == "parent" and student.parents.filter(user=request.user).exists())
        or (
            request.user.role == "teacher"
            and permitted_classrooms(request.user).filter(pk=student.classroom_id).exists()
        )
    )
    if not allowed:
        raise PermissionDenied
    month, year = report_period(request)
    records = student.attendance_records.filter(date__month=month, date__year=year)
    parent = getattr(request.user, "parent_profile", None) if request.user.role == "parent" else None
    children = parent.children.select_related("user") if parent else None
    return render(
        request,
        "attendance/report.html",
        {
            "student": student,
            "records": records,
            "summary": attendance_summary(records),
            "month": month,
            "year": year,
            "children": children,
        },
    )


@login_required
def my_report(request):
    if request.user.role == "student":
        student = getattr(request.user, "student_profile", None)
        if student:
            return redirect("attendance:report", student_id=student.pk)
        messages.info(request, "Your student profile is not set up yet. Please contact a school administrator.")
        return redirect("dashboard:home")
    if request.user.role == "parent":
        parent = getattr(request.user, "parent_profile", None)
        children = parent.children.all() if parent else StudentProfile.objects.none()
        raw_child = request.GET.get("child")
        child_id = safe_int(raw_child, minimum=1, maximum=2_147_483_647) if raw_child else None
        child = children.filter(pk=child_id).first() if child_id else children.first()
        if child:
            return redirect("attendance:report", student_id=child.pk)
        messages.info(request, "No children are linked to your account yet. Please contact a school administrator.")
        return redirect("dashboard:home")
    raise PermissionDenied


@login_required
def class_report(request, classroom_id):
    if request.user.role not in ("teacher", "admin"):
        raise PermissionDenied
    classroom = get_object_or_404(permitted_classrooms(request.user), pk=classroom_id)
    month, year = report_period(request)
    students = (
        classroom.students.select_related("user")
        .annotate(
            present=Count(
                "attendance_records",
                filter=Q(
                    attendance_records__date__month=month,
                    attendance_records__date__year=year,
                    attendance_records__status="present",
                ),
            ),
            absent=Count(
                "attendance_records",
                filter=Q(
                    attendance_records__date__month=month,
                    attendance_records__date__year=year,
                    attendance_records__status="absent",
                ),
            ),
            late=Count(
                "attendance_records",
                filter=Q(
                    attendance_records__date__month=month,
                    attendance_records__date__year=year,
                    attendance_records__status="late",
                ),
            ),
            leave=Count(
                "attendance_records",
                filter=Q(
                    attendance_records__date__month=month,
                    attendance_records__date__year=year,
                    attendance_records__status="leave",
                ),
            ),
        )
    )
    for student in students:
        total = student.present + student.absent + student.late + student.leave
        student.percentage = student.present * 100 / total if total else 0
    return render(
        request,
        "attendance/class_report.html",
        {"classroom": classroom, "students": students, "month": month, "year": year},
    )
