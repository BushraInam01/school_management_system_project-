"""Validated grade entry and report-card remark forms."""
from decimal import Decimal
from django import forms
from django.forms import modelformset_factory
from .models import Grade, ReportCardRemark


class GradeEntryForm(forms.ModelForm):
    student_id = forms.IntegerField(widget=forms.HiddenInput, required=False)

    class Meta:
        model = Grade
        fields = ("marks_obtained", "total_marks", "remarks")

    def clean(self):
        cleaned = super().clean()
        obtained = cleaned.get("marks_obtained")
        total = cleaned.get("total_marks")
        if obtained is not None and total is not None:
            if total <= 0 or obtained < 0 or obtained > total:
                raise forms.ValidationError("Marks must be between zero and total marks.")
        return cleaned


class BaseGradeEntryFormSet(forms.BaseModelFormSet):
    def clean(self):
        super().clean()
        seen_students = set()
        for form in self.forms:
            if self.can_delete and self._should_delete_form(form):
                continue
            expected_student = getattr(form, "expected_student", None)
            if not expected_student:
                continue

            raw_sid = form.data.get(form.add_prefix("student_id"))
            if raw_sid:
                try:
                    if int(raw_sid) != expected_student.pk:
                        form.add_error("student_id", "Student ID mismatch or tampering detected.")
                        form.add_error(None, "Student ID mismatch or tampering detected.")
                except (ValueError, TypeError):
                    form.add_error("student_id", "Invalid student ID.")
                    form.add_error(None, "Invalid student ID.")

            submitted_sid = form.cleaned_data.get("student_id") if hasattr(form, "cleaned_data") else None
            if submitted_sid is not None and submitted_sid != expected_student.pk:
                form.add_error("student_id", "Student ID mismatch or tampering detected.")
                form.add_error(None, "Student ID mismatch or tampering detected.")

            if form.instance and form.instance.pk:
                if form.instance.student_id != expected_student.pk:
                    form.add_error(None, "Student mismatch on existing grade record.")

            if hasattr(form, "cleaned_data") and form.cleaned_data and form.cleaned_data.get("marks_obtained") is not None:
                if expected_student.pk in seen_students:
                    form.add_error(None, f"Duplicate grade entry for student {expected_student.roll_no}.")
                seen_students.add(expected_student.pk)


GradeEntryFormSet = modelformset_factory(
    Grade, form=GradeEntryForm, formset=BaseGradeEntryFormSet, extra=0, can_delete=False
)


def grade_formset(extra=0):
    return modelformset_factory(
        Grade, form=GradeEntryForm, formset=BaseGradeEntryFormSet, extra=extra, can_delete=False
    )


class ReportCardRemarkForm(forms.ModelForm):
    class Meta:
        model = ReportCardRemark
        fields = ("teacher_remark", "principal_remark")
