from decimal import Decimal
from fees.money import CENT

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Sum
from django.shortcuts import render
from django.utils import timezone

from academics.models import Classroom, Subject
from accounts.models import StudentProfile, TeacherProfile
from attendance.models import Attendance
from attendance.views import attendance_summary
from fees.models import FeePayment
from grades.models import Exam, Grade
from homework.models import Submission
from timetable.models import TimetableEntry


def fee_totals(queryset):
    totals = queryset.aggregate(due=Sum("amount_due"), collected=Sum("amount_paid"))
    due = totals["due"] or Decimal("0")
    collected = totals["collected"] or Decimal("0")
    due, collected = due.quantize(CENT), collected.quantize(CENT)
    return {"due": due, "collected": collected, "pending": (due - collected).quantize(CENT)}


def latest_result(student):
    exam = Exam.objects.filter(grades__student=student).distinct().first()
    if not exam:
        return None
    totals = Grade.objects.filter(student=student, exam=exam).aggregate(earned=Sum("marks_obtained"), total=Sum("total_marks"))
    earned, total = totals["earned"] or Decimal("0"), totals["total"] or Decimal("0")
    return {"exam": exam, "earned": earned, "total": total, "percentage": earned * 100 / total if total else Decimal("0")}


@login_required
def home(request):
    user = request.user
    context = {"title": f"{user.get_role_display()} dashboard"}
    if user.role == "admin":
        context["counts"] = {"students": StudentProfile.objects.count(), "teachers": TeacherProfile.objects.count(), "classrooms": Classroom.objects.count(), "subjects": Subject.objects.count()}
        today = timezone.localdate()
        attendance = Attendance.objects.filter(date=today).aggregate(present=Count("id", filter=Q(status=Attendance.Status.PRESENT)), absent=Count("id", filter=Q(status=Attendance.Status.ABSENT)))
        context["today_attendance"] = {"present": attendance["present"], "absent": attendance["absent"], "not_marked": max(StudentProfile.objects.count() - Attendance.objects.filter(date=today).values("student_id").distinct().count(), 0)}
        context["fees"] = fee_totals(FeePayment.objects.all())
        context["recent_payments"] = FeePayment.objects.select_related("student__user", "fee_structure").order_by("-date", "-id")[:5]
        context["recent_students"] = StudentProfile.objects.select_related("user", "classroom").order_by("-id")[:5]
    elif user.role == "teacher":
        teacher = getattr(user, "teacher_profile", None)
        if teacher is None:
            context["profile_message"] = "Your teacher profile is not set up yet. Please contact a school administrator."
            return render(request, "dashboard/home.html", context)
        context["classes"] = teacher.teaching_assignments.select_related("classroom", "subject")
        context["today_periods"] = TimetableEntry.objects.filter(teacher=teacher, timeslot__day=timezone.localdate().weekday()).select_related("classroom", "subject", "timeslot")
        context["waiting_review"] = Submission.objects.filter(homework__created_by=user, status__in=(Submission.Status.SUBMITTED, Submission.Status.LATE)).count()
        context["class_teacher_classes"] = teacher.classrooms_led.all()
    elif user.role == "student":
        student = getattr(user, "student_profile", None)
        if student is None:
            context["profile_message"] = "Your student profile is not set up yet. Please contact a school administrator."
            return render(request, "dashboard/home.html", context)
        context.update(student=student, attendance_summary=attendance_summary(student.attendance_records.all()), pending_homework=student.submissions.filter(status=Submission.Status.PENDING).count(), latest_result=latest_result(student), fee_dues=fee_totals(student.fee_payments.all()))
    elif user.role == "parent":
        parent = getattr(user, "parent_profile", None)
        children = list(parent.children.select_related("user", "classroom")) if parent else []
        if not children:
            context["profile_message"] = "No children are linked to your account yet. Please contact a school administrator."
            return render(request, "dashboard/home.html", context)
        child_ids = [child.pk for child in children]
        attendance = Attendance.objects.filter(student_id__in=child_ids).values("student_id").annotate(total=Count("id"), present=Count("id", filter=Q(status=Attendance.Status.PRESENT)))
        attendance_by_student = {item["student_id"]: item for item in attendance}
        payments = FeePayment.objects.filter(student_id__in=child_ids).values("student_id").annotate(due=Sum("amount_due"), collected=Sum("amount_paid"))
        payments_by_student = {item["student_id"]: item for item in payments}
        grade_rows = Grade.objects.filter(student_id__in=child_ids).values("student_id", "exam_id", "exam__start_date", "marks_obtained", "total_marks").order_by("student_id", "-exam__start_date", "-exam_id")
        results = {}
        for row in grade_rows:
            result = results.setdefault(row["student_id"], {"exam_id": row["exam_id"], "earned": Decimal("0"), "total": Decimal("0")})
            if result["exam_id"] == row["exam_id"]:
                result["earned"] += row["marks_obtained"]
                result["total"] += row["total_marks"]
        exams_by_id = {exam.pk: exam for exam in Exam.objects.filter(pk__in=[item["exam_id"] for item in results.values()])}
        child_cards = []
        for child in children:
            record, payment, result = attendance_by_student.get(child.pk, {}), payments_by_student.get(child.pk, {}), results.get(child.pk)
            if result:
                result["exam"] = exams_by_id[result["exam_id"]]
                result["percentage"] = result["earned"] * 100 / result["total"] if result["total"] else Decimal("0")
            total, present = record.get("total", 0), record.get("present", 0)
            child_cards.append({"child": child, "attendance_percentage": present * 100 / total if total else 0, "result": result, "fee_due": ((payment.get("due") or Decimal("0.00")) - (payment.get("collected") or Decimal("0.00"))).quantize(CENT)})
        context["child_cards"] = child_cards
        context["show_child_switcher"] = len(children) > 1
    return render(request, "dashboard/home.html", context)
