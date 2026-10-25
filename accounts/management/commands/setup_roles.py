"""Create the application role groups safely on every environment."""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group
from accounts.models import User
class Command(BaseCommand):
    help="Create Admin, Teacher, Student and Parent groups."
    def handle(self,*args,**options):
        for role,label in User.Role.choices:
            group,_=Group.objects.get_or_create(name=label)
            self.stdout.write(f"{group.name}: ready")
