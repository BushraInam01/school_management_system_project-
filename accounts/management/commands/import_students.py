"""Import student and linked parent records from the documented CSV format."""
import csv
import secrets
from datetime import date
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from accounts.models import User, ParentProfile, StudentProfile
from academics.models import Classroom
class Command(BaseCommand):
    help="Import students: first_name,last_name,username,email,roll_no,class_name,section,parent_username,parent_email"
    def add_arguments(self, parser):
        parser.add_argument("csv_path"); parser.add_argument("--dry-run",action="store_true")
    def handle(self,*args,**options):
        created=skipped=errors=0
        call_command("setup_roles",verbosity=0)
        try: rows=list(csv.DictReader(open(options["csv_path"],newline="",encoding="utf-8")))
        except OSError as exc: raise CommandError(str(exc))
        required={"first_name","last_name","username","email","roll_no","class_name","section","parent_username","parent_email"}
        if not rows or not required.issubset(rows[0]): raise CommandError("CSV headers do not match the required format.")
        with transaction.atomic():
            for number,row in enumerate(rows,2):
                if not all(row.get(key,"").strip() for key in required): self.stderr.write(f"Row {number}: missing required value"); errors+=1; continue
                if User.objects.filter(username=row["username"]).exists() or StudentProfile.objects.filter(roll_no=row["roll_no"]).exists(): skipped+=1; continue
                try: classroom=Classroom.objects.get(name=row["class_name"],section=row["section"])
                except Classroom.DoesNotExist: self.stderr.write(f"Row {number}: classroom not found"); errors+=1; continue
                student=User.objects.create_user(username=row["username"],email=row["email"],first_name=row["first_name"],last_name=row["last_name"],role="student",password=secrets.token_urlsafe(12))
                profile=StudentProfile.objects.create(user=student,roll_no=row["roll_no"],classroom=classroom,admission_date=date.today())
                parent,unused=User.objects.get_or_create(username=row["parent_username"],defaults={"email":row["parent_email"],"role":"parent"})
                if unused: parent.set_password(secrets.token_urlsafe(12)); parent.save()
                parent_profile,_=ParentProfile.objects.get_or_create(user=parent); profile.parents.add(parent_profile); created+=1
            if options["dry_run"]: transaction.set_rollback(True)
        self.stdout.write(f"created={created} skipped={skipped} errors={errors}" + (" (rolled back)" if options["dry_run"] else ""))
