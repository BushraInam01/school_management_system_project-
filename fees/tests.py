from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from unittest.mock import patch

from .money import money

from accounts.models import ParentProfile, StudentProfile, User
from academics.models import AcademicYear, Classroom
from .models import FeePayment, FeeStructure


class FeeWorkflowTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("admin", role="admin")
        self.classroom = Classroom.objects.create(name="9", section="A")
        self.other_classroom = Classroom.objects.create(name="9", section="B")
        self.year = AcademicYear.objects.create(name="2026", start=date(2026, 1, 1), end=date(2026, 12, 31), is_current=True)
        self.structure = FeeStructure.objects.create(classroom=self.classroom, fee_type="Tuition", amount=Decimal("100.00"), academic_year=self.year)
        self.student = StudentProfile.objects.create(user=User.objects.create_user("student", role="student"), roll_no="R1", classroom=self.classroom, admission_date=date.today())
        self.other_student = StudentProfile.objects.create(user=User.objects.create_user("other", role="student"), roll_no="R2", classroom=self.other_classroom, admission_date=date.today())

    def payment(self, amount):
        return FeePayment.objects.create(student=self.student, fee_structure=self.structure, amount_paid=Decimal(amount), method=FeePayment.Method.CASH, received_by=self.admin)

    def test_partial_payments_add_up_and_status_transitions(self):
        unpaid = self.payment("0.00")
        self.assertEqual(unpaid.status, FeePayment.Status.UNPAID)
        partial = self.payment("40.00")
        self.assertEqual(partial.status, FeePayment.Status.PARTIAL)
        paid = self.payment("60.00")
        self.assertEqual(paid.status, FeePayment.Status.PAID)
        self.assertEqual(sum(payment.amount_paid for payment in FeePayment.objects.all()), Decimal("100.00"))
        self.assertEqual(FeePayment.objects.filter(status=FeePayment.Status.PAID).count(), 3)

    def test_overpayment_rejected(self):
        self.payment("80.00")
        with self.assertRaises(ValidationError):
            self.payment("20.01")

    def test_receipt_numbers_are_unique_and_sequential(self):
        first, second = self.payment("10.00"), self.payment("10.00")
        self.assertNotEqual(first.receipt_no, second.receipt_no)
        self.assertEqual(int(second.receipt_no.rsplit("-", 1)[1]), int(first.receipt_no.rsplit("-", 1)[1]) + 1)


    def test_html_receipt_shows_balance_and_payment_method(self):
        self.payment("25.00")
        payment = FeePayment.objects.get(student=self.student)
        self.client.force_login(self.student.user)
        response = self.client.get(reverse("fees:receipt", args=[payment.pk]))
        self.assertContains(response, "Outstanding balance")
        self.assertContains(response, "Cash")
        self.assertContains(response, "75.00")

    def test_receipt_pdf_is_a_pdf(self):
        payment = self.payment("10.00")
        self.client.force_login(self.student.user)
        response = self.client.get(reverse("fees:receipt_pdf", args=[payment.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(b"".join(response.streaming_content).startswith(b"%PDF"))

    def test_money_formatter_always_uses_two_decimal_places(self):
        self.assertEqual(money(Decimal("5000")), "5000.00")
        self.assertEqual(money(Decimal("1234.5")), "1234.50")

    def test_receipt_html_and_pdf_format_total_paid_so_far(self):
        self.structure.amount = Decimal("5000.00")
        self.structure.save()
        payment = self.payment("5000.00")
        self.client.force_login(self.student.user)
        response = self.client.get(reverse("fees:receipt", args=[payment.pk]))
        self.assertContains(response, "Total paid so far")
        self.assertContains(response, "5000.00")

        rendered_lines = []
        class FakeCanvas:
            def __init__(self, _data): pass
            def drawString(self, _x, _y, value): rendered_lines.append(value)
            def showPage(self): pass
            def save(self): pass
        with patch("reportlab.pdfgen.canvas.Canvas", FakeCanvas):
            pdf_response = self.client.get(reverse("fees:receipt_pdf", args=[payment.pk]))
        self.assertEqual(pdf_response.status_code, 200)
        self.assertIn("Total paid so far: 5000.00", rendered_lines)

    def test_student_and_admin_fee_pages_format_money(self):
        self.structure.amount = Decimal("1234.50")
        self.structure.save()
        self.payment("234.50")
        self.client.force_login(self.student.user)
        response = self.client.get(reverse("fees:student", args=[self.student.pk]))
        self.assertContains(response, "1234.50")
        self.assertContains(response, "234.50")
        self.client.force_login(self.admin)
        response = self.client.get(reverse("fees:summary"))
        self.assertContains(response, "1234.50")

    def test_student_and_parent_cannot_open_unrelated_fees_or_receipts(self):
        other_structure = FeeStructure.objects.create(classroom=self.other_classroom, fee_type="Tuition", amount=Decimal("100.00"), academic_year=self.year)
        other_payment = FeePayment.objects.create(student=self.other_student, fee_structure=other_structure, amount_paid=Decimal("10.00"), method=FeePayment.Method.CASH, received_by=self.admin)
        self.client.force_login(self.student.user)
        self.assertEqual(self.client.get(reverse("fees:student", args=[self.other_student.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("fees:receipt", args=[other_payment.pk])).status_code, 403)
        parent_user = User.objects.create_user("parent", role="parent")
        parent = ParentProfile.objects.create(user=parent_user)
        self.student.parents.add(parent)
        self.client.force_login(parent_user)
        self.assertEqual(self.client.get(reverse("fees:student", args=[self.other_student.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("fees:receipt", args=[other_payment.pk])).status_code, 403)

    def test_teacher_is_forbidden_from_every_fee_url(self):
        teacher = User.objects.create_user("teacher", role="teacher")
        payment = self.payment("10.00")
        self.client.force_login(teacher)
        urls = [
            reverse("fees:list"), reverse("fees:summary"), reverse("fees:structure_list"),
            reverse("fees:structure_create"), reverse("fees:structure_edit", args=[self.structure.pk]),
            reverse("fees:structure_delete", args=[self.structure.pk]), reverse("fees:payment_create"),
            reverse("fees:student", args=[self.student.pk]), reverse("fees:receipt", args=[payment.pk]),
            reverse("fees:receipt_pdf", args=[payment.pk]),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)
