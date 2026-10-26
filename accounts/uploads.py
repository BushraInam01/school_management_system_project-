from pathlib import PurePath
from uuid import uuid4


def _random_upload_path(folder, filename):
    extension = PurePath(filename).suffix.lower()
    return f"{folder}/{uuid4().hex}{extension}"


def student_photo_upload_to(instance, filename):
    return _random_upload_path("students", filename)


def homework_attachment_upload_to(instance, filename):
    return _random_upload_path("homework", filename)


def submission_upload_to(instance, filename):
    return _random_upload_path("submissions", filename)
