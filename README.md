# School Management System

A role-based school management web application built with **Django 5.2** (Templates + Forms). It provides separate portals for **Admin, Teacher, Student and Parent**, covering timetables, attendance, grades with PDF report cards, homework, and fee records.

---

## Features

### Role-based portals
| Role | What they can do |
|---|---|
| **Admin** | Full access: manage students, teachers, parents, classrooms, subjects, class-subject assignments, academic years, timetable, fees, attendance, grades and homework. Dashboard with school statistics. |
| **Teacher** | Only their own classes: mark attendance, enter grades, write report card remarks, create homework, review submissions, view their timetable. Class teachers can also see their class reports. |
| **Student** | Read-only access to their own timetable, attendance, grades, report card (PDF) and fees. Submits homework and sees teacher feedback. |
| **Parent** | Read-only access to linked children only, with a child switcher when there is more than one child. Can download report cards and view fees and homework. |

### Modules
- **Timetable and scheduling:** weekly grid (Monday to Saturday), 6 periods per day, clash validation (a teacher or a class cannot be double-booked).
- **Attendance:** bulk marking for a whole class on one page (Django formset), editing already-marked days, monthly class and student reports with attendance percentage, highlighting below 75%, warning on Sundays, future dates rejected.
- **Grades and report cards:** bulk grade entry with a Django model formset, validation (0 to total marks), automatic percentage and grade letter, class rank, teacher/principal remarks, and **PDF report cards** generated with ReportLab.
- **Homework:** teachers assign homework, students submit text or files (size and extension validated), automatic late detection, submission tracking (Submitted / Pending / Late), review with marks and feedback.
- **Fees:** fee structures, partial payments, overpayment prevention, auto-generated unique receipt numbers (`RCPT-YYYY-000001`), outstanding balance, fee summary, and HTML and **PDF receipts**. All amounts are shown with two decimals.

### Security
- Permissions are enforced **on the server** in every view, never just by hiding links.
- Ownership-filtered queries: changing an ID in the URL never exposes another user's data (returns 403/404).
- CSRF protection on all forms, upload validation, custom 403/404/500 pages.

---

## Tech stack
- Python 3.11+
- Django 5.2
- SQLite (development)
- ReportLab (PDF generation), Pillow (image fields)
- Bootstrap 5 (CDN)

---

## Project structure

```
school_management_system_project/
├── school_project/   # settings, root URLs
├── accounts/         # custom User, profiles, role mixins, management commands
├── academics/        # academic years, classrooms, subjects, class-subjects, admin CRUD
├── timetable/        # time slots, timetable entries, weekly grid
├── attendance/       # attendance marking and monthly reports
├── grades/           # exams, grades, remarks, report card PDF
├── homework/         # homework, submissions, tracking and review
├── fees/             # fee structures, payments, receipts
├── dashboard/        # role-specific dashboards
├── templates/        # shared templates (base, sidebar, errors, per-app pages)
├── sample_students.csv
├── requirements.txt
└── manage.py
```

---

## Getting started

### 1. Clone the repository
```bash
git clone https://github.com/BushraInam01/school_management_system_project-.git
cd school_management_system_project-
```

### 2. Create and activate a virtual environment

**Linux / macOS / WSL (Ubuntu):**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

**Windows (PowerShell):**
```powershell
python -m venv .venv
.venv\Scripts\activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Set up the database and demo data
```bash
python manage.py migrate
python manage.py seed_demo_data
```

### 5. Run the server
```bash
python manage.py runserver
```

Open **http://127.0.0.1:8000/**. You will be redirected to the login page, and to `/dashboard/` after login.

---

## Demo accounts

All demo accounts use the password **`DemoPass123!`**

| Role | Username | Notes |
|---|---|---|
| Admin | `admin` | Full access |
| Teacher | `teacher1` | Grade 6-A and Grade 6-B (class teacher of both) |
| Teacher | `teacher2` | Grade 7-A and Grade 7-B (class teacher of both) |
| Teacher | `teacher3` | No classes (used to test empty states and isolation) |
| Student | `student1` to `student20` | e.g. `student1` is in Grade 6-A |
| Parent | `parent1` | 1 child (student1) |
| Parent | `parent2` | 2 children (student2, student3, both in Grade 7-A) |
| Parent | `parent3` | 4 children (student4, student5, student6, student7 across four classes) |
| Parent | `parent4` to `parent16` | 1 child each (student8 to student20) |

### Demo layout
- **4 classrooms**, 5 students each: Grade 6-A, Grade 6-B, Grade 7-A, Grade 7-B
- **Subjects:** English and Urdu
- **Data included:** one month of attendance, 2 exams with grades and remarks, homework with mixed submission statuses, and fee payments with mixed Paid/Partial/Unpaid statuses

---

## Management commands

### `setup_roles`
Creates the Admin / Teacher / Student / Parent groups and assigns permissions. Safe to run repeatedly.
```bash
python manage.py setup_roles
```

### `seed_demo_data`
Creates demo data. **Safe by default:** it only creates what is missing and never overwrites existing records.

| Command | What it does |
|---|---|
| `python manage.py seed_demo_data` | Creates only missing demo data |
| `python manage.py seed_demo_data --timetable-only` | Rebuilds only time slots and timetable entries |
| `python manage.py seed_demo_data --reset --yes` | Rebuilds all demo data, **deleting or replacing existing records** |

> **Warning:** Back up `db.sqlite3` before using `--reset`. Without `--yes`, `--reset` aborts and changes nothing.

### `import_students`
Bulk-imports students from a CSV file.
```bash
# Preview only (nothing is saved)
python manage.py import_students sample_students.csv --dry-run

# Real import
python manage.py import_students sample_students.csv
```

**CSV columns:**
```
first_name,last_name,username,email,roll_no,class_name,section,parent_username,parent_email
```

The command validates every row, skips duplicates (username or roll number), creates the user, student profile and parent link, assigns groups, generates a temporary password, runs inside a transaction, and prints a summary of created / skipped / errors with row numbers. A sample file is included as `sample_students.csv`.

---

## Running the tests
```bash
python manage.py test
```
The suite (68 tests) covers role permissions, URL-tampering isolation, attendance formsets, grade validation and ranking, PDF generation, homework rules, fee calculations, timetable clash validation, seeding and import commands, and an admin-access audit over all URLs.

Other useful checks:
```bash
python manage.py check
python manage.py makemigrations --check
```

---

## Django admin
The Django admin is available at `/admin/` (log in as `admin`) and uses **inlines**:
- **User:** StudentProfile / TeacherProfile / ParentProfile
- **Classroom:** ClassSubject
- **Exam:** Grade

---

## Concepts demonstrated
- Django groups and permissions, with a role mixin and decorator for role-based access
- Formsets for bulk attendance marking and bulk grade entry
- PDF report cards and receipts with ReportLab
- Custom management commands (data import, demo seeding)
- Django admin inlines
- Template-driven conditional rendering per role

---

## Known limitations
- Development settings (`DEBUG=True`, a development `SECRET_KEY`, empty `ALLOWED_HOSTS`, no HTTPS/HSTS). `python manage.py check --deploy` reports these warnings by design.
- SQLite is used for development only. Use PostgreSQL or similar for production.
- Uploaded files are served by Django only when `DEBUG=True`. A production setup needs proper media file hosting.
- Teachers cannot edit the timetable. Only the admin manages it, which avoids scheduling clashes.

