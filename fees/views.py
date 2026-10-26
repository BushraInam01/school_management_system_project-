from io import BytesIO
from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Prefetch, Sum
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, UpdateView

from accounts.mixins import RoleRequiredMixin
from accounts.models import StudentProfile
from academics.models import Classroom
from .forms import FeePaymentForm, FeeStructureForm
from .models import FeePayment, FeeStructure
from .money import CENT, money


def permitted(user, payment):
    return user.role == "admin" or (user.role == "student" and payment.student.user_id == user.id) or (user.role == "parent" and payment.student.parents.filter(user=user).exists())


def permitted_student(user, student):
    return user.role == "admin" or (user.role == "student" and student.user_id == user.id) or (user.role == "parent" and student.parents.filter(user=user).exists())


def fee_accounts(students, classroom=None):
    accounts = []
    for student in students:
        structures = FeeStructure.objects.filter(classroom=student.classroom).select_related("academic_year", "classroom").prefetch_related(Prefetch("payments", queryset=FeePayment.objects.filter(student=student), to_attr="student_payments"))
        for structure in structures:
            paid = sum((payment.amount_paid for payment in structure.student_payments), Decimal("0.00")).quantize(CENT)
            status = FeePayment.Status.PAID if paid >= structure.amount else FeePayment.Status.PARTIAL if paid else FeePayment.Status.UNPAID
            accounts.append({"student": student, "structure": structure, "due": structure.amount, "paid": paid, "outstanding": structure.amount - paid, "status": status, "payments": structure.student_payments})
    return accounts


class AdminOnly(RoleRequiredMixin):
    allowed_roles = ("admin",)


class FeeStructureCreate(AdminOnly, CreateView):
    model = FeeStructure; form_class = FeeStructureForm; template_name = "fees/form.html"; success_url = reverse_lazy("fees:summary")
    def form_valid(self, form): messages.success(self.request, "Fee structure saved."); return super().form_valid(form)


class FeeStructureUpdate(AdminOnly, UpdateView):
    model = FeeStructure; form_class = FeeStructureForm; template_name = "fees/form.html"; success_url = reverse_lazy("fees:summary")
    def form_valid(self, form): messages.success(self.request, "Fee structure saved."); return super().form_valid(form)


class FeeStructureDelete(AdminOnly, DeleteView):
    model = FeeStructure; template_name = "fees/confirm_delete.html"; success_url = reverse_lazy("fees:summary")
    def form_valid(self, form): messages.success(self.request, "Fee structure deleted."); return super().form_valid(form)


def structure_list(request):
    if not request.user.is_authenticated or request.user.role != "admin": raise PermissionDenied
    structures = FeeStructure.objects.select_related("classroom", "academic_year")
    return render(request, "fees/structure_list.html", {"structures": structures})


class PaymentCreate(AdminOnly, CreateView):
    model = FeePayment; form_class = FeePaymentForm; template_name = "fees/payment_form.html"; success_url = reverse_lazy("fees:summary")
    def form_valid(self, form):
        form.instance.received_by = self.request.user
        messages.success(self.request, "Payment recorded.")
        return super().form_valid(form)


def summary(request):
    if not request.user.is_authenticated or request.user.role != "admin": raise PermissionDenied
    classroom_id, selected_status = request.GET.get("classroom"), request.GET.get("status", "")
    students = StudentProfile.objects.select_related("user", "classroom")
    if classroom_id: students = students.filter(classroom_id=classroom_id)
    accounts = fee_accounts(students)
    if selected_status: accounts = [account for account in accounts if account["status"] == selected_status]
    totals = {"due": sum((account["due"] for account in accounts), Decimal("0.00")).quantize(CENT), "paid": sum((account["paid"] for account in accounts), Decimal("0.00")).quantize(CENT), "pending": sum((account["outstanding"] for account in accounts), Decimal("0.00")).quantize(CENT)}
    page = Paginator(accounts, 20).get_page(request.GET.get("page"))
    return render(request, "fees/summary.html", {"accounts": page, "page_obj": page, "totals": totals, "classrooms": Classroom.objects.all(), "classroom_id": str(classroom_id or ""), "selected_status": selected_status, "statuses": FeePayment.Status})


def student_fees(request, student_id):
    student = get_object_or_404(StudentProfile.objects.select_related("user", "classroom"), pk=student_id)
    if not request.user.is_authenticated or not permitted_student(request.user, student): raise PermissionDenied
    accounts = fee_accounts([student])
    totals = {"due": sum((account["due"] for account in accounts), Decimal("0.00")).quantize(CENT), "paid": sum((account["paid"] for account in accounts), Decimal("0.00")).quantize(CENT), "outstanding": sum((account["outstanding"] for account in accounts), Decimal("0.00")).quantize(CENT)}
    return render(request, "fees/student_fees.html", {"student": student, "accounts": accounts, "totals": totals})


def list_fees(request):
    if not request.user.is_authenticated: return redirect("login")
    if request.user.role == "admin": return redirect("fees:summary")
    if request.user.role == "student":
        student = getattr(request.user, "student_profile", None)
        if student: return redirect("fees:student", student_id=student.pk)
        messages.info(request, "Your student profile is not set up yet. Please contact a school administrator.")
        return redirect("dashboard:home")
    if request.user.role == "parent":
        parent = getattr(request.user, "parent_profile", None)
        children = parent.children.all() if parent else StudentProfile.objects.none()
        child = children.filter(pk=request.GET.get("child")).first() or children.first()
        if child: return redirect("fees:student", student_id=child.pk)
        messages.info(request, "No children are linked to your account yet. Please contact a school administrator.")
        return redirect("dashboard:home")
    raise PermissionDenied


def receipt(request, payment_id):
    payment = get_object_or_404(FeePayment.objects.select_related("student__user", "fee_structure"), pk=payment_id)
    if not request.user.is_authenticated or not permitted(request.user, payment): raise PermissionDenied
    paid_so_far = (payment.amount_due - payment.balance_after).quantize(CENT)
    context = {"payment": payment, "paid_so_far": paid_so_far, "outstanding": payment.balance_after}
    return render(request, "fees/receipt.html", context)


def receipt_pdf(request, payment_id):
    from reportlab.pdfgen import canvas
    payment = get_object_or_404(FeePayment.objects.select_related("student__user", "fee_structure"), pk=payment_id)
    if not request.user.is_authenticated or not permitted(request.user, payment): raise PermissionDenied
    data = BytesIO(); pdf = canvas.Canvas(data)
    paid_so_far = (payment.amount_due - payment.balance_after).quantize(CENT)
    lines = ["School Management System", "FEE PAYMENT RECEIPT", f"Receipt number: {payment.receipt_no}", f"Payment date: {payment.date}", f"Student: {payment.student.user.get_full_name() or payment.student.user.username}", f"Roll number: {payment.student.roll_no}", f"Class: {payment.student.classroom}", f"Fee type: {payment.fee_structure.fee_type}", f"Payment method: {payment.get_method_display()}", f"Received by: {payment.received_by.get_full_name() or payment.received_by.username}", f"Total fee: {money(payment.amount_due)}", f"Amount paid this payment: {money(payment.amount_paid)}", f"Total paid so far: {money(paid_so_far)}", f"Outstanding balance: {money(payment.balance_after)}", f"Status: {payment.get_status_display()}"]
    y=780
    for line in lines:
        pdf.drawString(72,y,line); y-=16
    pdf.drawString(72, y-12, "Signature: ______________________________")
    pdf.showPage(); pdf.save(); data.seek(0)
    return FileResponse(data, content_type="application/pdf", as_attachment=True, filename=f"{payment.receipt_no}.pdf")
