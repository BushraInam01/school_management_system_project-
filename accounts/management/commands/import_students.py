"""Import student and linked parent records from the documented CSV format."""
import csv
import io
import secrets
from datetime import date
from pathlib import Path
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from accounts.models import User, ParentProfile, StudentProfile
from academics.models import Classroom
class Command(BaseCommand):
    help="Import students: first_name,last_name,username,email,roll_no,class_name,section,parent_username,parent_email"
    def add_arguments(self, parser):
        parser.add_argument("csv_path"); parser.add_argument("--dry-run",action="store_true")
        parser.add_argument("--credentials-file", metavar="PATH", help="Write created usernames and temporary passwords to a CSV file.")
    def temporary_password(self, user):
        while True:
            password=secrets.token_urlsafe(18)+"A1!"
            try: validate_password(password,user)
            except ValidationError: continue
            return password
    def handle(self,*args,**options):
        created=skipped=errors=0
        credentials=[]
        call_command("setup_roles",verbosity=0)
        try:
            with open(options["csv_path"], newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
        except OSError as exc: raise CommandError(str(exc))
        required={"first_name","last_name","username","email","roll_no","class_name","section","parent_username","parent_email"}
        if not rows or not required.issubset(rows[0]): raise CommandError("CSV headers do not match the required format.")
        with transaction.atomic():
            for number,row in enumerate(rows,2):
                if not all(row.get(key,"").strip() for key in required): self.stderr.write(f"Row {number}: missing required value"); errors+=1; continue
                if User.objects.filter(username=row["username"]).exists() or StudentProfile.objects.filter(roll_no=row["roll_no"]).exists(): skipped+=1; continue
                try: classroom=Classroom.objects.get(name=row["class_name"],section=row["section"])
                except Classroom.DoesNotExist: self.stderr.write(f"Row {number}: classroom not found"); errors+=1; continue
                parent_username = row["parent_username"].strip()
                existing_parent = User.objects.filter(username=parent_username).first()
                if existing_parent:
                    if existing_parent.role != User.Role.PARENT:
                        self.stderr.write(
                            f"Row {number}: parent username '{parent_username}' belongs to an account with incompatible role '{existing_parent.role}'"
                        )
                        errors += 1
                        continue
                    if not existing_parent.is_active:
                        self.stderr.write(
                            f"Row {number}: parent username '{parent_username}' belongs to an inactive account"
                        )
                        errors += 1
                        continue
                    parent = existing_parent
                else:
                    parent = User(
                        username=parent_username,
                        email=row["parent_email"].strip(),
                        role=User.Role.PARENT,
                    )
                    parent_password = self.temporary_password(parent)
                    parent.set_password(parent_password)
                    parent.save()
                    credentials.append((parent.username, parent_password))

                student = User(
                    username=row["username"].strip(),
                    email=row["email"].strip(),
                    first_name=row["first_name"].strip(),
                    last_name=row["last_name"].strip(),
                    role="student",
                )
                student_password = self.temporary_password(student)
                student.set_password(student_password)
                student.save()
                credentials.append((student.username, student_password))
                profile = StudentProfile.objects.create(
                    user=student,
                    roll_no=row["roll_no"].strip(),
                    classroom=classroom,
                    admission_date=date.today(),
                )
                parent_profile, _ = ParentProfile.objects.get_or_create(user=parent)
                profile.parents.add(parent_profile)
                created += 1
            if options["dry_run"]: transaction.set_rollback(True)
        if not options["dry_run"] and credentials:
            output=io.StringIO(newline="")
            writer=csv.writer(output); writer.writerow(("username","temporary_password")); writer.writerows(credentials)
            if options["credentials_file"]:
                try: Path(options["credentials_file"]).write_text(output.getvalue(),encoding="utf-8",newline="")
                except OSError as exc: raise CommandError(str(exc))
            else:
                self.stdout.write("Temporary login credentials (store securely):")
                self.stdout.write(output.getvalue().rstrip())
        self.stdout.write(f"created={created} skipped={skipped} errors={errors}" + (" (rolled back)" if options["dry_run"] else ""))
