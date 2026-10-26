from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import ParentProfile, StudentProfile, TeacherProfile, User


@receiver(post_delete, sender=StudentProfile)
@receiver(post_delete, sender=TeacherProfile)
@receiver(post_delete, sender=ParentProfile)
def deactivate_profile_user(sender, instance, **kwargs):
    User.objects.filter(pk=instance.user_id).update(is_active=False)
