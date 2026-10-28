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
        self.assertEqual(FeePayment.objects.filter(status=FeePayment.Status.PAID).count(), 1)
        self.assertEqual(unpaid.status, FeePayment.Status.UNPAID)
        self.assertEqual(partial.status, FeePayment.Status.PARTIAL)

    def test_receipt_snapshot_survives_later_payment(self):
        self.structure.amount = Decimal("5000.00"); self.structure.save()
        first = self.payment("2000.00")
        second = self.payment("3000.00")
        first.refresh_from_db()
        self.assertEqual(first.status, FeePayment.Status.PARTIAL)
        self.assertEqual(first.balance_after, Decimal("3000.00"))
        self.assertEqual(second.status, FeePayment.Status.PAID)
        self.assertEqual(second.balance_after, Decimal("0.00"))
        self.client.force_login(self.student.user)
        response = self.client.get(reverse("fees:receipt", args=[first.pk]))
        self.assertContains(response, "Partial")
        self.assertContains(response, "3000.00")
        lines = []
        class FakeCanvas:
            def __init__(self, _data): pass
            def drawString(self, _x, _y, value): lines.append(value)
            def showPage(self): pass
            def save(self): pass
        with patch("reportlab.pdfgen.canvas.Canvas", FakeCanvas):
            pdf = self.client.get(reverse("fees:receipt_pdf", args=[first.pk]))
        self.assertEqual(pdf.status_code, 200)
        self.assertIn("Status: Partial", lines)
        self.assertIn("Outstanding balance: 3000.00", lines)

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


class AcademicYearFeeCalculationTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("fee_admin", role="admin")
        self.class_9a = Classroom.objects.create(name="9", section="A")
        self.class_9b = Classroom.objects.create(name="9", section="B")
        self.year_2025 = AcademicYear.objects.create(name="2025", start=date(2025, 1, 1), end=date(2025, 12, 31), is_current=False)
        self.year_2026 = AcademicYear.objects.create(name="2026", start=date(2026, 1, 1), end=date(2026, 12, 31), is_current=True)

        self.struct_2025_9a = FeeStructure.objects.create(classroom=self.class_9a, fee_type="Tuition", amount=Decimal("4000.00"), academic_year=self.year_2025)
        self.struct_2026_9a = FeeStructure.objects.create(classroom=self.class_9a, fee_type="Tuition", amount=Decimal("5000.00"), academic_year=self.year_2026)
        self.struct_2026_9a_lab = FeeStructure.objects.create(classroom=self.class_9a, fee_type="Lab", amount=Decimal("1000.00"), academic_year=self.year_2026)
        self.struct_2026_9b = FeeStructure.objects.create(classroom=self.class_9b, fee_type="Tuition", amount=Decimal("6000.00"), academic_year=self.year_2026)

        self.student1 = StudentProfile.objects.create(user=User.objects.create_user("stu1", role="student"), roll_no="S1", classroom=self.class_9a, admission_date=date(2025, 1, 1))
        self.student2 = StudentProfile.objects.create(user=User.objects.create_user("stu2", role="student"), roll_no="S2", classroom=self.class_9a, admission_date=date(2026, 1, 1))
        self.student3 = StudentProfile.objects.create(user=User.objects.create_user("stu3", role="student"), roll_no="S3", classroom=self.class_9a, admission_date=date(2025, 1, 1))

    def test_current_year_fees_scoped_and_historical_debt_preserved(self):
        from fees.views import fee_accounts
        from dashboard.views import fee_totals

        # Student 1 has partial payment from 2025 (4000 due, 2500 paid, 1500 outstanding)
        FeePayment.objects.create(student=self.student1, fee_structure=self.struct_2025_9a, amount_paid=Decimal("2500.00"), method=FeePayment.Method.CASH, received_by=self.admin)
        # Student 1 pays 3000 towards 2026 Tuition (5000 due, 3000 paid, 2000 outstanding)
        FeePayment.objects.create(student=self.student1, fee_structure=self.struct_2026_9a, amount_paid=Decimal("3000.00"), method=FeePayment.Method.CASH, received_by=self.admin)

        accounts1 = fee_accounts([self.student1])
        # Student 1 has 3 accounts: 2026 Tuition, 2026 Lab (unpaid), and 2025 Tuition (historical)
        self.assertEqual(len(accounts1), 3)

        struct_map = {acc["structure"].pk: acc for acc in accounts1}
        # 2026 Tuition
        self.assertEqual(struct_map[self.struct_2026_9a.pk]["due"], Decimal("5000.00"))
        self.assertEqual(struct_map[self.struct_2026_9a.pk]["paid"], Decimal("3000.00"))
        self.assertEqual(struct_map[self.struct_2026_9a.pk]["outstanding"], Decimal("2000.00"))
        # 2026 Lab (unpaid)
        self.assertEqual(struct_map[self.struct_2026_9a_lab.pk]["due"], Decimal("1000.00"))
        self.assertEqual(struct_map[self.struct_2026_9a_lab.pk]["paid"], Decimal("0.00"))
        self.assertEqual(struct_map[self.struct_2026_9a_lab.pk]["outstanding"], Decimal("1000.00"))
        # 2025 Historical debt
        self.assertEqual(struct_map[self.struct_2025_9a.pk]["due"], Decimal("4000.00"))
        self.assertEqual(struct_map[self.struct_2025_9a.pk]["paid"], Decimal("2500.00"))
        self.assertEqual(struct_map[self.struct_2025_9a.pk]["outstanding"], Decimal("1500.00"))
        self.assertFalse(struct_map[self.struct_2025_9a.pk]["is_current_year"])

        # Student 2 joined in 2026: only 2026 structures belong to student 2!
        accounts2 = fee_accounts([self.student2])
        self.assertEqual(len(accounts2), 2)
        s2_structures = {acc["structure"].pk for acc in accounts2}
        self.assertEqual(s2_structures, {self.struct_2026_9a.pk, self.struct_2026_9a_lab.pk})
        # 2025 structure is NOT assigned to student 2
        self.assertNotIn(self.struct_2025_9a.pk, s2_structures)

    def test_student_changing_classroom_preserves_old_fee_debt(self):
        from fees.views import fee_accounts
        # Student 3 was in 9-A in 2025, paid 3500 towards 2025 9-A Tuition (500 outstanding)
        FeePayment.objects.create(student=self.student3, fee_structure=self.struct_2025_9a, amount_paid=Decimal("3500.00"), method=FeePayment.Method.CASH, received_by=self.admin)

        # Student 3 is promoted to 9-B for 2026
        self.student3.classroom = self.class_9b
        self.student3.save(update_fields=["classroom"])

        accounts3 = fee_accounts([self.student3])
        self.assertEqual(len(accounts3), 2)
        struct_map = {acc["structure"].pk: acc for acc in accounts3}
        # Current classroom 9-B 2026 fee:
        self.assertEqual(struct_map[self.struct_2026_9b.pk]["due"], Decimal("6000.00"))
        self.assertEqual(struct_map[self.struct_2026_9b.pk]["outstanding"], Decimal("6000.00"))
        # Previous 9-A historical debt:
        self.assertEqual(struct_map[self.struct_2025_9a.pk]["due"], Decimal("4000.00"))
        self.assertEqual(struct_map[self.struct_2025_9a.pk]["outstanding"], Decimal("500.00"))


class PaymentConcurrencyAndReceiptTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("pay_admin", role="admin")
        self.classroom = Classroom.objects.create(name="10", section="A")
        self.year = AcademicYear.objects.create(name="2026-PAY", start=date(2026, 1, 1), end=date(2026, 12, 31), is_current=True)
        self.structure = FeeStructure.objects.create(classroom=self.classroom, fee_type="Tuition", amount=Decimal("10000.00"), academic_year=self.year)
        self.student = StudentProfile.objects.create(user=User.objects.create_user("p_stu", role="student"), roll_no="P01", classroom=self.classroom, admission_date=date.today())

    def test_multiple_installments_accumulate_safely(self):
        p1 = FeePayment.objects.create(student=self.student, fee_structure=self.structure, amount_paid=Decimal("3000.00"), method=FeePayment.Method.CASH, received_by=self.admin)
        self.assertEqual(p1.status, FeePayment.Status.PARTIAL)
        self.assertEqual(p1.balance_after, Decimal("7000.00"))

        p2 = FeePayment.objects.create(student=self.student, fee_structure=self.structure, amount_paid=Decimal("4000.00"), method=FeePayment.Method.BANK, received_by=self.admin)
        self.assertEqual(p2.status, FeePayment.Status.PARTIAL)
        self.assertEqual(p2.balance_after, Decimal("3000.00"))

        p3 = FeePayment.objects.create(student=self.student, fee_structure=self.structure, amount_paid=Decimal("3000.00"), method=FeePayment.Method.ONLINE, received_by=self.admin)
        self.assertEqual(p3.status, FeePayment.Status.PAID)
        self.assertEqual(p3.balance_after, Decimal("0.00"))

        # Crucial: Earlier payments remain immutable
        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p1.status, FeePayment.Status.PARTIAL)
        self.assertEqual(p1.balance_after, Decimal("7000.00"))
        self.assertEqual(p2.status, FeePayment.Status.PARTIAL)
        self.assertEqual(p2.balance_after, Decimal("3000.00"))

    def test_exact_overpayment_boundary_and_negative_rejection(self):
        FeePayment.objects.create(student=self.student, fee_structure=self.structure, amount_paid=Decimal("9999.00"), method=FeePayment.Method.CASH, received_by=self.admin)
        # Attempt to pay 1.01 exceeds 10000 by 0.01
        with self.assertRaises(ValidationError):
            FeePayment.objects.create(student=self.student, fee_structure=self.structure, amount_paid=Decimal("1.01"), method=FeePayment.Method.CASH, received_by=self.admin)

        # Negative payment rejected
        with self.assertRaises(ValidationError):
            FeePayment.objects.create(student=self.student, fee_structure=self.structure, amount_paid=Decimal("-10.00"), method=FeePayment.Method.CASH, received_by=self.admin)

        # Exact 1.00 settlement succeeds
        exact = FeePayment.objects.create(student=self.student, fee_structure=self.structure, amount_paid=Decimal("1.00"), method=FeePayment.Method.CASH, received_by=self.admin)
        self.assertEqual(exact.status, FeePayment.Status.PAID)
        self.assertEqual(exact.balance_after, Decimal("0.00"))

    def test_invalid_query_params_on_fees_views_handled_cleanly(self):
        self.client.force_login(self.admin)
        # Bad classroom query param
        resp = self.client.get(reverse("fees:summary"), {"classroom": "invalid"})
        self.assertEqual(resp.status_code, 200)

        # Bad student_id in student fees
        resp404 = self.client.get(reverse("fees:student", args=[999999]))
        self.assertEqual(resp404.status_code, 404)
