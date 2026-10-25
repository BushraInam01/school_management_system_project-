from django import forms
from .models import TimeSlot, TimetableEntry
class TimeSlotForm(forms.ModelForm):
    class Meta: model=TimeSlot; fields="__all__"
class TimetableEntryForm(forms.ModelForm):
    class Meta: model=TimetableEntry; fields="__all__"
    def clean(self):
        cleaned=super().clean()
        if cleaned.get("classroom") and cleaned.get("teacher") and cleaned.get("timeslot"):
            probe=TimetableEntry(**cleaned); probe.pk=self.instance.pk
            try: probe.clean()
            except Exception as error: self.add_error(None,error)
        return cleaned
