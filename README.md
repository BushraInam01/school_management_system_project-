# School Management System

A Django 5 school-management application for administrators, teachers, students, and parents. It includes academic setup, timetables, attendance, grades and report-card PDFs, homework submission/review, fee collection with printable/PDF receipts, role-scoped dashboards, and CSV student import.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py setup_roles
python manage.py seed_demo_data
python manage.py runserver
```

The development database uses SQLite. Media files are served by Django only while `DEBUG=True`.

## Demo credentials

All seeded accounts use `DemoPass123!`.

| Role | Username | Notes |
| --- | --- | --- |
| Admin | `admin` | Site administrator |
| Teacher | `teacher1` | Grade 6-A and Grade 6-B (English, Urdu) |
| Teacher | `teacher2` | Grade 7-A and Grade 7-B (English, Urdu) |
| Teacher | `teacher3` | No assigned classes |
| Student | `student1`, `student4`, `student2`, `student5` | Grade 6-A, Grade 6-B, Grade 7-A, Grade 7-B respectively |
| Parent | `parent1`, `parent2`, `parent3` | 1 child; 2 children both in Grade 7-A; 4 children across all four classes |

`seed_demo_data` runs in safe create-only mode by default: it creates missing demo records and leaves existing records and user-entered data untouched. Use `python manage.py seed_demo_data --timetable-only` to normalize and seed only timetable slots and entries. The destructive corrective/rebuild behavior is available with `python manage.py seed_demo_data --reset --yes`; it prints a warning and requires a database backup before use. `--reset` without `--yes` aborts without changes.

| Classroom | Students |
| --- | --- |
| Grade 6-A | `student1`, `student6`, `student10`, `student14`, `student17` |
| Grade 6-B | `student4`, `student8`, `student12`, `student15`, `student19` |
| Grade 7-A | `student2`, `student3`, `student7`, `student11`, `student18` |
| Grade 7-B | `student5`, `student9`, `student13`, `student16`, `student20` |

## Student CSV import

The required header is:

```text
first_name,last_name,username,email,roll_no,class_name,section,parent_username,parent_email
```

Use a dry run to validate a file without writing data:

```bash
python manage.py import_students sample_students.csv --dry-run
python manage.py import_students sample_students.csv
```

Duplicate usernames and roll numbers are skipped. Invalid rows report their CSV row number; rows whose classroom does not exist are reported and skipped.

## Verification

```bash
python manage.py check
python manage.py makemigrations --check
python manage.py migrate
python manage.py test
python manage.py check --deploy
```

## Project layout

`accounts` owns identity, profiles, commands, and role gates. `academics` owns years, classes, subjects, and assignments. `timetable`, `attendance`, `grades`, `homework`, and `fees` own their workflows. Shared Bootstrap templates provide navigation, breadcrumbs, messages, pagination, and empty states.
