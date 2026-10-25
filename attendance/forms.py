"""Formset and filters for bulk attendance workflow."""
from django import forms
from django.forms import formset_factory
from django.utils import timezone
from .models import Attendance

class AttendanceRowForm(forms.Form):
    student_id=forms.IntegerField(widget=forms.HiddenInput)
    status=forms.ChoiceField(choices=Attendance.Status.choices, initial=Attendance.Status.PRESENT)
    remarks=forms.CharField(max_length=255, required=False)

AttendanceFormSet=formset_factory(AttendanceRowForm, extra=0)

class AttendanceFilterForm(forms.Form):
    classroom=forms.ChoiceField(required=False)
    date=forms.DateField(initial=timezone.localdate, widget=forms.DateInput(attrs={"type":"date"}))
    def __init__(self,*args,classrooms=None,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields["classroom"].choices=[("","Choose a classroom")] + [(item.pk,str(item)) for item in (classrooms or [])]
    def clean_date(self):
        value=self.cleaned_data["date"]
        if value > timezone.localdate(): raise forms.ValidationError("Attendance cannot be marked in the future.")
        return value
