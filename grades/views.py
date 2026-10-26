from io import BytesIO
from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Sum
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from accounts.models import StudentProfile
from academics.models import ClassSubject
from attendance.views import attendance_summary
from .forms import GradeEntryFormSet, ReportCardRemarkForm, grade_formset
from .models import Exam, Grade, ReportCardRemark
from school_project.query_params import safe_int
def can_access(user, student):
    teacher=getattr(user,"teacher_profile",None) if user.role=="teacher" else None
    return user.role=="admin" or (user.role=="student" and student.user_id==user.id) or (user.role=="parent" and student.parents.filter(user=user).exists()) or (teacher is not None and (student.classroom.class_teacher_id==teacher.id or student.classroom.class_subjects.filter(teacher=teacher).exists()))

def allowed_assignments(user):
    assignments=ClassSubject.objects.select_related("classroom","subject","teacher")
    if user.role=="admin": return assignments.order_by("classroom__name","classroom__section","subject__name")
    if user.role=="teacher":
        teacher=getattr(user,"teacher_profile",None)
        return assignments.filter(teacher=teacher).order_by("classroom__name","classroom__section","subject__name") if teacher else ClassSubject.objects.none()
    return ClassSubject.objects.none()

def report_data(student, exam):
    grades=list(Grade.objects.filter(student=student,exam=exam).select_related("subject"))
    total=sum((grade.total_marks for grade in grades),Decimal("0")); earned=sum((grade.marks_obtained for grade in grades),Decimal("0"))
    percentage=earned / total * 100 if total else Decimal("0")
    letter="A+" if percentage>=90 else "A" if percentage>=80 else "B" if percentage>=70 else "C" if percentage>=60 else "D" if percentage>=50 else "F"
    classmates=StudentProfile.objects.filter(classroom=student.classroom).annotate(score=Sum("grades__marks_obtained",filter=__import__("django.db.models",fromlist=["Q"]).Q(grades__exam=exam))).order_by("-score","roll_no")
    student_score=next((item.score or Decimal("0") for item in classmates if item.pk==student.pk),Decimal("0"))
    rank=1 + sum(1 for item in classmates if (item.score or Decimal("0")) > student_score)
    remark=ReportCardRemark.objects.filter(student=student,exam=exam).first()
    return {"grades":grades,"total":total,"earned":earned,"percentage":percentage,"letter":letter,"rank":rank,"attendance":attendance_summary(student.attendance_records.all()),"remark":remark}
@login_required
def entry(request):
    if request.user.role not in ("teacher","admin"): raise PermissionDenied
    assignments=allowed_assignments(request.user); class_subject_id=(request.POST or request.GET).get("class_subject"); exam_id=(request.POST or request.GET).get("exam")
    legacy_classroom_id=(request.POST or request.GET).get("classroom"); legacy_subject_id=(request.POST or request.GET).get("subject")
    if legacy_classroom_id or legacy_subject_id:
        legacy_classroom_id=safe_int(legacy_classroom_id,minimum=1,maximum=2_147_483_647); legacy_subject_id=safe_int(legacy_subject_id,minimum=1,maximum=2_147_483_647)
        legacy_assignment=get_object_or_404(ClassSubject, classroom_id=legacy_classroom_id, subject_id=legacy_subject_id)
        if not assignments.filter(pk=legacy_assignment.pk).exists(): raise PermissionDenied
    selected=None; students=StudentProfile.objects.none(); queryset=Grade.objects.none()
    if class_subject_id and exam_id:
        class_subject_id=safe_int(class_subject_id,minimum=1,maximum=2_147_483_647)
        exam_id=safe_int(exam_id,minimum=1,maximum=2_147_483_647)
        selected=get_object_or_404(ClassSubject.objects.select_related("classroom","subject"),pk=class_subject_id)
        if not assignments.filter(pk=selected.pk).exists(): raise PermissionDenied
        students=StudentProfile.objects.filter(classroom=selected.classroom).select_related("user").order_by("roll_no")
        exam=get_object_or_404(Exam,pk=exam_id)
        existing=Grade.objects.filter(student__in=students,exam=exam,subject=selected.subject).order_by("student__roll_no","student_id")
        existing_map={grade.student_id:grade for grade in existing}
        # Keep form rows in student order, including when only some grades already exist.
        initial=[{"marks_obtained":existing_map[student.pk].marks_obtained,"total_marks":existing_map[student.pk].total_marks,"remarks":existing_map[student.pk].remarks} if student.pk in existing_map else {"marks_obtained":"","total_marks":"100","remarks":""} for student in students]
        missing=[student.pk for student in students if student.pk not in existing_map]
        formset=grade_formset(len(missing))(request.POST or None,queryset=existing,initial=[row for student,row in zip(students,initial) if student.pk not in existing_map],prefix="grades")
        if request.method=="POST" and formset.is_valid():
            forms=list(formset.forms)
            if len(forms) != len(students): formset._non_form_errors=formset.error_class(["Every student must have one grade row."])
            else:
                with transaction.atomic():
                    missing_order=list(StudentProfile.objects.filter(pk__in=missing).order_by("roll_no"))
                    form_students=[grade.student for grade in existing]+missing_order
                    for student,form in zip(form_students,forms):
                        data=form.cleaned_data
                        if not data or any(key not in data for key in ("marks_obtained","total_marks","remarks")):
                            continue
                        Grade.objects.update_or_create(student=student,exam=exam,subject=selected.subject,defaults={"marks_obtained":data["marks_obtained"],"total_marks":data["total_marks"],"remarks":data["remarks"],"entered_by":request.user})
                messages.success(request,"Grades saved."); return redirect(f"{request.path}?class_subject={selected.pk}&exam={exam_id}")
    else: formset=GradeEntryFormSet(queryset=Grade.objects.none(),prefix="grades")
    return render(request,"grades/entry.html",{"assignments":assignments,"exams":Exam.objects.all(),"students":students,"formset":formset,"class_subject_id":str(class_subject_id or ""),"exam_id":str(exam_id or "")})

@login_required
def remarks(request,student_id,exam_id):
    student=get_object_or_404(StudentProfile.objects.select_related("classroom"),pk=student_id); exam=get_object_or_404(Exam,pk=exam_id)
    if request.user.role=="teacher" and not (student.classroom.class_teacher_id==request.user.teacher_profile.id or student.classroom.class_subjects.filter(teacher=request.user.teacher_profile).exists()): raise PermissionDenied
    if request.user.role not in ("teacher","admin"): raise PermissionDenied
    remark,_=ReportCardRemark.objects.get_or_create(student=student,exam=exam)
    form=ReportCardRemarkForm(request.POST or None,instance=remark)
    if request.method=="POST" and form.is_valid(): form.save(); messages.success(request,"Remarks saved."); return redirect("grades:report",student_id=student.pk,exam_id=exam.pk)
    return render(request,"grades/remarks.html",{"form":form,"student":student,"exam":exam})
@login_required
def report(request,student_id,exam_id):
    student=get_object_or_404(StudentProfile.objects.select_related("user","classroom"),pk=student_id)
    if not can_access(request.user,student): raise PermissionDenied
    exam=get_object_or_404(Exam,pk=exam_id)
    return render(request,"grades/report.html",{"student":student,"exam":exam,**report_data(student,exam)})
@login_required
def report_pdf(request,student_id,exam_id):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    student=get_object_or_404(StudentProfile.objects.select_related("user","classroom"),pk=student_id)
    if not can_access(request.user,student): raise PermissionDenied
    exam=get_object_or_404(Exam,pk=exam_id); data=report_data(student,exam); grades=data["grades"]
    buffer=BytesIO(); pdf=canvas.Canvas(buffer,pagesize=A4); pdf.setTitle("Report Card")
    from reportlab.platypus import Table, TableStyle
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    pdf.setFont("Helvetica-Bold",16); pdf.drawString(50,800,"School Management System — Report Card")
    pdf.setFont("Helvetica",10); pdf.drawString(50,780,f"Student: {student.user}  Roll number: {student.roll_no}  Class: {student.classroom}")
    pdf.drawString(50,765,f"Academic year: {exam.academic_year.name}  Exam: {exam}")
    table_data=[["Subject","Marks","Total","Percentage","Grade"]]
    for grade in grades: table_data.append([grade.subject.name,str(grade.marks_obtained),str(grade.total_marks),f"{grade.percentage:.1f}%",grade.letter_grade])
    table=Table(table_data,colWidths=[150,80,80,100,70]); table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.lightgrey),("GRID",(0,0),(-1,-1),0.5,colors.black),("PADDING",(0,0),(-1,-1),6)])); _, table_height=table.wrap(500,600); table.drawOn(pdf,50,753-12-table_height)
    y=753-12-table_height-12
    pdf.drawString(50,y,f"Grand total: {data['earned']}/{data['total']}  Overall: {data['percentage']:.1f}% ({data['letter']})  Rank: {data['rank']}")
    pdf.drawString(50,y-25,f"Attendance: {data['attendance']['percentage']:.1f}%")
    if data["remark"] and data["remark"].teacher_remark:
        pdf.drawString(50,y-50,f"Teacher remarks: {data['remark'].teacher_remark[:100]}")
    if data["remark"] and data["remark"].principal_remark:
        pdf.drawString(50,y-65,f"Principal remarks: {data['remark'].principal_remark[:100]}")
    for x,label in ((50,"Class Teacher"),(240,"Principal"),(430,"Parent")):
        pdf.line(x,100,x+120,100); pdf.drawString(x,84,f"{label} signature")
    pdf.showPage(); pdf.save(); buffer.seek(0)
    return FileResponse(buffer,content_type="application/pdf",as_attachment=True,filename=f"report-card-{student.roll_no}.pdf")

@login_required
def grade_list(request):
    if request.user.role=="student":
        student=getattr(request.user,"student_profile",None)
        if not student:
            messages.info(request,"Your student profile is not set up yet. Please contact a school administrator.")
            return redirect("dashboard:home")
    elif request.user.role=="parent":
        parent=getattr(request.user,"parent_profile",None)
        children=parent.children.select_related("user") if parent else StudentProfile.objects.none(); requested_child=request.GET.get("child")
        if not children.exists():
            messages.info(request,"No children are linked to your account yet. Please contact a school administrator.")
            return redirect("dashboard:home")
        student=children.filter(pk=requested_child).first() if requested_child else children.first()
        if not student: raise PermissionDenied
    else: raise PermissionDenied
    exams=Exam.objects.filter(grades__student=student).distinct().prefetch_related("grades__subject")
    return render(request,"grades/list.html",{"student":student,"exams":exams})
