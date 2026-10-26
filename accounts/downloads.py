import mimetypes
from pathlib import Path

from django.conf import settings
from django.core.exceptions import SuspiciousFileOperation
from django.http import FileResponse, Http404


def protected_file_response(upload, display_name):
    if not upload:
        raise Http404("File not found.")
    try:
        media_root = Path(settings.MEDIA_ROOT).resolve(strict=True)
        resolved_path = Path(upload.path).resolve(strict=True)
        resolved_path.relative_to(media_root)
        if not resolved_path.is_file():
            raise Http404("File not found.")
        file_handle = resolved_path.open("rb")
    except (OSError, ValueError, SuspiciousFileOperation) as exc:
        raise Http404("File not found.") from exc
    content_type = mimetypes.guess_type(display_name or "")[0] or "application/octet-stream"
    return FileResponse(file_handle, as_attachment=True, filename=display_name or resolved_path.name, content_type=content_type)
