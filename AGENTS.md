# School Management System Agent Rules

Build a Django 5 school management system in `school_project` with the apps `accounts`, `academics`, `timetable`, `attendance`, `grades`, `homework`, `fees`, and `dashboard`. Use a custom `accounts.User` from the initial migration, SQLite for development, Django templates/forms, Bootstrap CDN, ReportLab PDFs, and Pillow uploads only. Server-side role and ownership checks are mandatory; all mutating forms use CSRF and validated uploads.

Architecture: models own validation and computed business rules; forms and small services coordinate workflows; class-based views enforce access with role mixins and use related-object query optimisation; templates inherit the global base and include shared navigation/messages/pagination/empty states. The four roles are admin, teacher, student and parent, mapped to Django groups by the idempotent `setup_roles` command. Each phase is verified using `check`, migration checks, migrations and tests before proceeding.
