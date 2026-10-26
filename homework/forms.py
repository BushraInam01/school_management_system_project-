from django import forms

from academics.models import ClassSubject
from .models import Homework, Submission


class ClassSubjectChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, assignment):
        return f"{assignment.classroom}: {assignment.subject.name}"


class HomeworkForm(forms.ModelForm):
    class_subject = ClassSubjectChoiceField(queryset=ClassSubject.objects.none(), label="Class and subject", empty_label=None)

    class Meta:
        model = Homework
        fields = ("class_subject", "title", "description", "due_date", "attachment")
        widgets = {"due_date": forms.DateInput(attrs={"type": "date"}), "attachment": forms.FileInput}

    def __init__(self, *args, teacher=None, **kwargs):
        super().__init__(*args, **kwargs)
        assignments = ClassSubject.objects.select_related("classroom", "subject").order_by("classroom__name", "classroom__section", "subject__name")
        if teacher is not None:
            assignments = assignments.filter(teacher=teacher)
        self.fields["class_subject"].queryset = assignments
        if self.instance.pk:
            self.initial["class_subject"] = assignments.filter(classroom_id=self.instance.classroom_id, subject_id=self.instance.subject_id).first()
        self.teacher = teacher

    def clean(self):
        cleaned = super().clean()
        assignment = cleaned.get("class_subject")
        if assignment:
            # The queryset above is teacher-scoped; derive both persisted fields here.
            self.instance.classroom = assignment.classroom
            self.instance.subject = assignment.subject
        return cleaned


class SubmissionForm(forms.ModelForm):
    class Meta:
        model = Submission
        fields = ("file", "text")
        widgets = {"file": forms.FileInput}

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("file") and not cleaned.get("text", "").strip() and not self.instance.file:
            raise forms.ValidationError("Provide a file or text submission.")
        return cleaned


class ReviewForm(forms.ModelForm):
    class Meta:
        model = Submission
        fields = ("marks", "feedback")
