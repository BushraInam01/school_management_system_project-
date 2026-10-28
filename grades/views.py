from decimal import Decimal
from io import BytesIO
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Avg, Q, Sum
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from accounts.models import StudentProfile
from academics.models import ClassSubject
from attendance.views import attendance_summary
from .forms import GradeEntryFormSet, ReportCardRemarkForm, grade_formset
from .models import Exam, Grade, ReportCardRemark
from school_project.query_params import safe_int


def can_access(user, student):
    teacher = getattr(user, "teacher_profile", None) if user.role == "teacher" else None
    return (
        user.role == "admin"
        or (user.role == "student" and student.user_id == user.id)
        or (user.role == "parent" and student.parents.filter(user=user).exists())
        or (
            teacher is not None
            and (
                student.classroom.class_teacher_id == teacher.id
                or student.classroom.class_subjects.filter(teacher=teacher).exists()
            )
        )
    )


def allowed_assignments(user):
    if user.role == "admin":
        return ClassSubject.objects.select_related("classroom", "subject").all()
    teacher = getattr(user, "teacher_profile", None)
    if teacher is None:
        return ClassSubject.objects.none()
    return teacher.teaching_assignments.select_related("classroom", "subject")


def report_data(student, exam):
    grades = Grade.objects.filter(student=student, exam=exam).select_related("subject")
    earned = grades.aggregate(total=Sum("marks_obtained"))["total"] or Decimal("0")
    total = grades.aggregate(total=Sum("total_marks"))["total"] or Decimal("0")
    percentage = (earned / total * 100) if total else Decimal("0")
    letter = (
        "A+"
        if percentage >= 90
        else "A"
        if percentage >= 80
        else "B"
        if percentage >= 70
        else "C"
        if percentage >= 60
        else "D"
        if percentage >= 50
        else "F"
    )
    classmates = (
        StudentProfile.objects.filter(classroom=student.classroom)
        .annotate(score=Sum("grades__marks_obtained", filter=Q(grades__exam=exam)))
        .order_by("-score", "roll_no")
    )
    student_score = next((item.score or Decimal("0") for item in classmates if item.pk == student.pk), Decimal("0"))
    rank = 1 + sum(1 for item in classmates if (item.score or Decimal("0")) > student_score)
    remark = ReportCardRemark.objects.filter(student=student, exam=exam).first()
    return {
        "grades": grades,
        "total": total,
        "earned": earned,
        "percentage": percentage,
        "letter": letter,
        "rank": rank,
        "attendance": attendance_summary(student.attendance_records.all()),
        "remark": remark,
    }


@login_required
def entry(request):
    if request.user.role not in ("teacher", "admin"):
        raise PermissionDenied
    assignments = allowed_assignments(request.user)
    raw_class_subject = (request.POST or request.GET).get("class_subject")
    raw_exam = (request.POST or request.GET).get("exam")
    legacy_classroom_id = (request.POST or request.GET).get("classroom")
    legacy_subject_id = (request.POST or request.GET).get("subject")
    if legacy_classroom_id or legacy_subject_id:
        legacy_classroom_id = safe_int(legacy_classroom_id, minimum=1, maximum=2_147_483_647)
        legacy_subject_id = safe_int(legacy_subject_id, minimum=1, maximum=2_147_483_647)
        legacy_assignment = get_object_or_404(
            ClassSubject, classroom_id=legacy_classroom_id, subject_id=legacy_subject_id
        )
        if not assignments.filter(pk=legacy_assignment.pk).exists():
            raise PermissionDenied

    selected = None
    students = StudentProfile.objects.none()
    formset = None
    class_subject_id = None
    exam_id = None

    if raw_class_subject and raw_exam:
        class_subject_id = safe_int(raw_class_subject, minimum=1, maximum=2_147_483_647)
        exam_id = safe_int(raw_exam, minimum=1, maximum=2_147_483_647)
        if not class_subject_id or not exam_id:
            raise Http404("Invalid class-subject or exam identifier.")
        selected = get_object_or_404(
            ClassSubject.objects.select_related("classroom", "subject"), pk=class_subject_id
        )
        if not assignments.filter(pk=selected.pk).exists():
            raise PermissionDenied
        exam = get_object_or_404(Exam, pk=exam_id)
        students = list(
            StudentProfile.objects.filter(classroom=selected.classroom, is_active=True)
            .select_related("user")
            .order_by("roll_no")
        )
        student_map = {s.pk: s for s in students}
        existing = list(
            Grade.objects.filter(student__in=students, exam=exam, subject=selected.subject).order_by(
                "student__roll_no", "student_id"
            )
        )
        existing_map = {g.student_id: g for g in existing}
        missing = [s for s in students if s.pk not in existing_map]

        initial_extra = [{"student_id": s.pk, "total_marks": "100"} for s in missing]
        formset_class = grade_formset(len(missing))
        existing_qs = Grade.objects.filter(pk__in=[g.pk for g in existing]).order_by(
            "student__roll_no", "student_id"
        )
        formset = formset_class(
            request.POST or None,
            queryset=existing_qs,
            initial=initial_extra,
            prefix="grades",
        )

        # Attach student references to every form in the formset
        forms = list(formset.forms)
        for grade, form in zip(existing, forms[: len(existing)]):
            form.student = grade.student
            form.expected_student = grade.student
            if "student_id" in form.fields:
                form.fields["student_id"].initial = grade.student_id
        for student, form in zip(missing, forms[len(existing) :]):
            form.student = student
            form.expected_student = student
            if "student_id" in form.fields:
                form.fields["student_id"].initial = student.pk

        if request.method == "POST" and formset.is_valid():
            with transaction.atomic():
                for form in forms:
                    data = form.cleaned_data
                    if not data or any(key not in data for key in ("marks_obtained", "total_marks")):
                        continue
                    target_student = getattr(form, "expected_student", None)
                    if not target_student or target_student.pk not in student_map:
                        continue
                    if target_student.classroom_id != selected.classroom_id:
                        continue
                    Grade.objects.update_or_create(
                        student=target_student,
                        exam=exam,
                        subject=selected.subject,
                        defaults={
                            "marks_obtained": data["marks_obtained"],
                            "total_marks": data["total_marks"],
                            "remarks": data.get("remarks", ""),
                            "entered_by": request.user,
                        },
                    )
            messages.success(request, "Grades saved.")
            return redirect(f"{request.path}?class_subject={selected.pk}&exam={exam_id}")
    else:
        formset = GradeEntryFormSet(queryset=Grade.objects.none(), prefix="grades")

    return render(
        request,
        "grades/entry.html",
        {
            "assignments": assignments,
            "exams": Exam.objects.all(),
            "students": students,
            "formset": formset,
            "class_subject_id": str(class_subject_id or ""),
            "exam_id": str(exam_id or ""),
        },
    )


@login_required
def remarks(request, student_id, exam_id):
    student = get_object_or_404(StudentProfile.objects.select_related("classroom"), pk=student_id)
    exam = get_object_or_404(Exam, pk=exam_id)
    if request.user.role == "teacher":
        teacher = getattr(request.user, "teacher_profile", None)
        if teacher is None:
            raise PermissionDenied
        if not (
            student.classroom.class_teacher_id == teacher.id
            or student.classroom.class_subjects.filter(teacher=teacher).exists()
        ):
            raise PermissionDenied
    elif request.user.role != "admin":
        raise PermissionDenied
    remark, _ = ReportCardRemark.objects.get_or_create(student=student, exam=exam)
    form = ReportCardRemarkForm(request.POST or None, instance=remark)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Remarks saved.")
        return redirect("grades:report", student_id=student.pk, exam_id=exam.pk)
    return render(request, "grades/remarks.html", {"form": form, "student": student, "exam": exam})


@login_required
def report(request, student_id, exam_id):
    student = get_object_or_404(StudentProfile.objects.select_related("user", "classroom"), pk=student_id)
    if not can_access(request.user, student):
        raise PermissionDenied
    exam = get_object_or_404(Exam, pk=exam_id)
    return render(request, "grades/report.html", {"student": student, "exam": exam, **report_data(student, exam)})


@login_required
def report_pdf(request, student_id, exam_id):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.platypus import Table, TableStyle
    from reportlab.lib import colors

    student = get_object_or_404(StudentProfile.objects.select_related("user", "classroom"), pk=student_id)
    if not can_access(request.user, student):
        raise PermissionDenied
    exam = get_object_or_404(Exam, pk=exam_id)
    data = report_data(student, exam)
    grades = data["grades"]
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    pdf.setTitle("Report Card")

    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(50, 800, "School Management System — Report Card")
    pdf.setFont("Helvetica", 10)
    student_display = str(student.user)[:35]
    pdf.drawString(
        50,
        780,
        f"Student: {student_display}  Roll number: {student.roll_no}  Class: {student.classroom}",
    )
    pdf.drawString(50, 765, f"Academic year: {exam.academic_year.name}  Exam: {exam}")

    table_data = [["Subject", "Marks", "Total", "Percentage", "Grade"]]
    for grade in grades:
        table_data.append(
            [
                grade.subject.name,
                str(grade.marks_obtained),
                str(grade.total_marks),
                f"{grade.percentage:.1f}%",
                grade.letter_grade,
            ]
        )
    table = Table(table_data, colWidths=[150, 80, 80, 100, 70])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("PADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    _, table_height = table.wrap(500, 600)
    table.drawOn(pdf, 50, 753 - 12 - table_height)
    y = 753 - 12 - table_height - 12
    pdf.drawString(
        50,
        y,
        f"Grand total: {data['earned']}/{data['total']}  Overall: {data['percentage']:.1f}% ({data['letter']})  Rank: {data['rank']}",
    )
    pdf.drawString(50, y - 25, f"Attendance: {data['attendance']['percentage']:.1f}%")
    if data["remark"] and data["remark"].teacher_remark:
        pdf.drawString(50, y - 50, f"Teacher remarks: {data['remark'].teacher_remark[:100]}")
    if data["remark"] and data["remark"].principal_remark:
        pdf.drawString(50, y - 65, f"Principal remarks: {data['remark'].principal_remark[:100]}")
    for x, label in ((50, "Class Teacher"), (240, "Principal"), (430, "Parent")):
        pdf.line(x, 100, x + 120, 100)
        pdf.drawString(x, 84, f"{label} signature")
    pdf.showPage()
    pdf.save()
    buffer.seek(0)
    return FileResponse(
        buffer,
        content_type="application/pdf",
        as_attachment=True,
        filename=f"report-card-{student.roll_no}.pdf",
    )


@login_required
def grade_list(request):
    if request.user.role == "student":
        student = getattr(request.user, "student_profile", None)
        if not student:
            messages.info(request, "Your student profile is not set up yet. Please contact a school administrator.")
            return redirect("dashboard:home")
    elif request.user.role == "parent":
        parent = getattr(request.user, "parent_profile", None)
        children = parent.children.select_related("user") if parent else StudentProfile.objects.none()
        raw_child = request.GET.get("child")
        requested_child = safe_int(raw_child, minimum=1, maximum=2_147_483_647) if raw_child else None
        if not children.exists():
            messages.info(request, "No children are linked to your account yet. Please contact a school administrator.")
            return redirect("dashboard:home")
        student = children.filter(pk=requested_child).first() if requested_child else children.first()
        if not student:
            raise PermissionDenied
    else:
        raise PermissionDenied
    exams = Exam.objects.filter(grades__student=student).distinct().prefetch_related("grades__subject")
    return render(request, "grades/list.html", {"student": student, "exams": exams})
