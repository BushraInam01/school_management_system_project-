"""Validated grade entry and report-card remark forms."""
from django import forms
from django.forms import modelformset_factory
from .models import Grade, ReportCardRemark

class GradeEntryForm(forms.ModelForm):
    class Meta:
        model=Grade
        fields=("marks_obtained","total_marks","remarks")
    def clean(self):
        cleaned=super().clean(); obtained=cleaned.get("marks_obtained"); total=cleaned.get("total_marks")
        if obtained is not None and total is not None and (total <= 0 or obtained < 0 or obtained > total):
            raise forms.ValidationError("Marks must be between zero and total marks.")
        return cleaned

GradeEntryFormSet=modelformset_factory(Grade,form=GradeEntryForm,extra=0,can_delete=False)
def grade_formset(extra=0):
    return modelformset_factory(Grade,form=GradeEntryForm,extra=extra,can_delete=False)

class ReportCardRemarkForm(forms.ModelForm):
    class Meta:
        model=ReportCardRemark
        fields=("teacher_remark","principal_remark")
