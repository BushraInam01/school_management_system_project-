from django import forms
from django.db.models import Sum
from decimal import Decimal

from accounts.models import StudentProfile
from .models import FeePayment, FeeStructure


class FeeStructureForm(forms.ModelForm):
    class Meta:
        model = FeeStructure
        fields = ("classroom", "fee_type", "amount", "academic_year")


class FeePaymentForm(forms.ModelForm):
    amount_paid = forms.DecimalField(label="Amount", min_value=0)

    class Meta:
        model = FeePayment
        fields = ("student", "fee_structure", "amount_paid", "method", "date")
        widgets = {"date": forms.DateInput(attrs={"type": "date"})}

    def clean(self):
        cleaned = super().clean()
        student, structure = cleaned.get("student"), cleaned.get("fee_structure")
        if student and structure:
            if student.classroom_id != structure.classroom_id:
                self.add_error("fee_structure", "Choose a fee structure for the student's classroom.")
            else:
                paid = FeePayment.objects.filter(student=student, fee_structure=structure).aggregate(total=Sum("amount_paid"))["total"] or Decimal("0.00")
                if paid + (cleaned.get("amount_paid") or 0) > structure.amount:
                    self.add_error("amount_paid", "Payment exceeds the fee due.")
        return cleaned
