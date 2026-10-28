from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

class FeeStructure(models.Model):
    classroom=models.ForeignKey("academics.Classroom",on_delete=models.CASCADE,related_name="fee_structures")
    fee_type=models.CharField(max_length=100)
    amount=models.DecimalField(max_digits=10,decimal_places=2)
    academic_year=models.ForeignKey("academics.AcademicYear",on_delete=models.PROTECT)
    class Meta: constraints=[models.UniqueConstraint(fields=["classroom","fee_type","academic_year"],name="unique_fee_structure")]
    def __str__(self): return f"{self.classroom} {self.fee_type}"


class ReceiptSequence(models.Model):
    year=models.PositiveIntegerField(unique=True)
    last_number=models.PositiveIntegerField(default=0)

class FeePayment(models.Model):
    class Method(models.TextChoices): CASH="cash","Cash"; BANK="bank","Bank"; ONLINE="online","Online"
    class Status(models.TextChoices): PAID="paid","Paid"; PARTIAL="partial","Partial"; UNPAID="unpaid","Unpaid"
    student=models.ForeignKey("accounts.StudentProfile",on_delete=models.PROTECT,related_name="fee_payments")
    fee_structure=models.ForeignKey(FeeStructure,on_delete=models.PROTECT,related_name="payments")
    amount_due=models.DecimalField(max_digits=10,decimal_places=2)
    amount_paid=models.DecimalField(max_digits=10,decimal_places=2,default=0)
    balance_after=models.DecimalField(max_digits=10,decimal_places=2,default=0)
    date=models.DateField(default=timezone.localdate)
    method=models.CharField(max_length=10,choices=Method.choices)
    status=models.CharField(max_length=10,choices=Status.choices,default=Status.UNPAID)
    receipt_no=models.CharField(max_length=30,unique=True,blank=True)
    received_by=models.ForeignKey("accounts.User",on_delete=models.PROTECT)
    class Meta: ordering=("-date","-id")
    def clean(self):
        if self.student_id and self.fee_structure_id and self.student.classroom_id != self.fee_structure.classroom_id:
            raise ValidationError("The student must belong to the fee structure's classroom.")
        if self.fee_structure_id and not self.pk:
            self.amount_due=self.fee_structure.amount
        if self.amount_paid < 0: raise ValidationError("Payment cannot be negative.")
        previous=FeePayment.objects.filter(student=self.student,fee_structure=self.fee_structure).exclude(pk=self.pk).aggregate(total=models.Sum("amount_paid"))["total"] or Decimal("0")
        if previous + self.amount_paid > self.amount_due: raise ValidationError("Payment exceeds the fee due.")
    def save(self,*args,**kwargs):
        with transaction.atomic():
            if self.fee_structure_id:
                structure=FeeStructure.objects.select_for_update().get(pk=self.fee_structure_id)
                if not self.pk: self.amount_due=structure.amount
            self.full_clean()
            previous=FeePayment.objects.filter(student=self.student,fee_structure=self.fee_structure).exclude(pk=self.pk).aggregate(total=models.Sum("amount_paid"))["total"] or Decimal("0")
            total=previous+self.amount_paid
            self.status=self.Status.PAID if total >= self.amount_due else self.Status.PARTIAL if total else self.Status.UNPAID
            self.balance_after=max(self.amount_due-total,Decimal("0.00"))
            if not self.receipt_no:
                year=timezone.localdate().year
                sequence,_=ReceiptSequence.objects.select_for_update().get_or_create(year=year)
                sequence.last_number+=1; sequence.save(update_fields=["last_number"])
                self.receipt_no=f"RCPT-{year}-{sequence.last_number:06d}"
            super().save(*args,**kwargs)
    @property
    def outstanding(self): return self.amount_due - self.amount_paid
