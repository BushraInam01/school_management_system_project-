"""Create a repeatable, corrective demonstration school data set."""
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from accounts.models import ParentProfile, StudentProfile, TeacherProfile, User
from academics.models import AcademicYear, ClassSubject, Classroom, Subject
from attendance.models import Attendance
from fees.models import FeePayment, FeeStructure
from grades.models import Exam, Grade, ReportCardRemark
from homework.models import Homework, Submission
from timetable.models import TimeSlot, TimetableEntry


class Command(BaseCommand):
    help = "Create and correct an idempotent demonstration school data set."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Rebuild the demonstration data (destructive).")
        parser.add_argument("--yes", action="store_true", help="Confirm the destructive reset.")
        parser.add_argument("--timetable-only", action="store_true", help="Only normalize and seed timetable tables.")

    def handle(self, *args, **kwargs):
        if kwargs["reset"]:
            if not kwargs["yes"]:
                self.stderr.write(self.style.ERROR("Reset aborted: pass --yes to confirm. No changes made."))
                return
            self.stdout.write(self.style.WARNING("WARNING: --reset rebuilds demo data and deletes or replaces existing records. Back up your database first."))
            return self.reset_data()
        if kwargs["timetable_only"]:
            return self.seed_timetable()
        return self.seed_missing()

    def seed_missing(self):
        # Deliberately create-only. Existing profiles and user-entered records are never saved or deleted.
        call_command("setup_roles", verbosity=0)
        def user(username, role, first):
            obj, created = User.objects.get_or_create(username=username, defaults={"role": role, "first_name": first, "email": f"{username}@example.com"})
            if created:
                obj.set_password("DemoPass123!"); obj.save(update_fields=("password",))
            return obj
        admin = user("admin", User.Role.ADMIN, "Administrator")
        teachers = {}
        for n in (1, 2, 3):
            u=user(f"teacher{n}",User.Role.TEACHER,f"Teacher {n}")
            teachers[n],_=TeacherProfile.objects.get_or_create(user=u,defaults={"employee_id":f"T{n:03d}"})
        year,_=AcademicYear.objects.get_or_create(name="2026-27",defaults={"start":date(2026,4,1),"end":date(2027,3,31),"is_current":not AcademicYear.objects.filter(is_current=True).exists()})
        subjects={code:Subject.objects.get_or_create(code=code,defaults={"name":name})[0] for code,name in (("ENG","English"),("URD","Urdu"))}
        specs=(("Grade 6","A",1),("Grade 6","B",1),("Grade 7","A",2),("Grade 7","B",2))
        classes={}
        for name,section,tn in specs:
            c,_=Classroom.objects.get_or_create(name=name,section=section,defaults={"class_teacher":teachers[tn]})
            classes[(name,section)]=c
            for code,subject in subjects.items(): ClassSubject.objects.get_or_create(classroom=c,subject=subject,defaults={"teacher":teachers[tn]})
        parent_map={1:(1,),2:(2,3),3:(4,5,6,7),4:(8,),5:(9,),6:(10,),7:(11,),8:(12,),9:(13,),10:(14,),11:(15,),12:(16,),13:(17,),14:(18,),15:(19,),16:(20,)}
        student_class={1:("Grade 6","A"),6:("Grade 6","A"),10:("Grade 6","A"),14:("Grade 6","A"),17:("Grade 6","A"),4:("Grade 6","B"),8:("Grade 6","B"),12:("Grade 6","B"),15:("Grade 6","B"),19:("Grade 6","B"),2:("Grade 7","A"),3:("Grade 7","A"),7:("Grade 7","A"),11:("Grade 7","A"),18:("Grade 7","A"),5:("Grade 7","B"),9:("Grade 7","B"),13:("Grade 7","B"),16:("Grade 7","B"),20:("Grade 7","B")}
        students={}
        for n,cl in student_class.items():
            u=user(f"student{n}",User.Role.STUDENT,f"Student {n}")
            students[n],_=StudentProfile.objects.get_or_create(user=u,defaults={"roll_no":f"R{n:03d}","classroom":classes[cl],"admission_date":date(2026,4,1)})
        for n,children in parent_map.items():
            u=user(f"parent{n}",User.Role.PARENT,f"Parent {n}")
            parent,_=ParentProfile.objects.get_or_create(user=u)
            for child in children: parent.children.add(students[child])
        today=timezone.localdate()
        for student in students.values():
            for offset in range(30):
                day=today-timedelta(days=29-offset)
                Attendance.objects.get_or_create(student=student,date=day,defaults={"status":Attendance.Status.PRESENT,"marked_by":admin})
        exams=[]
        for n,label in ((1,"Term 1"),(2,"Term 2")):
            exam,_=Exam.objects.get_or_create(name=f"Demo Exam {n}",academic_year=year,term=label,defaults={"start_date":today-timedelta(days=90-n)})
            exams.append(exam)
        for student in students.values():
            tn=1 if student.classroom.name=="Grade 6" else 2
            for exam in exams:
                for subject in subjects.values(): Grade.objects.get_or_create(student=student,exam=exam,subject=subject,defaults={"marks_obtained":Decimal("75"),"total_marks":Decimal("100"),"remarks":"Demo grade","entered_by":teachers[tn].user})
                ReportCardRemark.objects.get_or_create(student=student,exam=exam,defaults={"teacher_remark":"Steady progress.","principal_remark":"Keep up the good work."})
        for classroom in classes.values():
            tn=1 if classroom.name=="Grade 6" else 2
            homework,_=Homework.objects.get_or_create(classroom=classroom,title="Demo homework workflow",defaults={"subject":subjects["ENG"],"description":"Seeded assignment.","due_date":today-timedelta(days=2),"created_by":teachers[tn].user})
            for student in students.values():
                if student.classroom_id==classroom.pk: Submission.objects.get_or_create(homework=homework,student=student,defaults={"status":Submission.Status.PENDING})
            structure,_=FeeStructure.objects.get_or_create(classroom=classroom,fee_type="Tuition",academic_year=year,defaults={"amount":Decimal("5000")})
            for student in students.values():
                if student.classroom_id==classroom.pk and not FeePayment.objects.filter(student=student,fee_structure=structure).exists(): FeePayment.objects.create(student=student,fee_structure=structure,amount_paid=Decimal("0"),method=FeePayment.Method.CASH,received_by=admin)
        if not TimetableEntry.objects.exists():
            self.seed_timetable()

    def seed_timetable(self):
        # This path writes only TimeSlot and TimetableEntry rows.
        specs=(("Grade 6","A",1),("Grade 6","B",1),("Grade 7","A",2),("Grade 7","B",2))
        classes={(name,section):Classroom.objects.filter(name=name,section=section).first() for name,section,_ in specs}
        teachers={number:TeacherProfile.objects.filter(user__username=f"teacher{number}").first() for number in (1,2)}
        subjects={code:Subject.objects.filter(code=code).first() for code in ("ENG","URD")}
        if not all(classes.values()) or not all(teachers.values()) or not all(subjects.values()):
            self.stderr.write(self.style.ERROR("Timetable seed needs the demo classes, teachers and subjects to exist; no timetable changes made."))
            return

        class_subjects_by_class={}
        for key,classroom in classes.items():
            teacher=teachers[1 if classroom.name=="Grade 6" else 2]
            assigned={item.subject.code:item.subject for item in ClassSubject.objects.filter(
                classroom=classroom,teacher=teacher,subject__code__in=("ENG","URD")
            ).select_related("subject")}
            if not all(code in assigned for code in ("ENG","URD")):
                self.stderr.write(self.style.ERROR(f"{classroom} needs English and Urdu assignments for its seeded teacher."))
                return
            class_subjects_by_class[key]=assigned

        # Timetable-only is a rebuild of the timetable tables. Recreating these
        # two tables' rows keeps old demo slot layouts from accumulating.
        TimetableEntry.objects.all().delete()
        TimeSlot.objects.all().delete()
        slots={}
        for day in range(6):
            for period,hour in enumerate(range(8,14)):
                slots[(day,period)]=TimeSlot.objects.create(
                    day=day,start_time=time(hour),end_time=time(hour,45)
                )

        # Each teacher's paired classes alternate slots, giving each class three
        # periods while keeping that teacher in only one classroom per slot.
        for name,section,teacher_number in specs:
            classroom=classes[(name,section)]
            teacher=teachers[teacher_number]
            class_subjects=class_subjects_by_class[(name,section)]
            offset=0 if section=="A" else 1
            for day in range(6):
                for period_index in range(3):
                    period=period_index*2+offset
                    code="ENG" if period_index%2==0 else "URD"
                    TimetableEntry.objects.create(
                        classroom=classroom,subject=class_subjects[code],teacher=teacher,
                        timeslot=slots[(day,period)],room="101"
                    )
        self.stdout.write(self.style.SUCCESS("Timetable seeded."))

    def reset_data(self):
        return self._reset_data()

    def _reset_data(self):
        call_command("setup_roles", verbosity=0)

        def demo_user(username, role, first_name):
            user, _ = User.objects.get_or_create(username=username)
            user.role, user.first_name, user.email = role, first_name, f"{username}@example.com"
            user.set_password("DemoPass123!")
            user.save()
            return user

        admin = demo_user("admin", User.Role.ADMIN, "Administrator")
        admin.is_staff = admin.is_superuser = True
        admin.save(update_fields=("is_staff", "is_superuser"))
        teachers = {}
        for number in range(1, 4):
            user = demo_user(f"teacher{number}", User.Role.TEACHER, f"Teacher {number}")
            teacher, _ = TeacherProfile.objects.get_or_create(user=user, defaults={"employee_id": f"T{number:03d}"})
            if teacher.employee_id != f"T{number:03d}":
                teacher.employee_id = f"T{number:03d}"
                teacher.save(update_fields=("employee_id",))
            teachers[number] = teacher

        year, _ = AcademicYear.objects.get_or_create(name="2026-27", defaults={"start": date(2026, 4, 1), "end": date(2027, 3, 31), "is_current": True})
        AcademicYear.objects.exclude(pk=year.pk).filter(is_current=True).update(is_current=False)
        year.start, year.end, year.is_current = date(2026, 4, 1), date(2027, 3, 31), True
        year.save(update_fields=("start", "end", "is_current"))
        subjects = {}
        for code, name in (("ENG", "English"), ("URD", "Urdu")):
            subject, _ = Subject.objects.get_or_create(code=code, defaults={"name": name})
            if subject.name != name:
                subject.name = name
                subject.save(update_fields=("name",))
            subjects[code] = subject

        class_specs = (("Grade 6", "A", 1), ("Grade 6", "B", 1), ("Grade 7", "A", 2), ("Grade 7", "B", 2))
        classrooms = {}
        for name, section, teacher_number in class_specs:
            classroom, _ = Classroom.objects.get_or_create(name=name, section=section)
            classroom.class_teacher = teachers[teacher_number]
            classroom.save(update_fields=("class_teacher",))
            classrooms[(name, section)] = classroom
        desired_classrooms = list(classrooms.values())

        # Remove all old teaching ownership before assigning the exact demo layout.
        TimetableEntry.objects.filter(Q(teacher__in=teachers.values()) | Q(classroom__in=desired_classrooms)).delete()
        ClassSubject.objects.filter(Q(teacher__in=teachers.values()) | Q(classroom__in=desired_classrooms)).delete()
        Classroom.objects.filter(class_teacher__in=teachers.values()).exclude(pk__in=[item.pk for item in desired_classrooms]).update(class_teacher=None)

        # The demo layout has no classes beyond these four. Fee payments protect
        # their fee structures, so remove them before deleting stale classrooms.
        stale_classrooms = Classroom.objects.exclude(pk__in=[item.pk for item in desired_classrooms])
        stale_students = StudentProfile.objects.filter(classroom__in=stale_classrooms)
        FeePayment.objects.filter(Q(student__in=stale_students) | Q(fee_structure__classroom__in=stale_classrooms)).delete()
        stale_students.delete()
        stale_classrooms.delete()

        for name, section, teacher_number in class_specs:
            classroom = classrooms[(name, section)]
            for code in ("ENG", "URD"):
                ClassSubject.objects.create(classroom=classroom, subject=subjects[code], teacher=teachers[teacher_number])

        # Keep exactly the current twenty demo students; deleting student21's
        # user also cascades all of that old demo student's dependent records.
        User.objects.filter(username="student21").delete()
        desired_student_usernames = {f"student{number}" for number in range(1, 21)}
        extra_students = StudentProfile.objects.exclude(user__username__in=desired_student_usernames)
        FeePayment.objects.filter(student__in=extra_students).delete()
        extra_students.delete()
        students = {}
        ordered_classrooms = [classrooms[("Grade 6", "A")], classrooms[("Grade 6", "B")], classrooms[("Grade 7", "A")], classrooms[("Grade 7", "B")]]
        student_class_map = {
            1: ("Grade 6", "A"), 6: ("Grade 6", "A"), 10: ("Grade 6", "A"), 14: ("Grade 6", "A"), 17: ("Grade 6", "A"),
            4: ("Grade 6", "B"), 8: ("Grade 6", "B"), 12: ("Grade 6", "B"), 15: ("Grade 6", "B"), 19: ("Grade 6", "B"),
            2: ("Grade 7", "A"), 3: ("Grade 7", "A"), 7: ("Grade 7", "A"), 11: ("Grade 7", "A"), 18: ("Grade 7", "A"),
            5: ("Grade 7", "B"), 9: ("Grade 7", "B"), 13: ("Grade 7", "B"), 16: ("Grade 7", "B"), 20: ("Grade 7", "B"),
        }
        for number in range(1, 21):
            user = demo_user(f"student{number}", User.Role.STUDENT, f"Student {number}")
            classroom = classrooms[student_class_map[number]]
            student, _ = StudentProfile.objects.get_or_create(user=user, defaults={"roll_no": f"R{number:03d}", "classroom": classroom, "admission_date": date(2026, 4, 1)})
            student.roll_no, student.classroom, student.admission_date = f"R{number:03d}", classroom, date(2026, 4, 1)
            student.save(update_fields=("roll_no", "classroom", "admission_date"))
            students[number] = student

        # Empty the entire parent/student join table before rebuilding exactly.
        StudentProfile.parents.through.objects.all().delete()
        desired_parent_usernames = {f"parent{number}" for number in range(1, 17)}
        User.objects.filter(role=User.Role.PARENT).exclude(username__in=desired_parent_usernames).delete()
        parents = {}
        for number in range(1, 17):
            user = demo_user(f"parent{number}", User.Role.PARENT, f"Parent {number}")
            parents[number], _ = ParentProfile.objects.get_or_create(user=user)
        parent_map = {1: (1,), 2: (2, 3), 3: (4, 5, 6, 7), 4: (8,), 5: (9,), 6: (10,), 7: (11,), 8: (12,), 9: (13,), 10: (14,), 11: (15,), 12: (16,), 13: (17,), 14: (18,), 15: (19,), 16: (20,)}
        for parent_number, student_numbers in parent_map.items():
            parents[parent_number].children.set([students[number] for number in student_numbers])

        today = timezone.localdate()
        student_list = list(students.values())
        Attendance.objects.filter(student__in=student_list).delete()
        attendance = []
        for student_index, student in enumerate(student_list):
            for offset in range(30):
                position = (student_index * 7 + offset * 3) % 30
                status = Attendance.Status.ABSENT if position == 0 else Attendance.Status.LATE if position == 1 else Attendance.Status.LEAVE if position == 2 else Attendance.Status.PRESENT
                attendance.append(Attendance(student=student, date=today - timedelta(days=29 - offset), status=status, marked_by=admin))
        Attendance.objects.bulk_create(attendance, batch_size=500)

        exams = []
        for number, label in ((1, "Term 1"), (2, "Term 2")):
            exam, _ = Exam.objects.get_or_create(name=f"Demo Exam {number}", academic_year=year, term=label, defaults={"start_date": today - timedelta(days=90 - number)})
            exam.start_date = today - timedelta(days=90 - number)
            exam.save(update_fields=("start_date",))
            exams.append(exam)
        Grade.objects.filter(student__in=student_list).delete()
        ReportCardRemark.objects.filter(student__in=student_list).delete()
        grades, remarks = [], []
        for student_index, student in enumerate(student_list):
            teacher_number = 1 if student.classroom_id in {ordered_classrooms[0].pk, ordered_classrooms[1].pk} else 2
            for exam_index, exam in enumerate(exams):
                for subject_index, subject in enumerate(subjects.values()):
                    grades.append(Grade(student=student, exam=exam, subject=subject, marks_obtained=Decimal(str(65 + ((student_index + subject_index + exam_index * 3) % 31))), total_marks=Decimal("100"), remarks="Demo grade", entered_by=teachers[teacher_number].user))
                remarks.append(ReportCardRemark(student=student, exam=exam, teacher_remark="Steady progress in the demo term.", principal_remark="Keep up the good work."))
        Grade.objects.bulk_create(grades, batch_size=500)
        ReportCardRemark.objects.bulk_create(remarks, batch_size=500)

        Homework.objects.filter(classroom__in=desired_classrooms).delete()
        for classroom in ordered_classrooms:
            teacher_number = 1 if classroom in ordered_classrooms[:2] else 2
            homework = Homework.objects.create(classroom=classroom, subject=subjects["ENG"], title="Demo homework workflow", description="A seeded assignment demonstrating all submission statuses.", due_date=today - timedelta(days=2), created_by=teachers[teacher_number].user)
            submissions = []
            for index, student in enumerate(student for student in student_list if student.classroom_id == classroom.pk):
                status = (Submission.Status.PENDING, Submission.Status.SUBMITTED, Submission.Status.LATE, Submission.Status.REVIEWED)[index % 4]
                submitted_at = None
                if status == Submission.Status.SUBMITTED:
                    submitted_at = timezone.make_aware(datetime.combine(homework.due_date - timedelta(days=1), time(12)))
                elif status == Submission.Status.LATE:
                    submitted_at = timezone.make_aware(datetime.combine(homework.due_date + timedelta(days=1), time(12)))
                elif status == Submission.Status.REVIEWED:
                    submitted_at = timezone.make_aware(datetime.combine(homework.due_date - timedelta(days=1), time(12)))
                submissions.append(Submission(homework=homework, student=student, status=status, text="" if status == Submission.Status.PENDING else "Demo submission.", submitted_at=submitted_at, marks=Decimal("85") if status == Submission.Status.REVIEWED else None, feedback="Well done." if status == Submission.Status.REVIEWED else ""))
            Submission.objects.bulk_create(submissions)

        FeePayment.objects.filter(student__in=student_list).delete()
        for classroom in ordered_classrooms:
            structure, _ = FeeStructure.objects.get_or_create(classroom=classroom, fee_type="Tuition", academic_year=year, defaults={"amount": Decimal("5000")})
            if structure.amount != Decimal("5000"):
                structure.amount = Decimal("5000")
                structure.save(update_fields=("amount",))
            for index, student in enumerate(student for student in student_list if student.classroom_id == classroom.pk):
                FeePayment.objects.create(student=student, fee_structure=structure, amount_paid=(Decimal("5000"), Decimal("2500"), Decimal("0"))[index % 3], method=FeePayment.Method.CASH, received_by=admin)

        for class_index, classroom in enumerate(ordered_classrooms):
            teacher_number = 1 if classroom in ordered_classrooms[:2] else 2
            for subject_index, code in enumerate(("ENG", "URD")):
                slot, _ = TimeSlot.objects.get_or_create(day=subject_index, start_time=time(8 + class_index), end_time=time(8 + class_index, 45))
                TimetableEntry.objects.create(classroom=classroom, subject=subjects[code], teacher=teachers[teacher_number], timeslot=slot, room="101")

        self.stdout.write("\nDemo credentials\nRole     | Username  | Password        | Notes\n---------|-----------|-----------------|----------------\nAdmin    | admin     | DemoPass123!    | Site administrator\nTeacher  | teacher1  | DemoPass123!    | Grade 6-A and Grade 6-B (English, Urdu)\nTeacher  | teacher2  | DemoPass123!    | Grade 7-A and Grade 7-B (English, Urdu)\nTeacher  | teacher3  | DemoPass123!    | No classes\nStudent  | student1  | DemoPass123!    | Grade 6-A\nStudent  | student4  | DemoPass123!    | Grade 6-B\nStudent  | student2  | DemoPass123!    | Grade 7-A\nStudent  | student5  | DemoPass123!    | Grade 7-B\nParent   | parent1   | DemoPass123!    | 1 child\nParent   | parent2   | DemoPass123!    | 2 children (both Grade 7-A)\nParent   | parent3   | DemoPass123!    | 4 children (one in each class)")
