from django.core.exceptions import ValidationError
from django.db import models

class TimeSlot(models.Model):
    class Day(models.IntegerChoices):
        MONDAY=0,"Monday"; TUESDAY=1,"Tuesday"; WEDNESDAY=2,"Wednesday"; THURSDAY=3,"Thursday"; FRIDAY=4,"Friday"; SATURDAY=5,"Saturday"
    day=models.PositiveSmallIntegerField(choices=Day.choices)
    start_time=models.TimeField()
    end_time=models.TimeField()
    class Meta:
        ordering=("day","start_time")
        constraints=[models.UniqueConstraint(fields=["day","start_time","end_time"],name="unique_slot")]
    def clean(self):
        if self.start_time >= self.end_time: raise ValidationError("End time must be after start time.")
        overlaps=TimeSlot.objects.filter(day=self.day,start_time__lt=self.end_time,end_time__gt=self.start_time)
        if self.pk: overlaps=overlaps.exclude(pk=self.pk)
        if overlaps.exists(): raise ValidationError("This time slot overlaps another slot on the same day.")
    def __str__(self): return f"{self.get_day_display()} {self.start_time:%H:%M}-{self.end_time:%H:%M}"

class TimetableEntry(models.Model):
    classroom=models.ForeignKey("academics.Classroom",on_delete=models.CASCADE,related_name="timetable_entries")
    subject=models.ForeignKey("academics.Subject",on_delete=models.PROTECT)
    teacher=models.ForeignKey("accounts.TeacherProfile",on_delete=models.PROTECT,related_name="timetable_entries")
    timeslot=models.ForeignKey(TimeSlot,on_delete=models.PROTECT,related_name="entries")
    room=models.CharField(max_length=30,blank=True)
    class Meta:
        ordering=("timeslot__day","timeslot__start_time")
        constraints=[models.UniqueConstraint(fields=["classroom","timeslot"],name="classroom_slot_clash"),models.UniqueConstraint(fields=["teacher","timeslot"],name="teacher_slot_clash")]
    def clean(self):
        from academics.models import ClassSubject
        if not ClassSubject.objects.filter(classroom=self.classroom,subject=self.subject,teacher=self.teacher).exists():
            raise ValidationError("Teacher must be assigned to this classroom and subject.")
        if not self.timeslot_id or not self.teacher_id or not self.classroom_id: return
        slot=self.timeslot
        conflicts=TimetableEntry.objects.filter(
            timeslot__day=slot.day,
            timeslot__start_time__lt=slot.end_time,
            timeslot__end_time__gt=slot.start_time,
        ).filter(models.Q(teacher_id=self.teacher_id)|models.Q(classroom_id=self.classroom_id))
        if self.pk: conflicts=conflicts.exclude(pk=self.pk)
        if conflicts.exists():
            raise ValidationError("This teacher or classroom is already booked during an overlapping time slot.")
    def __str__(self): return f"{self.classroom} {self.subject} {self.timeslot}"
